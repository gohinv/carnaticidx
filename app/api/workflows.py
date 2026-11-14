"""Workflow routes that compose repo calls in one transaction.

Public:
  POST /workflows/parse-setlist
  POST /workflows/submit-contribution

Admin:
  POST /workflows/approve-concert-draft/<id>
  POST /workflows/resolve-ingest-draft/<id>
  POST /workflows/replace-concert-lineup/<concert_id>
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests
from flask import jsonify, request
from sqlalchemy import func
from sqlalchemy.orm import joinedload

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingest.description_parser import parse_description  # noqa: E402
from ingest.populate_db import (  # noqa: E402
    PHONETIC_MIN_LEN,
    CatalogLookups,
    lookup_composer,
    lookup_raga,
    lookup_talam,
    normalize_for_match,
    phonetic_key,
)
from api.auth import require_admin  # noqa: E402
from api.crud import row_to_dict  # noqa: E402
from dbmodel import (  # noqa: E402
    db,
    Artist,
    Composer,
    Piece,
    PieceAlias,
    Raga,
    Talam,
)
from repo import (  # noqa: E402
    ConflictError,
    artists,
    composers,
    concert_artist_drafts,
    concert_artists,
    concert_drafts,
    concerts,
    ingest_drafts,
    normalize_name,
    piece_aliases,
    pieces,
    ragas,
    setlist_item_drafts,
    setlist_items,
    talams,
)

_UNUSABLE_META_NAMES = {"unknown", "none"}
ALLOWED_ARTIST_ROLES = frozenset({"main artist", "accompanist"})
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")

_REPOS_BY_MODEL = {
    Artist: artists,
    Raga: ragas,
    Talam: talams,
    Composer: composers,
}


class WorkflowError(Exception):
    """A workflow failure with an HTTP status and JSON ``error`` message."""

    def __init__(self, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


def register_workflows(app, limiter):
    """Attach workflow routes. Public routes keep their previous rate limits."""
    app.add_url_rule(
        "/workflows/parse-setlist",
        endpoint="workflow_parse_setlist",
        view_func=limiter.limit("20 per hour")(parse_setlist),
        methods=["POST"],
        strict_slashes=False,
    )
    app.add_url_rule(
        "/workflows/submit-contribution",
        endpoint="workflow_submit_contribution",
        view_func=limiter.limit("5 per hour")(submit_contribution),
        methods=["POST"],
        strict_slashes=False,
    )
    app.add_url_rule(
        "/workflows/approve-concert-draft/<int:draft_id>",
        endpoint="workflow_approve_concert_draft",
        view_func=require_admin(approve_concert_draft),
        methods=["POST"],
        strict_slashes=False,
    )
    app.add_url_rule(
        "/workflows/resolve-ingest-draft/<int:draft_id>",
        endpoint="workflow_resolve_ingest_draft",
        view_func=require_admin(resolve_ingest_draft),
        methods=["POST"],
        strict_slashes=False,
    )
    app.add_url_rule(
        "/workflows/replace-concert-lineup/<int:concert_id>",
        endpoint="workflow_replace_concert_lineup",
        view_func=require_admin(replace_concert_lineup),
        methods=["POST"],
        strict_slashes=False,
    )


def parse_setlist():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        return jsonify({"error": "description is required"}), 400
    if len(description) > 100_000:
        return jsonify({"error": "description is too long"}), 400

    parsed_lines = parse_description(description, _load_catalog_lookups())
    setlist = []
    for line in parsed_lines:
        if line.timestamp_seconds is None or not line.piece_name:
            continue

        raga_id, raga_name = _resolve_named_entity(Raga, line.raga, lookup_raga)
        talam_id, talam_name = _resolve_named_entity(Talam, line.talam, lookup_talam)
        composer_id, composer_name = _resolve_named_entity(
            Composer, line.composer, lookup_composer
        )

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
            "kind": _setlist_kind(line, piece, raga_name, composer_name),
        })

    if not setlist:
        return jsonify({
            "error": "No setlist entries with both a timestamp and piece name were found"
        }), 422

    return jsonify({"setlist": setlist})


def submit_contribution():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    if data.get("website"):
        return jsonify({"id": 0, "status": "submitted"}), 201

    token_value = data.get("cf-turnstile-response")
    token = token_value.strip() if isinstance(token_value, str) else ""
    remote_ip = request.remote_addr
    if not verify_turnstile(token, remote_ip):
        return jsonify({"error": "Captcha verification failed"}), 403

    validation_error = validate_concert_draft_payload(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    youtube_id = data["youtube_id"].strip()
    title = data["title"].strip()
    year = data.get("year")
    venue = data.get("venue")
    venue = venue.strip() if venue else None
    duration_seconds = data.get("duration_seconds")
    artist_rows = data["artists"]
    setlist = data["setlist"]

    if concerts.list({"youtube_id": [youtube_id]}, limit=1) or concert_drafts.list(
        {"youtube_id": [youtube_id], "status": ["submitted"]},
        limit=1,
    ):
        return jsonify({
            "error": "A concert or submitted draft already exists for this YouTube video"
        }), 409

    try:
        concert_draft = concert_drafts.create(
            commit=False,
            youtube_id=youtube_id,
            title=title,
            year=year,
            venue=venue,
            duration_seconds=duration_seconds,
            status="submitted",
        )
        for artist in artist_rows:
            concert_artist_drafts.create(
                commit=False,
                concert_draft_id=concert_draft.id,
                artist_id=artist.get("artist_id") or None,
                artist_name=artist.get("artist_name").strip(),
                instrument=(artist.get("instrument") or "").strip() or None,
                role=(artist.get("role") or "").strip() or None,
            )
        for setlist_item in setlist:
            setlist_item_drafts.create(
                commit=False,
                concert_draft_id=concert_draft.id,
                piece_id=setlist_item.get("piece_id") or None,
                raga_id=setlist_item.get("raga_id") or None,
                talam_id=setlist_item.get("talam_id") or None,
                composer_id=setlist_item.get("composer_id") or None,
                piece_name=setlist_item.get("piece_name").strip(),
                raga_name=(setlist_item.get("raga_name") or "").strip() or None,
                talam_name=(setlist_item.get("talam_name") or "").strip() or None,
                composer_name=(setlist_item.get("composer_name") or "").strip() or None,
                kind=(setlist_item.get("kind") or "").strip() or None,
                timestamp_seconds=setlist_item.get("timestamp_seconds"),
                sequence_number=setlist_item.get("sequence_number"),
            )
        draft_id = concert_draft.id
        status = concert_draft.status
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"id": draft_id, "status": status}), 201


def approve_concert_draft(draft_id: int):
    found = concert_drafts.get_many([draft_id])
    if not found:
        return jsonify({"error": "Not found"}), 404
    draft = found[0]
    if draft.status != "submitted":
        return jsonify({
            "error": (
                "Only submitted drafts can be approved; "
                f"status is {draft.status!r}"
            ),
        }), 409

    existing = concerts.list({"youtube_id": [draft.youtube_id]}, limit=1)
    if existing:
        return jsonify({
            "error": "A concert with this YouTube ID already exists",
            "concert_id": existing[0].id,
        }), 409

    if not draft.concert_artist_drafts:
        return jsonify({"error": "Draft has no artists"}), 422
    if not draft.setlist_item_drafts:
        return jsonify({"error": "Draft has no setlist items"}), 422

    try:
        concert = _publish_concert_draft(draft)
        concert_body = row_to_dict(concert)
        concert_body["url"] = (
            f"https://www.youtube.com/watch?v={concert.youtube_id}"
        )
        body = {
            "draft_id": draft.id,
            "status": "approved",
            "concert": concert_body,
        }
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify(body), 201


def resolve_ingest_draft(draft_id: int):
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        payload = _resolve_ingest_draft(draft_id, data)
        db.session.commit()
    except WorkflowError as exc:
        db.session.rollback()
        return _error_response(exc)
    except ConflictError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 409
    except Exception:
        db.session.rollback()
        raise
    return jsonify(payload)


def replace_concert_lineup(concert_id: int):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        created = _replace_concert_lineup(concert_id, data.get("artists"))
        payload = [row_to_dict(row) for row in created]
        db.session.commit()
    except WorkflowError as exc:
        db.session.rollback()
        return _error_response(exc)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


def validate_concert_draft_payload(data: dict) -> str | None:
    youtube_id = data.get("youtube_id")
    title = data.get("title")
    year = data.get("year")
    venue = data.get("venue")
    duration_seconds = data.get("duration_seconds")
    artist_rows = data.get("artists")
    setlist = data.get("setlist")

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

    if not isinstance(artist_rows, list) or not artist_rows:
        return "at least one artist is required"
    if len(artist_rows) > 50:
        return "no more than 50 artists are allowed"
    for i, artist in enumerate(artist_rows, start=1):
        if not isinstance(artist, dict):
            return f"artist {i}: must be an object"
        name = artist.get("artist_name")
        if not isinstance(name, str) or not name.strip():
            return f"artist {i}: name is required"
        if len(name.strip()) > 255:
            return f"artist {i}: name must be 255 characters or fewer"
        if not _valid_optional_string(artist.get("instrument"), 255):
            return f"artist {i}: instrument must be 255 characters or fewer"
        if not _valid_optional_string(artist.get("role"), 255):
            return f"artist {i}: role must be 255 characters or fewer"

    if not isinstance(setlist, list) or not setlist:
        return "at least one setlist item is required"
    if len(setlist) > 200:
        return "no more than 200 setlist items are allowed"

    sequence_numbers = set()
    for i, item in enumerate(setlist, start=1):
        if not isinstance(item, dict):
            return f"setlist item {i}: must be an object"
        piece_name = item.get("piece_name")
        if not isinstance(piece_name, str) or not piece_name.strip():
            return f"setlist item {i}: piece name is required"
        if len(piece_name.strip()) > 255:
            return f"setlist item {i}: piece name must be 255 characters or fewer"
        for field in ("raga_name", "talam_name", "composer_name"):
            if not _valid_optional_string(item.get(field), 255):
                return f"setlist item {i}: {field} must be 255 characters or fewer"
        if not _valid_optional_string(item.get("kind"), 50):
            return f"setlist item {i}: kind must be 50 characters or fewer"

        timestamp = item.get("timestamp_seconds")
        if not _is_integer(timestamp) or timestamp < 0:
            return f"setlist item {i}: timestamp must be a non-negative integer"
        sequence = item.get("sequence_number")
        if not _is_integer(sequence) or sequence < 1:
            return f"setlist item {i}: sequence must be a positive integer"
        if sequence in sequence_numbers:
            return f"setlist item {i}: duplicate sequence number"
        sequence_numbers.add(sequence)

    return None


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """Verify a Cloudflare Turnstile token. Skip only when disabled outside production."""
    is_production = os.getenv("FLASK_ENV") == "production"
    if os.getenv("TURNSTILE_DISABLED") == "1" and not is_production:
        return True

    secret = os.getenv("TURNSTILE_SECRET_KEY")
    if not secret or not token:
        return False

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        response = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=5)
        response.raise_for_status()
        return bool(response.json().get("success"))
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_response(exc: WorkflowError):
    return jsonify({"error": exc.message, **exc.extra}), exc.status


def _prefer_canonical_row(rows):
    """Prefer title-cased / earlier rows when normalized duplicates exist."""
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    def score(row):
        name = row.name or ""
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

    target_key = phonetic_key(target)

    matches = []
    suffix_matches = []
    phonetic_matches = []
    for row in db.session.scalars(db.select(model)).all():
        if not _usable_meta_name(row.name):
            continue
        norm = normalize_for_match(row.name)
        row_canon = lookup_fn(row.name) if lookup_fn else None
        if norm == target or (canon and row_canon == canon):
            matches.append(row)
        elif norm.endswith(f" {target}"):
            # e.g. parsed "ata" -> unique "Khanda Jati Ata"
            suffix_matches.append(row)
        elif len(target_key) >= PHONETIC_MIN_LEN and phonetic_key(norm) == target_key:
            # spelling variant, e.g. parsed "Muthuswamy" -> "Muthuswami"
            phonetic_matches.append(row)

    row = _prefer_canonical_row(matches) or (
        _prefer_canonical_row(suffix_matches) if len(suffix_matches) == 1 else None
    )
    if not row and phonetic_matches:
        # Only trust a spelling match when every candidate is the same name.
        if len({normalize_for_match(r.name) for r in phonetic_matches}) == 1:
            row = _prefer_canonical_row(phonetic_matches)
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

    pieces_rows = db.session.scalars(
        db.select(Piece).options(
            joinedload(Piece.raga),
            joinedload(Piece.talam),
            joinedload(Piece.composer),
        )
    ).unique().all()
    aliases = None

    def load_aliases():
        return db.session.scalars(
            db.select(PieceAlias).options(
                joinedload(PieceAlias.piece).joinedload(Piece.raga),
                joinedload(PieceAlias.piece).joinedload(Piece.talam),
                joinedload(PieceAlias.piece).joinedload(Piece.composer),
            )
        ).unique().all()

    candidates = [p for p in pieces_rows if normalize_for_match(p.name) == target]

    if not candidates:
        aliases = load_aliases()
        candidates = [
            a.piece for a in aliases
            if a.piece and normalize_for_match(a.alias) == target
        ]

    # Last resort: a unique transliteration variant of an existing piece name
    # or alias (e.g. "Thyagaraja" vs "Tyagaraja" style spelling differences).
    phonetic = False
    if not candidates:
        target_key = phonetic_key(target)
        if len(target_key) >= PHONETIC_MIN_LEN:
            phonetic = True
            candidates = [
                p for p in pieces_rows if phonetic_key(p.name) == target_key
            ]
            if not candidates:
                candidates = [
                    a.piece for a in aliases
                    if a.piece and phonetic_key(a.alias) == target_key
                ]

    if not candidates:
        return None

    if raga_id is not None:
        scoped = [p for p in candidates if p.raga_id == raga_id]
        if scoped:
            candidates = scoped
        else:
            # Don't link a piece from a different raga when we already know the raga.
            return None

    if phonetic and len({normalize_for_match(p.name) for p in candidates}) > 1:
        # Several differently-spelled pieces share this key; don't guess.
        return None

    if len(candidates) == 1:
        return candidates[0]
    return _prefer_canonical_row(candidates)


def _load_catalog_lookups():
    """Raga/talam/composer names from the database, for recognizing parsed tokens."""
    def names(model):
        return [
            name for name in db.session.scalars(db.select(model.name)).all()
            if _usable_meta_name(name)
        ]

    return CatalogLookups(
        ragas=names(Raga),
        talams=names(Talam),
        composers=names(Composer),
    )


def _setlist_kind(line, piece, raga_name, composer_name):
    """Kind from the line, else the linked piece, else krithi for a full raga + composer entry."""
    kind = line.kind or (piece.kind if piece else None)
    if not kind and raga_name and composer_name:
        kind = "krithi"
    return (kind or "").lower() or None


def _valid_optional_string(value, max_length: int) -> bool:
    return value is None or (
        isinstance(value, str) and len(value.strip()) <= max_length
    )


def _is_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _get_or_create(repo, name: str):
    """Exact-name lookup, then insert. ``name`` is not passed through list filters."""
    row = (
        db.session.query(repo.model)
        .filter_by(name=name)
        .order_by(repo.model.id)
        .first()
    )
    if row:
        return row, False
    return repo.create(commit=False, name=name), True


def _promote_named_draft_reference(
    model,
    entity_id,
    submitted_name,
    label,
    *,
    required=False,
):
    """Reuse a selected catalog row, or create the contributor's new named row."""
    repo = _REPOS_BY_MODEL[model]
    if entity_id:
        row = db.session.get(model, entity_id)
        if not row:
            raise ValueError(f"{label}_id {entity_id} does not exist")
        return row

    name = (submitted_name or "").strip()
    if not name:
        if required:
            raise ValueError(f"{label} name is required")
        return None

    row = (
        db.session.query(model)
        .filter(func.lower(model.name) == name.lower())
        .order_by(model.id)
        .first()
    )
    if row:
        return row
    return repo.create(commit=False, name=name)


def _promote_draft_piece(item_draft, *, raga_id, talam_id, composer_id):
    """Create a new contributed piece, reusing an exact catalog match if present."""
    name = (item_draft.piece_name or "").strip()
    if not name:
        raise ValueError(f"setlist item {item_draft.id}: piece name is required")

    query = db.session.query(Piece).filter(
        func.lower(Piece.name) == name.lower(),
        Piece.raga_id == raga_id,
        Piece.talam_id == talam_id,
        Piece.composer_id == composer_id,
    )
    if item_draft.kind:
        query = query.filter(func.lower(Piece.kind) == item_draft.kind.lower())
    else:
        query = query.filter(Piece.kind.is_(None))

    piece = query.order_by(Piece.id).first()
    if piece:
        return piece

    return pieces.create(
        commit=False,
        name=name,
        kind=item_draft.kind,
        raga_id=raga_id,
        talam_id=talam_id,
        composer_id=composer_id,
    )


def _publish_concert_draft(draft):
    concert = concerts.create(
        commit=False,
        youtube_id=draft.youtube_id,
        title=draft.title,
        year=draft.year,
        venue=draft.venue,
        duration_seconds=draft.duration_seconds,
    )
    for artist_draft in draft.concert_artist_drafts:
        artist = _promote_named_draft_reference(
            Artist,
            artist_draft.artist_id,
            artist_draft.artist_name,
            "artist",
            required=True,
        )
        concert_artist_drafts.update(
            artist_draft.id,
            commit=False,
            artist_id=artist.id,
        )
        concert_artists.create(
            commit=False,
            concert_id=concert.id,
            artist_id=artist.id,
            instrument=artist_draft.instrument,
            role=artist_draft.role,
        )

    for item_draft in draft.setlist_item_drafts:
        piece = None
        if item_draft.piece_id:
            found = pieces.get_many([item_draft.piece_id])
            if not found:
                raise ValueError(
                    f"setlist item {item_draft.id}: piece_id "
                    f"{item_draft.piece_id} does not exist"
                )
            piece = found[0]

        if not piece:
            raga = _promote_named_draft_reference(
                Raga, item_draft.raga_id, item_draft.raga_name, "raga",
            )
            talam = _promote_named_draft_reference(
                Talam, item_draft.talam_id, item_draft.talam_name, "talam",
            )
            composer = _promote_named_draft_reference(
                Composer, item_draft.composer_id,
                item_draft.composer_name, "composer",
            )
            piece = _promote_draft_piece(
                item_draft,
                raga_id=raga.id if raga else None,
                talam_id=talam.id if talam else None,
                composer_id=composer.id if composer else None,
            )
            setlist_item_drafts.update(
                item_draft.id,
                commit=False,
                piece_id=piece.id,
                raga_id=raga.id if raga else None,
                talam_id=talam.id if talam else None,
                composer_id=composer.id if composer else None,
            )

        setlist_items.create(
            commit=False,
            concert_id=concert.id,
            piece_id=piece.id,
            timestamp_seconds=item_draft.timestamp_seconds,
            sequence_number=item_draft.sequence_number,
        )

    concert_drafts.update(draft.id, commit=False, status="approved")
    return concert


def _resolve_ingest_draft(draft_id: int, data: dict) -> dict:
    found = ingest_drafts.get_many([draft_id])
    if not found:
        raise WorkflowError("Not found", 404)
    draft = found[0]
    if draft.status != "needs_review":
        raise WorkflowError(
            f"Draft already has status={draft.status!r}",
            400,
        )

    concert_rows = concerts.list({"youtube_id": [draft.youtube_id]}, limit=1)
    if not concert_rows:
        raise WorkflowError("Concert not found for this draft", 404)
    concert = concert_rows[0]

    piece_id = data.get("piece_id")
    piece_name = data.get("piece_name") or draft.parsed_piece
    raga_name = data.get("raga") or draft.parsed_raga
    composer_name = data.get("composer") or draft.parsed_composer
    talam_name = data.get("talam") or draft.parsed_talam
    kind = data.get("kind") or draft.parsed_kind

    piece = None
    if piece_id:
        matched = pieces.get_many([piece_id])
        if not matched:
            raise WorkflowError("piece_id not found", 400)
        piece = matched[0]
    elif piece_name:
        raga_row = None
        if raga_name:
            raga_row = (
                db.session.query(Raga).filter_by(name=raga_name).first()
            )
        composer_row = None
        if composer_name:
            composer_row, _ = _get_or_create(composers, composer_name)
        talam_row = None
        if talam_name:
            talam_row, _ = _get_or_create(talams, talam_name)
        if not raga_row and raga_name:
            raga_row, _ = _get_or_create(ragas, raga_name)

        norm = normalize_name(piece_name)
        match = None

        # Try raga-scoped exact match first, then cross-raga.
        for scoped in ([raga_row.id] if raga_row else []) + [None]:
            query = db.session.query(Piece).filter(Piece.name == piece_name)
            if scoped is not None:
                query = query.filter(Piece.raga_id == scoped)
            match = query.first()
            if match:
                break
            candidates = db.session.query(Piece)
            if scoped is not None:
                candidates = candidates.filter(Piece.raga_id == scoped)
            for candidate in candidates.all():
                if normalize_name(candidate.name) == norm:
                    match = candidate
                    break
            if match:
                break
            fuzzy = db.session.query(Piece).filter(
                func.similarity(Piece.name, norm) > 0.4
            ).order_by(func.similarity(Piece.name, norm).desc())
            if scoped is not None:
                fuzzy = fuzzy.filter(Piece.raga_id == scoped)
            match = fuzzy.first()
            if match:
                break

        if match:
            piece = match
            if normalize_name(piece_name) != normalize_name(piece.name):
                exists = any(
                    normalize_name(alias.alias) == normalize_name(piece_name)
                    for alias in piece.aliases
                )
                if not exists:
                    piece_aliases.create(
                        commit=False,
                        piece_id=piece.id,
                        alias=piece_name,
                    )
            updates = {}
            if raga_row and piece.raga_id is None:
                updates["raga_id"] = raga_row.id
            if composer_row and piece.composer_id is None:
                updates["composer_id"] = composer_row.id
            if talam_row and piece.talam_id is None:
                updates["talam_id"] = talam_row.id
            if kind and piece.kind is None:
                updates["kind"] = kind
            if updates:
                piece = pieces.update(piece.id, commit=False, **updates)
        else:
            piece = pieces.create(
                commit=False,
                name=piece_name,
                raga_id=raga_row.id if raga_row else None,
                composer_id=composer_row.id if composer_row else None,
                talam_id=talam_row.id if talam_row else None,
                kind=kind,
            )
    else:
        raise WorkflowError("Provide piece_id or piece_name", 400)

    seq = draft.sequence_number
    if seq is None:
        raise WorkflowError("Draft has no sequence_number", 400)

    existing_items = setlist_items.list(
        {
            "concert_id": [str(concert.id)],
            "sequence_number": [str(seq)],
        },
        limit=1,
    )
    if existing_items:
        fields = {"piece_id": piece.id}
        if draft.timestamp_seconds is not None:
            fields["timestamp_seconds"] = draft.timestamp_seconds
        setlist_item = setlist_items.update(
            existing_items[0].id,
            commit=False,
            **fields,
        )
    else:
        setlist_item = setlist_items.create(
            commit=False,
            concert_id=concert.id,
            piece_id=piece.id,
            timestamp_seconds=draft.timestamp_seconds or 0,
            sequence_number=seq,
        )

    ingest_drafts.update(
        draft.id,
        commit=False,
        status="resolved",
        resolved_setlist_item_id=setlist_item.id,
    )
    return {
        "draft_id": draft.id,
        "status": "resolved",
        "setlist_item_id": setlist_item.id,
        "piece": row_to_dict(piece),
    }


def _replace_concert_lineup(concert_id: int, artist_rows):
    concert = concerts.get_many([concert_id])
    if not concert:
        raise WorkflowError("Not found", 404)
    concert = concert[0]

    if not isinstance(artist_rows, list):
        raise WorkflowError("artists must be an array", 400)
    if not artist_rows:
        raise WorkflowError("at least one artist is required", 400)

    resolved = []
    seen_keys = set()
    has_main = False
    for i, row in enumerate(artist_rows):
        if not isinstance(row, dict):
            raise WorkflowError(f"artist {i + 1}: invalid object", 400)
        name = (row.get("artist_name") or "").strip()
        artist_id = row.get("artist_id") or None
        if artist_id is not None:
            try:
                artist_id = int(artist_id)
            except (TypeError, ValueError):
                raise WorkflowError(
                    f"artist {i + 1}: artist_id must be an integer",
                    400,
                ) from None
        role = (row.get("role") or "").strip() or "main artist"
        if role not in ALLOWED_ARTIST_ROLES:
            raise WorkflowError(
                f"artist {i + 1}: role must be 'main artist' or 'accompanist'",
                400,
            )
        instrument = row.get("instrument")
        instrument = (instrument or "").strip() or None

        artist = _promote_named_draft_reference(
            Artist,
            artist_id,
            name,
            "artist",
            required=True,
        )
        key = (artist.id, instrument or "", role)
        if key in seen_keys:
            raise WorkflowError(
                (
                    f"artist {i + 1}: duplicate lineup entry for "
                    f"{artist.name!r} with the same instrument and role"
                ),
                400,
            )
        seen_keys.add(key)
        if role == "main artist":
            has_main = True
        resolved.append((artist, instrument, role))

    if not has_main:
        raise WorkflowError("at least one main artist is required", 400)

    removed = set()
    while True:
        existing = [
            row for row in concert_artists.list(
                {"concert_id": [str(concert.id)]},
                limit=500,
            )
            if row.id not in removed
        ]
        if not existing:
            break
        for old in existing:
            removed.add(old.id)
            concert_artists.delete(old.id, commit=False)
    created = []
    for artist, instrument, role in resolved:
        created.append(concert_artists.create(
            commit=False,
            concert_id=concert.id,
            artist_id=artist.id,
            instrument=instrument,
            role=role,
        ))
    return created
