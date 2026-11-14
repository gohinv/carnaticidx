"""SQLAlchemy db instance and data models.

`db` is created unbound here and attached to the Flask app via
`db.init_app(app)` in app.py.
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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
