from math import pi
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

load_dotenv()

app = Flask(
    __name__,
    template_folder='../client',
    static_folder='../client',
    static_url_path='',
)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://gohitha@localhost/carnaticidx'

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

@app.route('/contributions/create_concert_draft', methods=['POST'])
def create_concert_draft():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    youtube_id = (data.get('youtube_id') or '').strip()
    title = (data.get('title') or '').strip()
    year = data.get('year')
    venue = data.get('venue')
    duration_seconds = data.get('duration_seconds')
    artists = data.get('artists') or []
    setlist = data.get('setlist') or []

    if not youtube_id:
        return jsonify({"error": "youtube_id is required"}), 400
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not artists:
        return jsonify({"error": "at least one artist is required"}), 400
    if not setlist:
        return jsonify({"error": "at least one setlist item is required"}), 400

    for i, artist in enumerate(artists):
        if not (artist.get('artist_name') or '').strip():
            return jsonify({"error": f"artist {i + 1}: name is required"}), 400

    for i, item in enumerate(setlist):
        if not (item.get('piece_name') or '').strip():
            return jsonify({"error": f"setlist item {i + 1}: piece name is required"}), 400
        if item.get('timestamp_seconds') is None:
            return jsonify({"error": f"setlist item {i + 1}: timestamp is required"}), 400
        if not item.get('sequence_number'):
            return jsonify({"error": f"setlist item {i + 1}: sequence is required"}), 400

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
                instrument=artist.get('instrument'),
                role=artist.get('role'),
            )
            db.session.add(concert_artist_draft)

        for setlist_item in setlist:
            setlist_item_draft = SetlistItemDraft(
                concert_draft_id=concert_draft.id,
                piece_id=setlist_item.get('piece_id') or None,
                piece_name=setlist_item.get('piece_name').strip(),
                raga_name=setlist_item.get('raga_name'),
                talam_name=setlist_item.get('talam_name'),
                composer_name=setlist_item.get('composer_name'),
                kind=setlist_item.get('kind'),
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
            "raga": p.raga.name if p.raga else None,
            "talam": p.talam.name if p.talam else None,
            "composer": p.composer.name if p.composer else None,
        }
        for p in rows
    ])

# Autocomplete Artist Names
@app.route('/artists/autocomplete/<string:prefix>', methods=['GET'])
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

# Autocomplete Composer Names
@app.route('/composers/autocomplete/<string:prefix>', methods=['GET'])
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
    return render_template('index.html')


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



if __name__ == '__main__':
    app.run(debug=True)