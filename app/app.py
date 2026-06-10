from flask import Flask, jsonify
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
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(255), unique=True, nullable=False)
    title = db.Column(db.String(255))
    year = db.Column(db.Integer)
    venue = db.Column(db.String(255))

    setlist_items = db.relationship('SetlistItem', back_populates='concert')
    concert_artists = db.relationship('ConcertArtist', back_populates='concert')

    def __repr__(self):
        return f"<Concert {self.title}>"

class Artist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))

    concert_artists = db.relationship('ConcertArtist', back_populates='artist')

    def __repr__(self):
        return f"<Artist {self.name}>"

class Piece(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)
    kind = db.Column(db.String(255)) # krithi, padam, varnam
    raga_id = db.Column(db.Integer, db.ForeignKey('raga.id'), nullable=False)
    composer_id = db.Column(db.Integer, db.ForeignKey('composer.id'), nullable=False)
    talam_id = db.Column(db.Integer, db.ForeignKey('talam.id'), nullable=False)

    raga = db.relationship('Raga', back_populates='pieces')
    composer = db.relationship('Composer', back_populates='pieces')
    talam = db.relationship('Talam', back_populates='pieces')
    setlist_items = db.relationship('SetlistItem', back_populates='piece')

    def __repr__(self):
        return f"<Piece {self.name}>"

class Composer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)

    pieces = db.relationship('Piece', back_populates='composer')

    def __repr__(self):
        return f"<Composer {self.name}>"

class Raga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)

    pieces = db.relationship('Piece', back_populates='raga')

    def __repr__(self):
        return f"<Raga {self.name}>"

class Talam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)

    pieces = db.relationship('Piece', back_populates='talam')

    def __repr__(self):
        return f"<Talam {self.name}>"

# Junction tables

class ConcertArtist(db.Model):
    concert_id = db.Column(db.Integer, db.ForeignKey('concert.id'), primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id'))
    instrument = db.Column(db.String(255))
    role = db.Column(db.String(255)) # "accompanist" or "main artist"

    concert = db.relationship('Concert', back_populates='concert_artists')
    artist = db.relationship('Artist', back_populates='concert_artists')

    def __repr__(self):
        return f"<ConcertArtist {self.artist_id}>"

class SetlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey('concert.id'), nullable=False)
    piece_id = db.Column(db.Integer, db.ForeignKey('piece.id'), nullable=False)
    timestamp_seconds = db.Column(db.Integer)
    sequence_number = db.Column(db.Integer)

    concert = db.relationship('Concert', back_populates='setlist_items')
    piece = db.relationship('Piece', back_populates='setlist_items')

    def __repr__(self):
        return f"<SetlistItem {self.piece_id}>"


@app.route('/')
def index():
    return jsonify({'message': 'Hello, World!'})

if __name__ == '__main__':
    app.run(debug=True)