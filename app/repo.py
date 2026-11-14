"""Generic persistence helpers over the SQLAlchemy models.

One module-level repo instance is created per table. Workflows pass
``commit=False`` and commit the session once.
"""

from __future__ import annotations

import unicodedata

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from dbmodel import (
    db,
    Artist,
    Composer,
    Concert,
    ConcertArtist,
    ConcertArtistDraft,
    ConcertDraft,
    IngestDraft,
    Piece,
    PieceAlias,
    Raga,
    SetlistItem,
    SetlistItemDraft,
    Talam,
)

WORD_SIMILARITY_THRESHOLD = 0.5


class ConflictError(Exception):
    """Unique or foreign-key constraint violation."""


class NotFoundError(Exception):
    """Requested row does not exist."""


class Repo:
    """CRUD for one mapped model. ``id`` is never writable."""

    def __init__(self, model):
        self.model = model
        self.columns = {
            col.name: getattr(model, col.name)
            for col in model.__table__.columns
        }

    def create(self, commit: bool = True, **fields):
        """Insert a row. Unknown columns raise ``ValueError``."""
        row = self.model(**self._writable(fields))
        db.session.add(row)
        self._persist(commit)
        return row

    def get_many(self, ids):
        """Return existing rows for ``ids``, sorted by id."""
        if not ids:
            return []
        rows = (
            db.session.query(self.model)
            .filter(self.model.id.in_(list(ids)))
            .all()
        )
        rows.sort(key=lambda row: row.id)
        return rows

    def list(
        self,
        filters: dict[str, list[str]] | None = None,
        limit: int = 200,
        offset: int = 0,
        order_by: str | None = None,
    ):
        """Filter with AND. Multiple values are IN; the string ``null`` is IS NULL."""
        query = db.session.query(self.model)
        for key, values in (filters or {}).items():
            if key not in self.columns:
                raise ValueError(f"unknown column: {key}")
            column = self.columns[key]
            include_null = False
            concrete = []
            for value in values:
                if value == "null":
                    include_null = True
                else:
                    concrete.append(_coerce(column, value))
            clauses = []
            if concrete:
                clauses.append(column.in_(concrete))
            if include_null:
                clauses.append(column.is_(None))
            if not clauses:
                query = query.filter(column.in_([]))
            elif len(clauses) == 1:
                query = query.filter(clauses[0])
            else:
                query = query.filter(or_(*clauses))
        return (
            query.order_by(self._order_clause(order_by))
            .limit(limit)
            .offset(offset)
            .all()
        )

    def update(self, row_id: int, commit: bool = True, **fields):
        """Partial update. Missing ids raise ``NotFoundError``."""
        row = self._get(row_id)
        for key, value in self._writable(fields).items():
            setattr(row, key, value)
        self._persist(commit)
        return row

    def delete(self, row_id: int, commit: bool = True):
        """Delete a row. Missing ids raise ``NotFoundError``."""
        row = self._get(row_id)
        db.session.delete(row)
        self._persist(commit)
        return row

    def _writable(self, fields: dict) -> dict:
        data = dict(fields)
        data.pop("id", None)
        unknown = [key for key in data if key not in self.columns]
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown column: {names}")
        return data

    def _persist(self, commit: bool) -> None:
        try:
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        except IntegrityError as exc:
            db.session.rollback()
            orig = getattr(exc, "orig", None)
            raise ConflictError(str(orig) if orig else str(exc)) from exc

    def _get(self, row_id: int):
        row = db.session.get(self.model, row_id)
        if row is None:
            raise NotFoundError(
                f"{self.model.__tablename__} {row_id} not found"
            )
        return row

    def _order_clause(self, order_by: str | None):
        if not order_by:
            return self.columns["id"].asc()
        spec = order_by.strip()
        descending = spec.startswith("-")
        name = spec[1:] if descending else spec
        if name not in self.columns:
            raise ValueError(f"unknown column: {name}")
        column = self.columns[name]
        return column.desc() if descending else column.asc()


class NamedRepo(Repo):
    """A ``Repo`` whose ``name_column`` supports hybrid autocomplete."""

    def __init__(self, model, name_column: str):
        super().__init__(model)
        if name_column not in self.columns:
            raise ValueError(f"unknown column: {name_column}")
        self.name_column = name_column

    def autocomplete(self, prefix: str, limit: int = 10):
        """Trigram word-similarity matches, then unseen substring matches.

        ``word_similarity`` scores the query against the best-matching extent
        of the name, so partial words anywhere in long names (concert titles)
        still match. ``limit`` is capped at 50; the merged list can hold up to
        twice that. An empty query returns no rows.
        """
        limit = min(int(limit), 50)
        query = (prefix or "").strip()
        if not query or limit < 1:
            return []

        norm = normalize_name(query)
        column = self.columns[self.name_column]
        score = func.word_similarity(norm, column)
        starts_with = column.istartswith(query, autoescape=True)
        fuzzy = (
            db.session.query(self.model)
            .filter(score >= WORD_SIMILARITY_THRESHOLD)
            .order_by(score.desc(), starts_with.desc(), column)
            .limit(limit)
            .all()
        )
        substring = (
            db.session.query(self.model)
            .filter(column.icontains(query, autoescape=True))
            .order_by(starts_with.desc(), column)
            .limit(limit)
            .all()
        )
        seen = {row.id for row in fuzzy}
        results = list(fuzzy)
        for row in substring:
            if row.id not in seen:
                results.append(row)
                seen.add(row.id)
        return results


def normalize_name(text: str) -> str:
    """NFKD, ASCII, lowercase. Shared by autocomplete and draft resolution."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower().strip()


concerts = NamedRepo(Concert, "title")
artists = NamedRepo(Artist, "name")
composers = NamedRepo(Composer, "name")
ragas = NamedRepo(Raga, "name")
talams = NamedRepo(Talam, "name")
pieces = NamedRepo(Piece, "name")
concert_artists = Repo(ConcertArtist)
setlist_items = Repo(SetlistItem)
piece_aliases = Repo(PieceAlias)
concert_drafts = Repo(ConcertDraft)
setlist_item_drafts = Repo(SetlistItemDraft)
concert_artist_drafts = Repo(ConcertArtistDraft)
ingest_drafts = Repo(IngestDraft)


def _python_type(column):
    try:
        return column.type.python_type
    except NotImplementedError:
        return str


def _coerce(column, value):
    """Coerce a query-string value to the column's Python type."""
    if not isinstance(value, str):
        return value
    py_type = _python_type(column)
    if py_type is bool:
        lowered = value.lower()
        if lowered in {"1", "true", "yes"}:
            return True
        if lowered in {"0", "false", "no"}:
            return False
        raise ValueError(f"invalid boolean for {column.key}: {value!r}")
    try:
        return py_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"invalid value for {column.key}: {value!r}"
        ) from exc
