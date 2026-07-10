"""
Review blueprint — interactive draft resolution and record editing.

Routes
------
GET  /review/                       → SPA shell (HTML)
GET  /review/drafts                 → paginated needs_review drafts
GET  /review/drafts/<id>            → single draft with concert + neighbours
POST /review/drafts/<id>/resolve    → link/create piece → SetlistItem → resolved
POST /review/drafts/<id>/skip       → mark skipped
POST /review/drafts/<id>/reject     → mark rejected
GET  /review/pieces/search          → trgm piece search (?q=&limit=)
GET  /review/pieces/incomplete      → pieces with any NULL FK
GET  /review/pieces/<id>            → piece detail + setlist appearances
PATCH /review/pieces/<id>           → edit name/raga/composer/talam/kind
GET  /review/concerts/search        → concert search (?q=&limit=)
GET  /review/concerts/<id>/setlist  → editable setlist for a concert
PATCH /review/setlist/<id>          → edit piece/timestamp/sequence
GET  /review/lookup/ragas           → all raga names
GET  /review/lookup/composers       → all composer names
GET  /review/lookup/talams          → all talam names
"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Blueprint, jsonify, request, abort, render_template

sys.path.insert(0, str(Path(__file__).resolve().parent))

_APP_DIR = Path(__file__).resolve().parent

review_bp = Blueprint(
    "review",
    __name__,
    url_prefix="/review",
    template_folder=str(_APP_DIR / "templates"),
    static_folder=str(_APP_DIR / "static"),
    static_url_path="/static",
)


def _db():
    from app import db
    return db


def _models():
    from app import (
        db, Concert, Artist, Raga, Talam, Composer,
        Piece, PieceAlias, SetlistItem, IngestDraft,
    )
    return db, Concert, Artist, Raga, Talam, Composer, Piece, PieceAlias, SetlistItem, IngestDraft


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _draft_summary(d) -> dict:
    return {
        "id": d.id,
        "youtube_id": d.youtube_id,
        "sequence_number": d.sequence_number,
        "timestamp_seconds": d.timestamp_seconds,
        "raw_line": d.raw_line,
        "parsed_piece": d.parsed_piece,
        "parsed_raga": d.parsed_raga,
        "parsed_talam": d.parsed_talam,
        "parsed_composer": d.parsed_composer,
        "parsed_kind": d.parsed_kind,
        "confidence": d.confidence,
        "status": d.status,
    }


def _piece_summary(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "raga": p.raga.name if p.raga else None,
        "composer": p.composer.name if p.composer else None,
        "talam": p.talam.name if p.talam else None,
        "raga_id": p.raga_id,
        "composer_id": p.composer_id,
        "talam_id": p.talam_id,
    }


def _setlist_item_summary(si) -> dict:
    return {
        "id": si.id,
        "concert_id": si.concert_id,
        "sequence_number": si.sequence_number,
        "timestamp_seconds": si.timestamp_seconds,
        "piece_id": si.piece_id,
        "piece": _piece_summary(si.piece) if si.piece else None,
    }


def _concert_summary(c) -> dict:
    return {
        "id": c.id,
        "youtube_id": c.youtube_id,
        "title": c.title,
        "year": c.year,
        "venue": c.venue,
        "duration_seconds": c.duration_seconds,
        "url": f"https://www.youtube.com/watch?v={c.youtube_id}",
    }


def _fmt_ts(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# SPA shell
# ---------------------------------------------------------------------------

@review_bp.route("/")
def review_index():
    return render_template("review.html")


# ---------------------------------------------------------------------------
# Draft endpoints
# ---------------------------------------------------------------------------

@review_bp.route("/drafts")
def list_drafts():
    db, Concert, *_, IngestDraft = _models()
    status = request.args.get("status", "needs_review")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 30))

    q = db.session.query(IngestDraft).filter_by(status=status).order_by(
        IngestDraft.youtube_id, IngestDraft.sequence_number
    )
    total = q.count()
    drafts = q.offset((page - 1) * per_page).limit(per_page).all()

    # Attach concert titles
    yt_ids = list({d.youtube_id for d in drafts})
    concerts = {
        c.youtube_id: c.title
        for c in db.session.query(Concert).filter(Concert.youtube_id.in_(yt_ids)).all()
    }

    items = []
    for d in drafts:
        item = _draft_summary(d)
        item["concert_title"] = concerts.get(d.youtube_id)
        items.append(item)

    return jsonify({"total": total, "page": page, "per_page": per_page, "items": items})


@review_bp.route("/drafts/<int:draft_id>")
def get_draft(draft_id: int):
    db, Concert, *_, SetlistItem, IngestDraft = _models()
    draft = db.session.get(IngestDraft, draft_id)
    if not draft:
        abort(404)

    concert = db.session.query(Concert).filter_by(youtube_id=draft.youtube_id).first()

    # Neighbouring setlist items for context
    neighbours = []
    if concert:
        neighbours = (
            db.session.query(SetlistItem)
            .filter_by(concert_id=concert.id)
            .order_by(SetlistItem.sequence_number)
            .all()
        )

    result = _draft_summary(draft)
    result["concert_title"] = concert.title if concert else None
    result["concert_id"] = concert.id if concert else None
    result["neighbours"] = [_setlist_item_summary(si) for si in neighbours]
    result["timestamp_fmt"] = _fmt_ts(draft.timestamp_seconds)
    return jsonify(result)


@review_bp.route("/drafts/<int:draft_id>/resolve", methods=["POST"])
def resolve_draft(draft_id: int):
    """
    Body (all optional except one of piece_id or piece_name must be present):
      piece_id      — ID of existing piece to link
      piece_name    — name for a new or matched piece
      raga          — raga name (used to find/create piece if piece_id absent)
      composer      — composer name
      talam         — talam name
      kind          — piece kind
    """
    db, Concert, _, Raga, Talam, Composer, Piece, PieceAlias, SetlistItem, IngestDraft = _models()

    draft = db.session.get(IngestDraft, draft_id)
    if not draft:
        abort(404)
    if draft.status != "needs_review":
        return jsonify({"error": f"Draft already has status={draft.status!r}"}), 400

    concert = db.session.query(Concert).filter_by(youtube_id=draft.youtube_id).first()
    if not concert:
        abort(404, "Concert not found for this draft")

    data = request.get_json(force=True) or {}
    piece_id = data.get("piece_id")
    piece_name = data.get("piece_name") or draft.parsed_piece
    raga_name = data.get("raga") or draft.parsed_raga
    composer_name = data.get("composer") or draft.parsed_composer
    talam_name = data.get("talam") or draft.parsed_talam
    kind = data.get("kind") or draft.parsed_kind

    piece = None

    if piece_id:
        piece = db.session.get(Piece, piece_id)
        if not piece:
            abort(400, "piece_id not found")
    elif piece_name:
        # Resolve or create
        raga_row = db.session.query(Raga).filter_by(name=raga_name).first() if raga_name else None
        composer_row = None
        if composer_name:
            composer_row, _ = _get_or_create(db.session, Composer, name=composer_name)
        talam_row = None
        if talam_name:
            talam_row, _ = _get_or_create(db.session, Talam, name=talam_name)
        if not raga_row and raga_name:
            raga_row, _ = _get_or_create(db.session, Raga, name=raga_name)

        from sqlalchemy import func as sqlfunc
        norm = _normalize(piece_name)
        match = None

        # Try raga-scoped exact match first, then cross-raga
        for scoped in ([raga_row.id] if raga_row else []) + [None]:
            q = db.session.query(Piece).filter(Piece.name == piece_name)
            if scoped is not None:
                q = q.filter(Piece.raga_id == scoped)
            match = q.first()
            if match:
                break
            # normalized
            candidates = db.session.query(Piece)
            if scoped is not None:
                candidates = candidates.filter(Piece.raga_id == scoped)
            for p in candidates.all():
                if _normalize(p.name) == norm:
                    match = p
                    break
            if match:
                break
            # trgm
            tq = db.session.query(Piece).filter(
                sqlfunc.similarity(Piece.name, norm) > 0.4
            ).order_by(sqlfunc.similarity(Piece.name, norm).desc())
            if scoped is not None:
                tq = tq.filter(Piece.raga_id == scoped)
            match = tq.first()
            if match:
                break

        if match:
            piece = match
            # Add alias if spelling differs
            if _normalize(piece_name) != _normalize(piece.name):
                exists = any(_normalize(a.alias) == _normalize(piece_name) for a in piece.aliases)
                if not exists:
                    db.session.add(PieceAlias(piece_id=piece.id, alias=piece_name))
            # Enrich NULL fields
            if raga_row and piece.raga_id is None:
                piece.raga_id = raga_row.id
            if composer_row and piece.composer_id is None:
                piece.composer_id = composer_row.id
            if talam_row and piece.talam_id is None:
                piece.talam_id = talam_row.id
            if kind and piece.kind is None:
                piece.kind = kind
        else:
            piece = Piece(
                name=piece_name,
                raga_id=raga_row.id if raga_row else None,
                composer_id=composer_row.id if composer_row else None,
                talam_id=talam_row.id if talam_row else None,
                kind=kind,
            )
            db.session.add(piece)
            db.session.flush()
    else:
        return jsonify({"error": "Provide piece_id or piece_name"}), 400

    seq = draft.sequence_number
    if seq is None:
        return jsonify({"error": "Draft has no sequence_number"}), 400

    existing = db.session.query(SetlistItem).filter_by(
        concert_id=concert.id, sequence_number=seq
    ).first()
    if existing:
        setlist_item = existing
        setlist_item.piece_id = piece.id
        if draft.timestamp_seconds is not None:
            setlist_item.timestamp_seconds = draft.timestamp_seconds
    else:
        setlist_item = SetlistItem(
            concert_id=concert.id,
            piece_id=piece.id,
            timestamp_seconds=draft.timestamp_seconds or 0,
            sequence_number=seq,
        )
        db.session.add(setlist_item)
        db.session.flush()

    draft.status = "resolved"
    draft.resolved_setlist_item_id = setlist_item.id
    db.session.commit()

    return jsonify({
        "draft_id": draft.id,
        "status": "resolved",
        "setlist_item_id": setlist_item.id,
        "piece": _piece_summary(piece),
    })


@review_bp.route("/drafts/<int:draft_id>/skip", methods=["POST"])
def skip_draft(draft_id: int):
    db = _db()
    from app import IngestDraft
    draft = db.session.get(IngestDraft, draft_id)
    if not draft:
        abort(404)
    draft.status = "skipped"
    db.session.commit()
    return jsonify({"draft_id": draft_id, "status": "skipped"})


@review_bp.route("/drafts/<int:draft_id>/reject", methods=["POST"])
def reject_draft(draft_id: int):
    db = _db()
    from app import IngestDraft
    draft = db.session.get(IngestDraft, draft_id)
    if not draft:
        abort(404)
    draft.status = "rejected"
    db.session.commit()
    return jsonify({"draft_id": draft_id, "status": "rejected"})


# ---------------------------------------------------------------------------
# Piece endpoints
# ---------------------------------------------------------------------------

@review_bp.route("/pieces/search")
def search_pieces():
    from sqlalchemy import func as sqlfunc
    db, *_, Piece, PieceAlias, SetlistItem, IngestDraft = _models()
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 10)), 50)
    if not q:
        return jsonify([])

    norm = _normalize(q)
    results = (
        db.session.query(Piece)
        .filter(sqlfunc.similarity(Piece.name, norm) > 0.2)
        .order_by(sqlfunc.similarity(Piece.name, norm).desc())
        .limit(limit)
        .all()
    )
    # Also exact prefix match to catch short names
    prefix = db.session.query(Piece).filter(Piece.name.ilike(f"{q}%")).limit(limit).all()
    seen = {p.id for p in results}
    for p in prefix:
        if p.id not in seen:
            results.append(p)
            seen.add(p.id)

    return jsonify([_piece_summary(p) for p in results])


@review_bp.route("/pieces/incomplete")
def incomplete_pieces():
    db, *_, Piece, PieceAlias, SetlistItem, IngestDraft = _models()
    from sqlalchemy import or_
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 30))

    q = db.session.query(Piece).filter(
        or_(Piece.raga_id.is_(None), Piece.composer_id.is_(None), Piece.talam_id.is_(None))
    ).order_by(Piece.name)
    total = q.count()
    pieces = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({"total": total, "page": page, "per_page": per_page,
                    "items": [_piece_summary(p) for p in pieces]})


@review_bp.route("/pieces/<int:piece_id>")
def get_piece(piece_id: int):
    db, Concert, *_, Piece, PieceAlias, SetlistItem, IngestDraft = _models()
    piece = db.session.get(Piece, piece_id)
    if not piece:
        abort(404)

    appearances = (
        db.session.query(SetlistItem, Concert)
        .join(Concert, SetlistItem.concert_id == Concert.id)
        .filter(SetlistItem.piece_id == piece_id)
        .order_by(Concert.year.desc().nullslast(), Concert.title)
        .all()
    )
    result = _piece_summary(piece)
    result["aliases"] = [a.alias for a in piece.aliases]
    result["appearances"] = [
        {
            "setlist_item_id": si.id,
            "concert_id": c.id,
            "concert_title": c.title,
            "concert_year": c.year,
            "sequence_number": si.sequence_number,
            "timestamp_seconds": si.timestamp_seconds,
            "timestamp_fmt": _fmt_ts(si.timestamp_seconds),
            "url": f"https://www.youtube.com/watch?v={c.youtube_id}&t={si.timestamp_seconds}",
        }
        for si, c in appearances
    ]
    return jsonify(result)


@review_bp.route("/pieces/<int:piece_id>", methods=["PATCH"])
def patch_piece(piece_id: int):
    db, _, _, Raga, Talam, Composer, Piece, *_ = _models()
    piece = db.session.get(Piece, piece_id)
    if not piece:
        abort(404)

    data = request.get_json(force=True) or {}

    def _resolve_fk(model, name_val):
        if name_val is None or name_val == "":
            return None
        row = db.session.query(model).filter_by(name=name_val).first()
        if not row:
            row = model(name=name_val)
            db.session.add(row)
            db.session.flush()
        return row

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        piece.name = name

    if "raga" in data:
        row = _resolve_fk(Raga, data["raga"])
        piece.raga_id = row.id if row else None
    if "composer" in data:
        row = _resolve_fk(Composer, data["composer"])
        piece.composer_id = row.id if row else None
    if "talam" in data:
        row = _resolve_fk(Talam, data["talam"])
        piece.talam_id = row.id if row else None
    if "kind" in data:
        kind = data["kind"]
        piece.kind = kind if kind else None

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    return jsonify(_piece_summary(piece))


# ---------------------------------------------------------------------------
# Concert / setlist endpoints
# ---------------------------------------------------------------------------

@review_bp.route("/concerts/search")
def search_concerts():
    from sqlalchemy import or_
    db, Concert, *_ = _models()
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    if not q:
        return jsonify([])

    rows = (
        db.session.query(Concert)
        .filter(
            or_(
                Concert.title.ilike(f"%{q}%"),
                Concert.youtube_id.ilike(f"%{q}%"),
                Concert.venue.ilike(f"%{q}%"),
            )
        )
        .order_by(Concert.year.desc().nullslast(), Concert.title)
        .limit(limit)
        .all()
    )
    return jsonify([_concert_summary(c) for c in rows])


@review_bp.route("/concerts/<int:concert_id>/setlist")
def concert_setlist(concert_id: int):
    db, Concert, *_, SetlistItem, IngestDraft = _models()
    concert = db.session.get(Concert, concert_id)
    if not concert:
        abort(404)

    items = (
        db.session.query(SetlistItem)
        .filter_by(concert_id=concert_id)
        .order_by(SetlistItem.sequence_number)
        .all()
    )
    return jsonify({
        "concert": _concert_summary(concert),
        "items": [_setlist_item_summary(si) for si in items],
    })


@review_bp.route("/setlist/<int:item_id>", methods=["PATCH"])
def patch_setlist_item(item_id: int):
    """
    Body (all optional):
      piece_id           — existing piece id, or null to unlink
      timestamp_seconds  — int >= 0
      sequence_number    — int >= 1 (must be unique within concert)
    """
    db, *_, Piece, PieceAlias, SetlistItem, IngestDraft = _models()
    item = db.session.get(SetlistItem, item_id)
    if not item:
        abort(404)

    data = request.get_json(force=True) or {}

    if "piece_id" in data:
        piece_id = data["piece_id"]
        if piece_id is None:
            item.piece_id = None
        else:
            piece = db.session.get(Piece, piece_id)
            if not piece:
                return jsonify({"error": "piece_id not found"}), 400
            item.piece_id = piece.id

    if "timestamp_seconds" in data:
        ts = data["timestamp_seconds"]
        if ts is None:
            return jsonify({"error": "timestamp_seconds cannot be null"}), 400
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            return jsonify({"error": "timestamp_seconds must be an integer"}), 400
        if ts < 0:
            return jsonify({"error": "timestamp_seconds must be >= 0"}), 400
        item.timestamp_seconds = ts

    if "sequence_number" in data:
        seq = data["sequence_number"]
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return jsonify({"error": "sequence_number must be an integer"}), 400
        if seq < 1:
            return jsonify({"error": "sequence_number must be >= 1"}), 400
        conflict = (
            db.session.query(SetlistItem)
            .filter(
                SetlistItem.concert_id == item.concert_id,
                SetlistItem.sequence_number == seq,
                SetlistItem.id != item.id,
            )
            .first()
        )
        if conflict:
            return jsonify({
                "error": f"sequence_number {seq} already used by setlist item {conflict.id}",
            }), 400
        item.sequence_number = seq

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    # Refresh relationship for serialiser
    db.session.refresh(item)
    return jsonify(_setlist_item_summary(item))


# ---------------------------------------------------------------------------
# Lookup endpoints
# ---------------------------------------------------------------------------

@review_bp.route("/lookup/ragas")
def lookup_ragas():
    db, _, _, Raga, *_ = _models()
    return jsonify([r.name for r in db.session.query(Raga).order_by(Raga.name).all()])


@review_bp.route("/lookup/composers")
def lookup_composers():
    db, _, _, _, _, Composer, *_ = _models()
    return jsonify([c.name for c in db.session.query(Composer).order_by(Composer.name).all()])


@review_bp.route("/lookup/talams")
def lookup_talams():
    db, _, _, _, Talam, *_ = _models()
    return jsonify([t.name for t in db.session.query(Talam).order_by(Talam.name).all()])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create(session, model, **kwargs):
    row = session.query(model).filter_by(**kwargs).first()
    if row:
        return row, False
    row = model(**kwargs)
    session.add(row)
    session.flush()
    return row, True


def _normalize(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower().strip()
