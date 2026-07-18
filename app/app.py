from math import pi
import sys
from pathlib import Path
import os
import re

import requests
from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingest.populate_db import (  # noqa: E402
    lookup_composer,
    lookup_raga,
    lookup_talam,
    normalize_for_match,
    parse_description,
)

load_dotenv()

IS_PRODUCTION = os.getenv("FLASK_ENV") == "production"

if IS_PRODUCTION:
    missing = [
        k for k in (
            "DATABASE_URI",
            "SECRET_KEY",
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD",
            "TURNSTILE_SITE_KEY",
            "TURNSTILE_SECRET_KEY",
        )
        if not os.getenv(k)
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

app = Flask(
    __name__,
    template_folder='../client',
    static_folder='../client',
    static_url_path='',
)

if IS_PRODUCTION:
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.config['TEMPLATES_AUTO_RELOAD'] = False
    app.jinja_env.auto_reload = False
else:
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-only')
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
)


@app.errorhandler(429)
def rate_limit_exceeded(_error):
    return jsonify({"error": "Too many requests. Please try again later."}), 429


db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Entity Tables

class Concert(db.Model):
    __tablename__ = 'concerts'
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(255), unique=True, nullable=False)
    title = db.Column(db.String(255), index=True)
    year = db.Column(db.Integer, index=True)
    venue = db.Column(db.String(255))
    duration_seconds = db.Column(db.Integer, nullable=True)

    setlist_items = db.relationship('SetlistItem', back_populates='concert', order_by='SetlistItem.sequence_number')
    concert_artists = db.relationship('ConcertArtist', back_populates='concert')

    def __repr__(self):
        return f"<Concert {self.title}>"

class Artist(db.Model):
    __tablename__ = 'artists'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))

    concert_artists = db.relationship('ConcertArtist', back_populates='artist')

    def __repr__(self):
        return f"<Artist {self.name}>"

class Composer(db.Model):
    __tablename__ = 'composers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)

    pieces = db.relationship('Piece', back_populates='composer')

    def __repr__(self):
        return f"<Composer {self.name}>"

class Raga(db.Model):
    __tablename__ = 'ragas'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)

    pieces = db.relationship('Piece', back_populates='raga')

    def __repr__(self):
        return f"<Raga {self.name}>"

class Talam(db.Model):
    __tablename__ = 'talams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)

    pieces = db.relationship('Piece', back_populates='talam')

    def __repr__(self):
        return f"<Talam {self.name}>"

class Piece(db.Model):
    __tablename__ = 'pieces'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    kind = db.Column(db.String(255)) # krithi, padam, varnam
    raga_id = db.Column(db.Integer, db.ForeignKey('ragas.id'), nullable=True, index=True)
    composer_id = db.Column(db.Integer, db.ForeignKey('composers.id'), nullable=True, index=True)
    talam_id = db.Column(db.Integer, db.ForeignKey('talams.id'), nullable=True, index=True)

    raga = db.relationship('Raga', back_populates='pieces')
    composer = db.relationship('Composer', back_populates='pieces')
    talam = db.relationship('Talam', back_populates='pieces')
    setlist_items = db.relationship('SetlistItem', back_populates='piece')

    __table_args__ = (
        db.UniqueConstraint('name', 'kind', 'raga_id', 'composer_id', 'talam_id', name='uix_piece_name_kind_raga_composer_talam'),
    )

    def __repr__(self):
        return f"<Piece {self.name}>"

# Junction tables

class ConcertArtist(db.Model):
    __tablename__ = 'concert_artists'
    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey('concerts.id', ondelete='CASCADE'), nullable=False, index=True)
    artist_id = db.Column(db.Integer, db.ForeignKey('artists.id'), nullable=False, index=True)
    instrument = db.Column(db.String(255))
    role = db.Column(db.String(255))  # "main artist" or "accompanist"

    concert = db.relationship('Concert', back_populates='concert_artists')
    artist = db.relationship('Artist', back_populates='concert_artists')

    __table_args__ = (
        db.Index('ix_concertartist_artist_role', 'artist_id', 'role'),
        db.UniqueConstraint('concert_id', 'artist_id', 'instrument', 'role', name='uix_concertartist_artist_instrument_role'),
    )

    def __repr__(self):
        return f"<ConcertArtist concert={self.concert_id} artist={self.artist_id} role={self.role!r}>"

class SetlistItem(db.Model):
    __tablename__ = 'setlist_items'
    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey('concerts.id', ondelete='CASCADE'), nullable=False, index=True)
    piece_id = db.Column(db.Integer, db.ForeignKey('pieces.id', ondelete='SET NULL'), nullable=True, index=True)
    timestamp_seconds = db.Column(db.Integer, nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)

    concert = db.relationship('Concert', back_populates='setlist_items')
    piece = db.relationship('Piece', back_populates='setlist_items')

    __table_args__ = (
        db.UniqueConstraint('concert_id', 'sequence_number', name='unique_concert_sequence'),
    )

    def __repr__(self):
        return f"<SetlistItem {self.piece_id}>"

class PieceAlias(db.Model):
    __tablename__ = 'piece_aliases'
    id = db.Column(db.Integer, primary_key=True)
    piece_id = db.Column(db.Integer, db.ForeignKey('pieces.id', ondelete='CASCADE'), nullable=False, index=True)
    alias = db.Column(db.String(255), nullable=False)

    piece = db.relationship('Piece', backref=db.backref('aliases', cascade='all, delete-orphan'))

    __table_args__ = (
        db.Index(
            'idx_piece_aliases_trgm',
            'alias',
            postgresql_using='gin',
            postgresql_ops={
                'alias': 'gin_trgm_ops'
            }
        ),
    )

# USER CONTRIBUTIONS

class ConcertDraft(db.Model):
    __tablename__ = 'concert_drafts'
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), index=True)
    year = db.Column(db.Integer, index=True)
    venue = db.Column(db.String(255))
    duration_seconds = db.Column(db.Integer, nullable=True)

    status = db.Column(db.String(50), default='submitted', index=True)

    setlist_item_drafts = db.relationship(
        'SetlistItemDraft',
        back_populates='concert_draft',
        order_by='SetlistItemDraft.sequence_number',
        cascade='all, delete-orphan',
    )
    concert_artist_drafts = db.relationship(
        'ConcertArtistDraft',
        back_populates='concert_draft',
        cascade='all, delete-orphan',
    )

class SetlistItemDraft(db.Model):
    __tablename__ = 'setlist_item_drafts'
    id = db.Column(db.Integer, primary_key=True)
    concert_draft_id = db.Column(db.Integer, db.ForeignKey('concert_drafts.id', ondelete='CASCADE'), nullable=False, index=True)

    # existing piece selected by user
    piece_id = db.Column(db.Integer, db.ForeignKey('pieces.id', ondelete='SET NULL'), nullable=True, index=True)
    raga_id = db.Column(db.Integer, db.ForeignKey('ragas.id', ondelete='SET NULL'), nullable=True, index=True)
    talam_id = db.Column(db.Integer, db.ForeignKey('talams.id', ondelete='SET NULL'), nullable=True, index=True)
    composer_id = db.Column(db.Integer, db.ForeignKey('composers.id', ondelete='SET NULL'), nullable=True, index=True)

    # new piece data entered by user
    piece_name = db.Column(db.String(255), nullable=False)
    raga_name = db.Column(db.String(255), nullable=True)
    talam_name = db.Column(db.String(255), nullable=True)
    composer_name = db.Column(db.String(255), nullable=True)
    kind = db.Column(db.String(50), nullable=True)

    timestamp_seconds = db.Column(db.Integer, nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)

    concert_draft = db.relationship('ConcertDraft', back_populates='setlist_item_drafts')
    piece = db.relationship('Piece')
    raga = db.relationship('Raga')
    talam = db.relationship('Talam')
    composer = db.relationship('Composer')

    __table_args__ = (
        db.UniqueConstraint('concert_draft_id', 'sequence_number', name='unique_concert_draft_sequence'),
    )

class ConcertArtistDraft(db.Model):
    __tablename__ = 'concert_artist_drafts'
    id = db.Column(db.Integer, primary_key=True)
    concert_draft_id = db.Column(db.Integer, db.ForeignKey('concert_drafts.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # only populate if existing artist
    artist_id = db.Column(db.Integer, db.ForeignKey('artists.id', ondelete='SET NULL'), nullable=True, index=True)

    # what the user entered
    artist_name = db.Column(db.String(255), nullable=False)
    instrument = db.Column(db.String(255))
    role = db.Column(db.String(255))  # "main artist" or "accompanist"

    concert_draft = db.relationship('ConcertDraft', back_populates='concert_artist_drafts')
    artist = db.relationship('Artist')


# AUTOMATIC INGESTION

class IngestDraft(db.Model):
    __tablename__ = 'ingest_drafts'
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(255), nullable=False, index=True)
    sequence_number = db.Column(db.Integer)
    timestamp_seconds = db.Column(db.Integer)
    raw_line = db.Column(db.Text, nullable=False)
    parsed_piece = db.Column(db.String(255))
    parsed_raga = db.Column(db.String(255))
    parsed_talam = db.Column(db.String(255))
    parsed_composer = db.Column(db.String(255))
    parsed_kind = db.Column(db.String(50))
    confidence = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='needs_review', index=True)
    resolved_setlist_item_id = db.Column(
        db.Integer, db.ForeignKey('setlist_items.id', ondelete='SET NULL'),
        nullable=True,
    )

    def __repr__(self):
        return f"<IngestDraft {self.id} [{self.status}] {self.parsed_piece}>"


# CLIENT ENDPOINTS - WRITE

_UNUSABLE_META_NAMES = {'unknown', 'none'}


def _prefer_canonical_row(rows):
    """Prefer title-cased / earlier rows when normalized duplicates exist."""
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    def score(row):
        name = row.name or ''
        letters = [c for c in name if c.isalpha()]
        upper = sum(1 for c in letters if c.isupper())
        return (
            1 if name[:1].isupper() else 0,
            upper,
            -len(name),
            -row.id,
        )

    return sorted(rows, key=score, reverse=True)[0]


def _usable_meta_name(name):
    return bool(name) and normalize_for_match(name) not in _UNUSABLE_META_NAMES


def _resolve_named_entity(model, raw_name, lookup_fn=None):
    """Match a parsed name to an existing DB entity via aliases / normalization."""
    if not raw_name:
        return None, None

    target = normalize_for_match(raw_name)
    if not target:
        return None, None

    canon = lookup_fn(raw_name) if lookup_fn else None
    if canon:
        target = normalize_for_match(canon)

    matches = []
    suffix_matches = []
    for row in db.session.scalars(db.select(model)).all():
        if not _usable_meta_name(row.name):
            continue
        norm = normalize_for_match(row.name)
        row_canon = lookup_fn(row.name) if lookup_fn else None
        if norm == target or (canon and row_canon == canon):
            matches.append(row)
        elif norm.endswith(f' {target}'):
            # e.g. parsed "ata" -> unique "Khanda Jati Ata"
            suffix_matches.append(row)

    row = _prefer_canonical_row(matches) or (
        _prefer_canonical_row(suffix_matches) if len(suffix_matches) == 1 else None
    )
    if not row:
        return None, raw_name
    return row.id, row.name


def _resolve_piece(piece_name, raga_id=None):
    """Match a parsed piece name to an existing piece, preferring raga scope."""
    if not piece_name:
        return None

    target = normalize_for_match(piece_name)
    if not target:
        return None

    candidates = []
    for piece in db.session.scalars(
        db.select(Piece).options(
            joinedload(Piece.raga),
            joinedload(Piece.talam),
            joinedload(Piece.composer),
        )
    ).unique().all():
        if normalize_for_match(piece.name) == target:
            candidates.append(piece)

    if not candidates:
        for alias in db.session.scalars(
            db.select(PieceAlias).options(
                joinedload(PieceAlias.piece).joinedload(Piece.raga),
                joinedload(PieceAlias.piece).joinedload(Piece.talam),
                joinedload(PieceAlias.piece).joinedload(Piece.composer),
            )
        ).unique().all():
            if normalize_for_match(alias.alias) == target and alias.piece:
                candidates.append(alias.piece)

    if not candidates:
        return None

    if raga_id is not None:
        scoped = [p for p in candidates if p.raga_id == raga_id]
        if scoped:
            candidates = scoped
        else:
            # Don't link a piece from a different raga when we already know the raga.
            return None

    if len(candidates) == 1:
        return candidates[0]
    return _prefer_canonical_row(candidates)


TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
YOUTUBE_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _valid_optional_string(value, max_length: int) -> bool:
    return value is None or (
        isinstance(value, str) and len(value.strip()) <= max_length
    )


def _is_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_concert_draft_payload(data: dict) -> str | None:
    youtube_id = data.get('youtube_id')
    title = data.get('title')
    year = data.get('year')
    venue = data.get('venue')
    duration_seconds = data.get('duration_seconds')
    artists = data.get('artists')
    setlist = data.get('setlist')

    if not isinstance(youtube_id, str) or not YOUTUBE_ID_PATTERN.fullmatch(
        youtube_id.strip()
    ):
        return "youtube_id must be a valid 11-character YouTube video ID"
    if not isinstance(title, str) or not title.strip():
        return "title is required"
    if len(title.strip()) > 255:
        return "title must be 255 characters or fewer"
    if not _valid_optional_string(venue, 255):
        return "venue must be 255 characters or fewer"
    if year is not None and (
        not _is_integer(year) or year < 1900 or year > 2100
    ):
        return "year must be an integer between 1900 and 2100"
    if duration_seconds is not None and (
        not _is_integer(duration_seconds) or duration_seconds < 0
    ):
        return "duration_seconds must be a non-negative integer"

    if not isinstance(artists, list) or not artists:
        return "at least one artist is required"
    if len(artists) > 50:
        return "no more than 50 artists are allowed"
    for i, artist in enumerate(artists, start=1):
        if not isinstance(artist, dict):
            return f"artist {i}: must be an object"
        name = artist.get('artist_name')
        if not isinstance(name, str) or not name.strip():
            return f"artist {i}: name is required"
        if len(name.strip()) > 255:
            return f"artist {i}: name must be 255 characters or fewer"
        if not _valid_optional_string(artist.get('instrument'), 255):
            return f"artist {i}: instrument must be 255 characters or fewer"
        if not _valid_optional_string(artist.get('role'), 255):
            return f"artist {i}: role must be 255 characters or fewer"

    if not isinstance(setlist, list) or not setlist:
        return "at least one setlist item is required"
    if len(setlist) > 200:
        return "no more than 200 setlist items are allowed"

    sequence_numbers = set()
    for i, item in enumerate(setlist, start=1):
        if not isinstance(item, dict):
            return f"setlist item {i}: must be an object"
        piece_name = item.get('piece_name')
        if not isinstance(piece_name, str) or not piece_name.strip():
            return f"setlist item {i}: piece name is required"
        if len(piece_name.strip()) > 255:
            return f"setlist item {i}: piece name must be 255 characters or fewer"
        for field in ('raga_name', 'talam_name', 'composer_name'):
            if not _valid_optional_string(item.get(field), 255):
                return f"setlist item {i}: {field} must be 255 characters or fewer"
        if not _valid_optional_string(item.get('kind'), 50):
            return f"setlist item {i}: kind must be 50 characters or fewer"

        timestamp = item.get('timestamp_seconds')
        if not _is_integer(timestamp) or timestamp < 0:
            return f"setlist item {i}: timestamp must be a non-negative integer"
        sequence = item.get('sequence_number')
        if not _is_integer(sequence) or sequence < 1:
            return f"setlist item {i}: sequence must be a positive integer"
        if sequence in sequence_numbers:
            return f"setlist item {i}: duplicate sequence number"
        sequence_numbers.add(sequence)

    return None


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """Verify a Cloudflare Turnstile token. Skip only when disabled outside production."""
    if os.getenv('TURNSTILE_DISABLED') == '1' and not IS_PRODUCTION:
        return True

    secret = os.getenv('TURNSTILE_SECRET_KEY')
    if not secret or not token:
        return False

    payload = {'secret': secret, 'response': token}
    if remote_ip:
        payload['remoteip'] = remote_ip

    try:
        response = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=5)
        response.raise_for_status()
        return bool(response.json().get('success'))
    except requests.RequestException:
        return False


@app.route('/contributions/parse_setlist', methods=['POST'])
@limiter.limit("20 per hour")
def parse_contribution_setlist():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    description = data.get('description')
    if not isinstance(description, str) or not description.strip():
        return jsonify({"error": "description is required"}), 400
    if len(description) > 100_000:
        return jsonify({"error": "description is too long"}), 400

    parsed_lines = parse_description(description)
    setlist = []
    for line in parsed_lines:
        if line.timestamp_seconds is None or not line.piece_name:
            continue

        raga_id, raga_name = _resolve_named_entity(Raga, line.raga, lookup_raga)
        talam_id, talam_name = _resolve_named_entity(Talam, line.talam, lookup_talam)
        composer_id, composer_name = _resolve_named_entity(Composer, line.composer, lookup_composer)

        piece = _resolve_piece(line.piece_name, raga_id=raga_id)
        piece_id = piece.id if piece else None
        piece_name = piece.name if piece else line.piece_name

        # If the piece is linked, fill any still-unresolved metadata from it.
        if piece:
            if raga_id is None and piece.raga and _usable_meta_name(piece.raga.name):
                raga_id = piece.raga_id
                raga_name = piece.raga.name
            if talam_id is None and piece.talam and _usable_meta_name(piece.talam.name):
                talam_id = piece.talam_id
                talam_name = piece.talam.name
            if composer_id is None and piece.composer and _usable_meta_name(piece.composer.name):
                composer_id = piece.composer_id
                composer_name = piece.composer.name

        setlist.append({
            "sequence_number": len(setlist) + 1,
            "timestamp_seconds": line.timestamp_seconds,
            "piece_id": piece_id,
            "piece_name": piece_name,
            "raga_id": raga_id,
            "raga_name": raga_name,
            "talam_id": talam_id,
            "talam_name": talam_name,
            "composer_id": composer_id,
            "composer_name": composer_name,
            "kind": (line.kind or (piece.kind if piece else None) or '').lower() or None,
        })

    if not setlist:
        return jsonify({
            "error": "No setlist entries with both a timestamp and piece name were found"
        }), 422

    return jsonify({"setlist": setlist})


@app.route('/contributions/create_concert_draft', methods=['POST'])
@limiter.limit("5 per hour")
def create_concert_draft():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    if data.get('website'):
        return jsonify({"id": 0, "status": "submitted"}), 201

    token_value = data.get('cf-turnstile-response')
    token = token_value.strip() if isinstance(token_value, str) else ''
    remote_ip = request.remote_addr
    if not verify_turnstile(token, remote_ip):
        return jsonify({"error": "Captcha verification failed"}), 403

    validation_error = validate_concert_draft_payload(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    youtube_id = data['youtube_id'].strip()
    title = data['title'].strip()
    year = data.get('year')
    venue = data.get('venue')
    venue = venue.strip() if venue else None
    duration_seconds = data.get('duration_seconds')
    artists = data['artists']
    setlist = data['setlist']

    existing_concert = db.session.scalar(
        db.select(Concert.id).where(Concert.youtube_id == youtube_id)
    )
    existing_draft = db.session.scalar(
        db.select(ConcertDraft.id).where(
            ConcertDraft.youtube_id == youtube_id,
            ConcertDraft.status == 'submitted',
        )
    )
    if existing_concert or existing_draft:
        return jsonify({
            "error": "A concert or submitted draft already exists for this YouTube video"
        }), 409

    try:
        concert_draft = ConcertDraft(
            youtube_id=youtube_id,
            title=title,
            year=year,
            venue=venue,
            duration_seconds=duration_seconds,
            status='submitted',
        )
        db.session.add(concert_draft)
        db.session.flush()

        for artist in artists:
            concert_artist_draft = ConcertArtistDraft(
                concert_draft_id=concert_draft.id,
                artist_id=artist.get('artist_id') or None,
                artist_name=artist.get('artist_name').strip(),
                instrument=(artist.get('instrument') or '').strip() or None,
                role=(artist.get('role') or '').strip() or None,
            )
            db.session.add(concert_artist_draft)

        for setlist_item in setlist:
            setlist_item_draft = SetlistItemDraft(
                concert_draft_id=concert_draft.id,
                piece_id=setlist_item.get('piece_id') or None,
                raga_id=setlist_item.get('raga_id') or None,
                talam_id=setlist_item.get('talam_id') or None,
                composer_id=setlist_item.get('composer_id') or None,
                piece_name=setlist_item.get('piece_name').strip(),
                raga_name=(setlist_item.get('raga_name') or '').strip() or None,
                talam_name=(setlist_item.get('talam_name') or '').strip() or None,
                composer_name=(setlist_item.get('composer_name') or '').strip() or None,
                kind=(setlist_item.get('kind') or '').strip() or None,
                timestamp_seconds=setlist_item.get('timestamp_seconds'),
                sequence_number=setlist_item.get('sequence_number'),
            )
            db.session.add(setlist_item_draft)

        db.session.commit()
        return jsonify({"id": concert_draft.id, "status": concert_draft.status}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

# CLIENT ENDPOINTS - READ

# Autocomplete Piece Names
@app.route('/pieces/autocomplete/<string:prefix>', methods=['GET'])
@limiter.limit("120 per minute")
def autocomplete_pieces(prefix: str):
    rows = db.session.scalars(
        db.select(Piece)
        .options(
            joinedload(Piece.raga),
            joinedload(Piece.talam),
            joinedload(Piece.composer),
        )
        .where(Piece.name.ilike(f"{prefix}%"))
        .order_by(Piece.name)
        .limit(10)
    ).unique().all()
    return jsonify([
        {
            "id": p.id,
            "name": p.name,
            "raga_id": p.raga_id,
            "raga": p.raga.name if p.raga else None,
            "talam_id": p.talam_id,
            "talam": p.talam.name if p.talam else None,
            "composer_id": p.composer_id,
            "composer": p.composer.name if p.composer else None,
        }
        for p in rows
    ])

# Autocomplete Artist Names
@app.route('/artists/autocomplete/<string:prefix>', methods=['GET'])
@limiter.limit("120 per minute")
def autocomplete_artists(prefix: str):
    rows = db.session.scalars(
        db.select(Artist)
        .where(Artist.name.ilike(f"{prefix}%"))
        .order_by(Artist.name)
        .limit(10)
    ).all()
    return jsonify([
        {
            "id": a.id,
            "name": a.name,
        }
        for a in rows
    ])

# Autocomplete Raga Names
@app.route('/ragas/autocomplete/<string:prefix>', methods=['GET'])
@limiter.limit("120 per minute")
def autocomplete_ragas(prefix: str):
    rows = db.session.scalars(
        db.select(Raga)
        .where(Raga.name.ilike(f"{prefix}%"))
        .order_by(Raga.name)
        .limit(10)
    ).all()
    return jsonify([
        {
            "id": r.id,
            "name": r.name,
        }
        for r in rows
    ])

# Autocomplete Talam Names
@app.route('/talams/autocomplete/<string:prefix>', methods=['GET'])
@limiter.limit("120 per minute")
def autocomplete_talams(prefix: str):
    rows = db.session.scalars(
        db.select(Talam)
        .where(Talam.name.ilike(f"{prefix}%"))
        .order_by(Talam.name)
        .limit(10)
    ).all()
    return jsonify([
        {
            "id": t.id,
            "name": t.name,
        }
        for t in rows
    ])

# Autocomplete Composer Names
@app.route('/composers/autocomplete/<string:prefix>', methods=['GET'])
@limiter.limit("120 per minute")
def autocomplete_composers(prefix: str):
    rows = db.session.scalars(
        db.select(Composer)
        .where(Composer.name.ilike(f"{prefix}%"))
        .order_by(Composer.name)
        .limit(10)
    ).all()
    return jsonify([
        {
            "id": c.id,
            "name": c.name,
        }
        for c in rows
    ])

# Find renditions of a piece
@app.route('/pieces/get-setlist/<string:piece_name>', methods=['GET'])
@limiter.limit("30 per minute")
def get_setlist(piece_name: str):
    rows = db.session.execute(
        db.select(SetlistItem, Piece, Concert)
        .join(Piece, SetlistItem.piece_id == Piece.id)
        .join(Concert, SetlistItem.concert_id == Concert.id)
        .where(Piece.name == piece_name)
    ).all()

    concert_ids = {c.id for _, _, c in rows}
    next_ts_by_item = {}
    if concert_ids:
        concert_items = db.session.scalars(
            db.select(SetlistItem)
            .where(SetlistItem.concert_id.in_(concert_ids))
            .order_by(SetlistItem.concert_id, SetlistItem.sequence_number)
        ).all()
        by_concert = {}
        for item in concert_items:
            by_concert.setdefault(item.concert_id, []).append(item)
        for items in by_concert.values():
            for i, item in enumerate(items):
                if i + 1 < len(items):
                    next_ts_by_item[item.id] = items[i + 1].timestamp_seconds

    results = []
    for si, p, c in rows:
        next_ts = next_ts_by_item.get(si.id, c.duration_seconds)
        duration = None
        if next_ts is not None and si.timestamp_seconds is not None:
            delta = next_ts - si.timestamp_seconds
            if delta > 0:
                duration = delta
        results.append({
            "piece_id": p.id,
            "piece_name": p.name,
            "raga": p.raga.name if p.raga else None,
            "talam": p.talam.name if p.talam else None,
            "composer": p.composer.name if p.composer else None,
            "concert_id": c.id,
            "concert_title": c.title,
            "concert_year": c.year,
            "concert_venue": c.venue,
            "track_url": f"https://www.youtube.com/watch?v={c.youtube_id}&t={si.timestamp_seconds}",
            "timestamp_seconds": si.timestamp_seconds,
            "duration_seconds": duration,
            "sequence_number": si.sequence_number,
        })
    return jsonify(results)

# Find concerts by main artist name
@app.route('/concerts/find/<string:main_artist>', methods=['GET'])
@limiter.limit("30 per minute")
def find_concerts(main_artist: str):
   rows = db.session.execute(
        db.select(Concert)
        .join(Concert.concert_artists)
        .join(ConcertArtist.artist)
        .where(ConcertArtist.role == 'main artist')
        .where(Artist.name == main_artist)
        .order_by(Concert.year)
   ).scalars().all()
   return jsonify([
        {
            "id": c.id,
            "title": c.title,
            "year": c.year,
            "venue": c.venue,
            "url": f"https://www.youtube.com/watch?v={c.youtube_id}",
        }
        for c in rows
    ])

# Get concert metadata by id
@app.route('/concerts/get-metadata/<int:concert_id>', methods=['GET'])
@limiter.limit("60 per minute")
def get_concert_metadata(concert_id: int):
    row = db.session.get(Concert, concert_id)
    if row is None:
        return jsonify({"error": "Concert not found"}), 404
    return jsonify({
        "id": row.id,
        "title": row.title,
        "year": row.year,
        "venue": row.venue,
        "url": f"https://www.youtube.com/watch?v={row.youtube_id}",
        "duration_seconds": row.duration_seconds,
    })

# View setlist for a concert
@app.route('/concerts/setlist/<int:concert_id>', methods=['GET'])
@limiter.limit("60 per minute")
def view_setlist(concert_id: int):
    rows = db.session.execute(
        db.select(SetlistItem, Piece)
        .outerjoin(Piece, SetlistItem.piece_id == Piece.id)
        .where(SetlistItem.concert_id == concert_id)
        .order_by(SetlistItem.sequence_number)
    ).all()
    return jsonify([
        {
            "sequence_number": si.sequence_number,
            "timestamp_seconds": si.timestamp_seconds,
            "id": p.id if p else None,
            "name": p.name if p else None,
            "raga": p.raga.name if p and p.raga else None,
            "composer": p.composer.name if p and p.composer else None,
            "talam": p.talam.name if p and p.talam else None,
        }
        for si, p in rows
    ])

# Get the artists for a concert
@app.route('/concerts/get-artists/<int:concert_id>', methods=['GET'])
@limiter.limit("60 per minute")
def get_concert_artists(concert_id: int):
    rows = db.session.execute(
        db.select(ConcertArtist, Artist)
        .join(Artist, ConcertArtist.artist_id == Artist.id)
        .where(ConcertArtist.concert_id == concert_id)
        .order_by(
            db.case((ConcertArtist.role == 'main artist', 0), else_=1),
            Artist.name,
        )
    ).all()
    return jsonify([
        {
            "id": a.id,
            "name": a.name,
            "instrument": ca.instrument,
            "role": ca.role,
        }
        for ca, a in rows
    ])

@app.route('/')
def index():
    return render_template(
        'index.html',
        turnstile_site_key=os.getenv('TURNSTILE_SITE_KEY', ''),
        turnstile_disabled=os.getenv('TURNSTILE_DISABLED') == '1',
    )


# TEST ENDPOINTS

@app.route('/concerts/view', methods=['GET'])
def view_concerts():
    concerts = db.session.execute(db.select(Concert).limit(3)).scalars().all()
    return jsonify([
        {
            "id": c.id,
            "title": c.title,
            "year": c.year,
            "venue": c.venue,
        }
        for c in concerts
    ])

    
# Register review blueprint
from review import review_bp  # noqa: E402
app.register_blueprint(review_bp)

if IS_PRODUCTION:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

if __name__ == '__main__':
    app.run(debug=not IS_PRODUCTION)