from flask import Flask, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

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


@app.route('/')
def index():
    return render_template('index.html')


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



# @app.route('/pieces/search')
# def pieces_search(name: str):
    
# Register review blueprint
from review import review_bp  # noqa: E402
app.register_blueprint(review_bp)



if __name__ == '__main__':
    app.run(debug=True)