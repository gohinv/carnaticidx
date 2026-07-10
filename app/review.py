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

from flask import Blueprint, jsonify, request, abort, render_template_string

sys.path.insert(0, str(Path(__file__).resolve().parent))

review_bp = Blueprint("review", __name__, url_prefix="/review")


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
    return render_template_string(REVIEW_HTML)


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


# ---------------------------------------------------------------------------
# SPA HTML — single template string so we need no templates folder
# ---------------------------------------------------------------------------

REVIEW_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Carnatic Review</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f0f0f; color: #e8e8e8; font-size: 14px; height: 100dvh; display: flex; flex-direction: column; }
  a { color: inherit; text-decoration: none; }

  /* Top bar */
  #topbar { display: flex; align-items: center; gap: 16px; padding: 10px 18px; background: #1a1a1a; border-bottom: 1px solid #2e2e2e; flex-shrink: 0; }
  #topbar h1 { font-size: 15px; font-weight: 600; letter-spacing: .02em; }
  #tabs { display: flex; gap: 2px; }
  .tab { padding: 5px 12px; border-radius: 5px; cursor: pointer; color: #888; font-size: 13px; }
  .tab.active { background: #252525; color: #e8e8e8; }
  #stats { margin-left: auto; color: #555; font-size: 12px; }

  /* Layout */
  #main { display: flex; flex: 1; min-height: 0; }
  #sidebar { width: 280px; border-right: 1px solid #1e1e1e; display: flex; flex-direction: column; flex-shrink: 0; }
  #list-container { flex: 1; overflow-y: auto; }
  #detail { flex: 1; overflow-y: auto; padding: 24px 28px; }
  #pieces-panel, #setlists-panel { flex: 1; overflow: hidden; padding: 20px 28px; display: none; flex-direction: column; }
  .edit-layout { display: flex; gap: 28px; min-height: 0; flex: 1; }
  .edit-list { width: 320px; flex-shrink: 0; border-right: 1px solid #1e1e1e; padding-right: 18px; overflow-y: auto; }
  .edit-form { flex: 1; min-width: 0; overflow-y: auto; }
  .panel-shell { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .panel-search { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-shrink: 0; }
  .search-box { flex: 1; background: #1a1a1a; border: 1px solid #2e2e2e; color: #e8e8e8; padding: 10px 12px; border-radius: 7px; font-size: 14px; }
  .search-box:focus { outline: none; border-color: #4a7cdc; }
  .search-box::placeholder { color: #555; }
  .result-item { padding: 8px 10px; border-radius: 5px; cursor: pointer; margin-bottom: 2px; }
  .result-item:hover { background: #161616; }
  .result-item.active { background: #1c2030; }
  .result-title { font-size: 13px; }
  .result-sub { font-size: 11px; color: #555; margin-top: 2px; }
  .filter-row { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
  .filter-row label { font-size: 12px; color: #666; display: flex; gap: 6px; align-items: center; cursor: pointer; white-space: nowrap; }
  .appearance { font-size: 12px; padding: 6px 0; border-bottom: 1px solid #1a1a1a; }
  .appearance a { color: #4a7cdc; }
  .setlist-edit-row { display: grid; grid-template-columns: 56px 80px 1fr auto; gap: 8px; align-items: start; padding: 10px 0; border-bottom: 1px solid #1a1a1a; }
  .setlist-edit-row input { background: #1a1a1a; border: 1px solid #2e2e2e; color: #e8e8e8; padding: 6px 8px; border-radius: 5px; font-size: 13px; width: 100%; }
  .setlist-edit-row input:focus { outline: none; border-color: #4a7cdc; }
  .setlist-piece-wrap { position: relative; }
  .setlist-piece-sub { font-size: 11px; color: #555; margin-top: 3px; }
  .btn-save { background: #1e2535; color: #6a9ae8; padding: 6px 12px; }
  .btn-sm { padding: 6px 12px; font-size: 12px; }
  .dirty input { border-color: #a09050 !important; }

  /* List items */
  .draft-item { padding: 10px 14px; border-bottom: 1px solid #1a1a1a; cursor: pointer; }
  .draft-item:hover { background: #161616; }
  .draft-item.active { background: #1c2030; border-left: 3px solid #4a7cdc; }
  .draft-title { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .draft-meta { font-size: 11px; color: #555; margin-top: 2px; }
  .draft-conf { font-size: 10px; padding: 1px 5px; border-radius: 3px; margin-left: 4px; }
  .conf-low { background: #3a1a1a; color: #c06060; }
  .conf-mid { background: #2a2a18; color: #a09050; }
  .conf-high { background: #1a2a1a; color: #60a060; }

  /* Detail pane */
  .section { margin-bottom: 20px; }
  .label { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 5px; }
  .raw-line { font-family: monospace; background: #161616; padding: 10px 12px; border-radius: 6px; font-size: 13px; color: #bbb; border: 1px solid #222; }
  .concert-link { font-size: 12px; color: #4a7cdc; }
  .concert-link:hover { text-decoration: underline; }

  /* Fields row */
  .fields { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
  .field { display: flex; flex-direction: column; gap: 3px; min-width: 130px; flex: 1; }
  .field label { font-size: 11px; color: #555; }
  .field input, .field select { background: #1a1a1a; border: 1px solid #2e2e2e; color: #e8e8e8; padding: 6px 8px; border-radius: 5px; font-size: 13px; width: 100%; }
  .field input:focus, .field select:focus { outline: none; border-color: #4a7cdc; }

  /* Piece search */
  #piece-search-wrap { position: relative; margin-bottom: 8px; }
  #piece-search { width: 100%; }
  #piece-suggestions { position: absolute; top: 100%; left: 0; right: 0; background: #1e1e1e; border: 1px solid #2e2e2e; border-top: none; border-radius: 0 0 6px 6px; z-index: 10; max-height: 180px; overflow-y: auto; }
  .suggestion { padding: 7px 10px; cursor: pointer; font-size: 13px; }
  .suggestion:hover, .suggestion.active { background: #1c2030; }
  .suggestion-sub { font-size: 11px; color: #555; margin-top: 1px; }

  /* Neighbours */
  .neighbour { display: flex; gap: 10px; align-items: baseline; padding: 4px 0; border-bottom: 1px solid #1a1a1a; font-size: 12px; }
  .neighbour-seq { color: #444; width: 22px; flex-shrink: 0; }
  .neighbour-ts { color: #555; width: 52px; flex-shrink: 0; }
  .neighbour-piece { flex: 1; }
  .neighbour-sub { color: #555; font-size: 11px; }
  .neighbour.current { color: #e8b84b; }

  /* Action buttons */
  .actions { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
  .btn { padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; transition: opacity .15s; }
  .btn:hover { opacity: .85; }
  .btn:disabled { opacity: .35; cursor: default; }
  .btn-resolve { background: #2d5a27; color: #8fdb7e; }
  .btn-skip { background: #2a2a2a; color: #888; }
  .btn-reject { background: #3a1a1a; color: #c06060; }
  .btn-next { background: #1e2535; color: #6a9ae8; }

  /* Kbd hints */
  .kbd-hints { font-size: 11px; color: #444; margin-top: 10px; }
  kbd { background: #222; border: 1px solid #333; border-radius: 3px; padding: 1px 5px; font-size: 10px; }

  /* Toast */
  #toast { position: fixed; bottom: 20px; right: 20px; background: #1e2535; color: #8fdb7e; padding: 10px 16px; border-radius: 7px; font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none; z-index: 100; border: 1px solid #2d5a27; }
  #toast.show { opacity: 1; }
  #toast.error { background: #2a1515; color: #c06060; border-color: #3a1a1a; }

  /* Pieces panel */
  .piece-row { display: flex; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid #1a1a1a; }
  .piece-name { font-size: 13px; width: 200px; flex-shrink: 0; }
  .piece-fields { display: flex; gap: 6px; flex: 1; flex-wrap: wrap; }
  .pill { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: #1e1e1e; color: #888; border: 1px solid #2a2a2a; cursor: pointer; }
  .pill.missing { border-color: #3a2a1a; color: #a07040; background: #1e1a14; }
  .pill:hover { border-color: #4a7cdc; color: #e8e8e8; }
  .pill-kind { background: #1a1e2a; color: #6a8aab; border-color: #1e2535; }

  /* Empty state */
  .empty { color: #444; text-align: center; margin-top: 60px; font-size: 14px; }
  .empty span { font-size: 32px; display: block; margin-bottom: 10px; }
</style>
</head>
<body>

<div id="topbar">
  <h1>Carnatic Review</h1>
  <div id="tabs">
    <div class="tab active" onclick="switchTab('drafts')">Drafts</div>
    <div class="tab" onclick="switchTab('pieces')">Pieces</div>
    <div class="tab" onclick="switchTab('setlists')">Setlists</div>
  </div>
  <div id="stats">Loading…</div>
</div>

<div id="main">
  <!-- Sidebar: draft list -->
  <div id="sidebar">
    <div id="list-container"></div>
  </div>

  <!-- Main: draft detail -->
  <div id="detail">
    <div class="empty"><span>📋</span>Select a draft from the list</div>
  </div>

  <!-- Main: pieces panel -->
  <div id="pieces-panel">
    <div class="empty"><span>🎵</span>Search or load incomplete pieces</div>
  </div>

  <!-- Main: setlists panel -->
  <div id="setlists-panel">
    <div class="empty"><span>🎼</span>Search a concert to edit its setlist</div>
  </div>
</div>

<div id="toast"></div>

<script>
// ---- State ----
let drafts = [];
let draftsTotal = 0;
let currentIdx = -1;
let ragas = [], composers = [], talams = [];
let selectedPieceId = null;
let suggestionIdx = -1;
let currentTab = 'drafts';
let pieceEditId = null;
let pieceSearchTimer = null;
let concertSearchTimer = null;
let setlistConcertId = null;
let setlistPieceTimers = {};
let setlistSuggestionIdx = {};
const KIND_OPTIONS = ['','krithi','varnam','padam','tillana','viruttam','slokam','mangalam','bhajan','rtp'];

// ---- Init ----
async function init() {
  [ragas, composers, talams] = await Promise.all([
    fetch('/review/lookup/ragas').then(r => r.json()),
    fetch('/review/lookup/composers').then(r => r.json()),
    fetch('/review/lookup/talams').then(r => r.json()),
  ]);
  await loadDrafts();
}

async function loadDrafts() {
  const res = await fetch('/review/drafts?per_page=200&page=1');
  const data = await res.json();
  drafts = data.items;
  draftsTotal = data.total;
  currentIdx = -1;
  updateDraftStats();
  renderList();
  if (drafts.length > 0) selectDraft(0);
}

function updateDraftStats() {
  const el = document.getElementById('stats');
  if (!el) return;
  if (draftsTotal === 0) {
    el.textContent = 'No drafts remaining';
  } else if (drafts.length < draftsTotal) {
    el.textContent = `${draftsTotal} drafts remaining (showing ${drafts.length})`;
  } else {
    el.textContent = `${draftsTotal} drafts remaining`;
  }
}

async function refillDraftQueue() {
  const res = await fetch('/review/drafts?per_page=200&page=1');
  const data = await res.json();
  draftsTotal = data.total;
  if (data.items.length === 0) {
    drafts = [];
    currentIdx = -1;
    updateDraftStats();
    renderList();
    document.getElementById('detail').innerHTML =
      '<div class="empty"><span>✅</span>All drafts resolved!</div>';
    return;
  }
  drafts = data.items;
  currentIdx = 0;
  updateDraftStats();
  renderList();
  await selectDraft(0);
}

// ---- Tab switching ----
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach((el, i) => {
    el.classList.toggle('active', ['drafts','pieces','setlists'][i] === tab);
  });
  document.getElementById('sidebar').style.display = tab === 'drafts' ? 'flex' : 'none';
  document.getElementById('detail').style.display = tab === 'drafts' ? 'block' : 'none';
  document.getElementById('pieces-panel').style.display = tab === 'pieces' ? 'flex' : 'none';
  document.getElementById('setlists-panel').style.display = tab === 'setlists' ? 'flex' : 'none';
  if (tab === 'pieces') initPiecesPanel();
  if (tab === 'setlists') initSetlistsPanel();
  if (tab === 'drafts') updateDraftStats();
}

// ---- Draft list ----
function renderList() {
  const container = document.getElementById('list-container');
  if (drafts.length === 0) {
    container.innerHTML = '<div class="empty" style="margin-top:40px"><span>✅</span>All done!</div>';
    return;
  }
  container.innerHTML = drafts.map((d, i) => {
    const conf = d.confidence;
    const cls = conf < 0.4 ? 'conf-low' : conf < 0.7 ? 'conf-mid' : 'conf-high';
    return `<div class="draft-item${i === currentIdx ? ' active' : ''}" onclick="selectDraft(${i})">
      <div class="draft-title">${d.parsed_piece || '<em style="color:#555">no piece name</em>'}
        <span class="draft-conf ${cls}">${(conf*100).toFixed(0)}%</span>
      </div>
      <div class="draft-meta">${d.concert_title ? truncate(d.concert_title,34) : d.youtube_id} · seq ${d.sequence_number}</div>
    </div>`;
  }).join('');
}

function truncate(s, n) { return s.length > n ? s.slice(0,n)+'…' : s; }

async function selectDraft(idx) {
  currentIdx = idx;
  selectedPieceId = null;
  renderList();
  const d = drafts[idx];
  const res = await fetch(`/review/drafts/${d.id}`);
  const detail = await res.json();
  renderDetail(detail);
}

// ---- Detail pane ----
function renderDetail(d) {
  selectedPieceId = null;
  const ytUrl = `https://youtu.be/${d.youtube_id}${d.timestamp_seconds ? '?t='+d.timestamp_seconds : ''}`;

  const neighbours = (d.neighbours || []).map(si => {
    const isCurrent = si.sequence_number === d.sequence_number;
    return `<div class="neighbour${isCurrent ? ' current' : ''}">
      <span class="neighbour-seq">${si.sequence_number}.</span>
      <span class="neighbour-ts">${fmtTs(si.timestamp_seconds)}</span>
      <span class="neighbour-piece">${si.piece ? si.piece.name : '<span style="color:#444">—</span>'}
        ${si.piece ? `<span class="neighbour-sub">· ${si.piece.raga||'?'} · ${si.piece.talam||'?'}</span>` : ''}
      </span>
    </div>`;
  }).join('');

  document.getElementById('detail').innerHTML = `
    <div class="section">
      <div class="label">Concert</div>
      <a class="concert-link" href="${ytUrl}" target="_blank">▶ ${d.concert_title || d.youtube_id}</a>
    </div>

    <div class="section">
      <div class="label">Raw line</div>
      <div class="raw-line">${escHtml(d.raw_line)}</div>
    </div>

    <div class="section">
      <div class="label">Match piece</div>
      <div id="piece-search-wrap">
        <input id="piece-search" class="field input" placeholder="Search pieces (or type new name)…"
          value="${escHtml(d.parsed_piece||'')}"
          oninput="onPieceSearch(this.value)"
          onkeydown="onPieceSearchKey(event)"
          autocomplete="off">
        <div id="piece-suggestions" style="display:none"></div>
      </div>
    </div>

    <div class="section">
      <div class="label">Metadata <span style="color:#444;font-size:10px;font-weight:400;text-transform:none">(leave blank to inherit from matched piece)</span></div>
      <div class="fields">
        <div class="field">
          <label>Raga</label>
          ${datalistInput('raga-input', 'raga-list', ragas, d.parsed_raga||'')}
        </div>
        <div class="field">
          <label>Composer</label>
          ${datalistInput('composer-input', 'composer-list', composers, d.parsed_composer||'')}
        </div>
        <div class="field">
          <label>Talam</label>
          ${datalistInput('talam-input', 'talam-list', talams, d.parsed_talam||'')}
        </div>
        <div class="field">
          <label>Kind</label>
          <select id="kind-input">
            ${['','krithi','varnam','padam','tillana','viruttam','slokam','mangalam','bhajan','rtp'].map(k =>
              `<option value="${k}"${k===(d.parsed_kind||'')?'selected':''}>${k||'—'}</option>`
            ).join('')}
          </select>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="label">Setlist context</div>
      ${neighbours || '<div style="color:#444;font-size:12px">No setlist items yet</div>'}
    </div>

    <div class="actions">
      <button class="btn btn-resolve" onclick="resolveAction()">Resolve → setlist</button>
      <button class="btn btn-skip" onclick="statusAction('skip')">Skip</button>
      <button class="btn btn-reject" onclick="statusAction('reject')">Reject</button>
      <button class="btn btn-next" onclick="nextDraft()">Next →</button>
    </div>
    <div class="kbd-hints">
      <kbd>j</kbd> next &nbsp; <kbd>k</kbd> prev &nbsp; <kbd>/</kbd> search piece &nbsp;
      <kbd>Enter</kbd> resolve &nbsp; <kbd>s</kbd> skip &nbsp; <kbd>x</kbd> reject
    </div>
  `;
  // Focus search if piece name present
  const ps = document.getElementById('piece-search');
  if (ps && d.parsed_piece) ps.select();
}

function datalistInput(id, listId, options, value) {
  return `<input id="${id}" list="${listId}" value="${escHtml(value)}" autocomplete="off">
    <datalist id="${listId}">${options.map(o=>`<option value="${escHtml(o)}">`).join('')}</datalist>`;
}

// ---- Piece search / autocomplete ----
let searchTimer = null;
async function onPieceSearch(q) {
  selectedPieceId = null;
  clearTimeout(searchTimer);
  if (!q || q.length < 2) { hideSuggestions(); return; }
  searchTimer = setTimeout(async () => {
    const res = await fetch(`/review/pieces/search?q=${encodeURIComponent(q)}&limit=8`);
    const items = await res.json();
    showSuggestions(items);
  }, 180);
}

function showSuggestions(items) {
  const box = document.getElementById('piece-suggestions');
  if (!items.length) { box.style.display = 'none'; return; }
  suggestionIdx = -1;
  box.innerHTML = items.map((p, i) =>
    `<div class="suggestion" data-id="${p.id}" data-name="${escHtml(p.name)}"
         onmousedown="pickSuggestion(${p.id}, '${escHtml(p.name)}')"
         onmouseover="suggestionIdx=${i};highlightSuggestion()">
      <div>${escHtml(p.name)}</div>
      <div class="suggestion-sub">${[p.raga,p.composer,p.talam].filter(Boolean).join(' · ')}</div>
    </div>`
  ).join('');
  box.style.display = 'block';
}

function hideSuggestions() {
  const box = document.getElementById('piece-suggestions');
  if (box) { box.style.display = 'none'; suggestionIdx = -1; }
}

function onPieceSearchKey(e) {
  const box = document.getElementById('piece-suggestions');
  const items = box ? box.querySelectorAll('.suggestion') : [];
  if (e.key === 'ArrowDown') {
    e.preventDefault(); suggestionIdx = Math.min(suggestionIdx+1, items.length-1); highlightSuggestion();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault(); suggestionIdx = Math.max(suggestionIdx-1, -1); highlightSuggestion();
  } else if (e.key === 'Enter' && suggestionIdx >= 0) {
    e.preventDefault(); e.stopPropagation();
    const el = items[suggestionIdx];
    if (el) pickSuggestion(+el.dataset.id, el.dataset.name);
  } else if (e.key === 'Escape') {
    hideSuggestions();
  }
}

function highlightSuggestion() {
  document.querySelectorAll('#piece-suggestions .suggestion').forEach((el, i) => {
    el.classList.toggle('active', i === suggestionIdx);
  });
}

function pickSuggestion(id, name) {
  selectedPieceId = id;
  const ps = document.getElementById('piece-search');
  if (ps) { ps.value = name; }
  hideSuggestions();
}

// ---- Actions ----
async function resolveAction() {
  const d = drafts[currentIdx];
  const pieceName = document.getElementById('piece-search')?.value?.trim();
  const body = {
    piece_name: pieceName || d.parsed_piece,
    raga: document.getElementById('raga-input')?.value?.trim() || null,
    composer: document.getElementById('composer-input')?.value?.trim() || null,
    talam: document.getElementById('talam-input')?.value?.trim() || null,
    kind: document.getElementById('kind-input')?.value || null,
  };
  if (selectedPieceId) body.piece_id = selectedPieceId;

  const res = await fetch(`/review/drafts/${d.id}/resolve`, {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
  });
  if (res.ok) {
    const data = await res.json();
    toast(`✓ Resolved → ${data.piece.name}`);
    await removeCurrent();
  } else {
    const err = await res.json();
    toast(err.error || 'Error', true);
  }
}

async function statusAction(action) {
  const d = drafts[currentIdx];
  const res = await fetch(`/review/drafts/${d.id}/${action}`, { method: 'POST' });
  if (res.ok) {
    toast(action === 'skip' ? 'Skipped' : 'Rejected');
    await removeCurrent();
  }
}

async function removeCurrent() {
  drafts.splice(currentIdx, 1);
  draftsTotal = Math.max(0, draftsTotal - 1);
  if (drafts.length === 0) {
    await refillDraftQueue();
    return;
  }
  currentIdx = Math.min(currentIdx, drafts.length - 1);
  updateDraftStats();
  renderList();
  await selectDraft(currentIdx);
}

function nextDraft() {
  if (currentIdx < drafts.length - 1) selectDraft(currentIdx + 1);
}
function prevDraft() {
  if (currentIdx > 0) selectDraft(currentIdx - 1);
}

// ---- Pieces panel ----
function initPiecesPanel() {
  const panel = document.getElementById('pieces-panel');
  if (!panel.dataset.ready) {
    panel.innerHTML = `
      <div class="panel-shell">
        <div class="panel-search">
          <input class="search-box" id="piece-edit-search" placeholder="Search pieces by name…"
            oninput="onPieceEditSearch(this.value)" autocomplete="off">
          <div class="filter-row">
            <label><input type="checkbox" id="piece-incomplete-only" onchange="onPieceFilterChange()"> Incomplete only</label>
          </div>
        </div>
        <div class="edit-layout">
          <div class="edit-list">
            <div id="piece-edit-results"></div>
          </div>
          <div class="edit-form" id="piece-edit-form">
            <div class="empty"><span>🎵</span>Search for a piece to edit</div>
          </div>
        </div>
      </div>`;
    panel.dataset.ready = '1';
  }
  onPieceFilterChange();
  requestAnimationFrame(() => document.getElementById('piece-edit-search')?.focus());
}

async function onPieceFilterChange() {
  const incompleteOnly = document.getElementById('piece-incomplete-only')?.checked;
  const q = document.getElementById('piece-edit-search')?.value?.trim() || '';
  if (q.length >= 2) {
    await runPieceSearch(q);
    return;
  }
  if (incompleteOnly) {
    await loadIncompletePieceList();
  } else {
    document.getElementById('piece-edit-results').innerHTML =
      '<div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>';
  }
}

async function loadIncompletePieceList() {
  const res = await fetch('/review/pieces/incomplete?per_page=100');
  const data = await res.json();
  renderPieceResults(data.items, `${data.total} incomplete`);
}

function onPieceEditSearch(q) {
  clearTimeout(pieceSearchTimer);
  const incompleteOnly = document.getElementById('piece-incomplete-only')?.checked;
  if (!q || q.length < 2) {
    if (incompleteOnly) loadIncompletePieceList();
    else {
      const box = document.getElementById('piece-edit-results');
      if (box) box.innerHTML = '<div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>';
    }
    return;
  }
  pieceSearchTimer = setTimeout(() => runPieceSearch(q), 180);
}

async function runPieceSearch(q) {
  const incompleteOnly = document.getElementById('piece-incomplete-only')?.checked;
  const res = await fetch(`/review/pieces/search?q=${encodeURIComponent(q)}&limit=30`);
  let items = await res.json();
  if (incompleteOnly) {
    items = items.filter(p => !p.raga || !p.composer || !p.talam);
  }
  renderPieceResults(items, `${items.length} result${items.length === 1 ? '' : 's'}`);
}

function renderPieceResults(items, label) {
  const box = document.getElementById('piece-edit-results');
  if (!items.length) {
    box.innerHTML = `<div style="color:#444;font-size:12px;padding:8px 0">No pieces found</div>`;
    return;
  }
  box.innerHTML = `
    <div style="color:#555;font-size:11px;margin-bottom:8px">${label}</div>
    ${items.map(p => `
      <div class="result-item${p.id === pieceEditId ? ' active' : ''}" onclick="selectPieceForEdit(${p.id})">
        <div class="result-title">${escHtml(p.name)}</div>
        <div class="result-sub">${[p.raga||'raga?', p.composer||'composer?', p.talam||'talam?', p.kind||'kind?'].join(' · ')}</div>
      </div>`).join('')}`;
}

async function selectPieceForEdit(pieceId) {
  pieceEditId = pieceId;
  document.querySelectorAll('#piece-edit-results .result-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick') === `selectPieceForEdit(${pieceId})`);
  });
  const res = await fetch(`/review/pieces/${pieceId}`);
  if (!res.ok) { toast('Piece not found', true); return; }
  const p = await res.json();
  renderPieceEditForm(p);
}

function renderPieceEditForm(p) {
  const appearances = (p.appearances || []).map(a => `
    <div class="appearance">
      <a href="${a.url}" target="_blank">${escHtml(a.concert_title || 'Concert')}</a>
      <span style="color:#555"> · ${a.concert_year || '?'} · seq ${a.sequence_number} · ${a.timestamp_fmt}</span>
      <button class="btn btn-sm btn-save" style="margin-left:8px" onclick="openSetlistFromAppearance(${a.concert_id})">Edit setlist</button>
    </div>`).join('');

  document.getElementById('piece-edit-form').innerHTML = `
    <div class="section">
      <div class="label">Edit piece #${p.id}</div>
      <div class="fields">
        <div class="field" style="flex:2;min-width:200px">
          <label>Name</label>
          <input id="pe-name" value="${escHtml(p.name||'')}">
        </div>
        <div class="field">
          <label>Kind</label>
          <select id="pe-kind">
            ${KIND_OPTIONS.map(k =>
              `<option value="${k}"${k===(p.kind||'')?'selected':''}>${k||'—'}</option>`
            ).join('')}
          </select>
        </div>
        <div class="field">
          <label>Raga</label>
          ${datalistInput('pe-raga', 'pe-raga-list', ragas, p.raga||'')}
        </div>
        <div class="field">
          <label>Composer</label>
          ${datalistInput('pe-composer', 'pe-composer-list', composers, p.composer||'')}
        </div>
        <div class="field">
          <label>Talam</label>
          ${datalistInput('pe-talam', 'pe-talam-list', talams, p.talam||'')}
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-resolve" onclick="savePieceEdit()">Save piece</button>
        <button class="btn btn-skip" onclick="clearPieceField('raga')">Clear raga</button>
        <button class="btn btn-skip" onclick="clearPieceField('composer')">Clear composer</button>
        <button class="btn btn-skip" onclick="clearPieceField('talam')">Clear talam</button>
      </div>
    </div>
    <div class="section">
      <div class="label">Appearances (${(p.appearances||[]).length})</div>
      ${appearances || '<div style="color:#444;font-size:12px">Not on any setlist yet</div>'}
    </div>
    ${(p.aliases||[]).length ? `
    <div class="section">
      <div class="label">Aliases</div>
      <div style="font-size:12px;color:#888">${p.aliases.map(escHtml).join(' · ')}</div>
    </div>` : ''}`;
}

function clearPieceField(field) {
  const el = document.getElementById('pe-' + field);
  if (el) el.value = '';
}

async function savePieceEdit() {
  if (!pieceEditId) return;
  const body = {
    name: document.getElementById('pe-name')?.value?.trim(),
    kind: document.getElementById('pe-kind')?.value || null,
    raga: document.getElementById('pe-raga')?.value?.trim() || null,
    composer: document.getElementById('pe-composer')?.value?.trim() || null,
    talam: document.getElementById('pe-talam')?.value?.trim() || null,
  };
  const res = await fetch(`/review/pieces/${pieceEditId}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
  });
  if (res.ok) {
    toast('✓ Piece saved');
    await selectPieceForEdit(pieceEditId);
    onPieceFilterChange();
  } else {
    const err = await res.json().catch(() => ({}));
    toast(err.error || 'Save failed', true);
  }
}

function openSetlistFromAppearance(concertId) {
  switchTab('setlists');
  loadConcertSetlist(concertId);
}

// ---- Setlists panel ----
function initSetlistsPanel() {
  const panel = document.getElementById('setlists-panel');
  if (!panel.dataset.ready) {
    panel.innerHTML = `
      <div class="panel-shell">
        <div class="panel-search">
          <input class="search-box" id="concert-search" placeholder="Search concerts by title, venue, or YouTube id…"
            oninput="onConcertSearch(this.value)" autocomplete="off">
        </div>
        <div class="edit-layout">
          <div class="edit-list">
            <div id="concert-results">
              <div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>
            </div>
          </div>
          <div class="edit-form" id="setlist-edit-form">
            <div class="empty"><span>🎼</span>Search for a concert to edit its setlist</div>
          </div>
        </div>
      </div>`;
    panel.dataset.ready = '1';
  }
  requestAnimationFrame(() => document.getElementById('concert-search')?.focus());
}

function onConcertSearch(q) {
  clearTimeout(concertSearchTimer);
  const box = document.getElementById('concert-results');
  if (!q || q.length < 2) {
    if (box) box.innerHTML = '<div style="color:#444;font-size:12px;padding:8px 0">Type at least 2 characters to search</div>';
    return;
  }
  concertSearchTimer = setTimeout(async () => {
    const res = await fetch(`/review/concerts/search?q=${encodeURIComponent(q)}&limit=25`);
    const items = await res.json();
    if (!box) return;
    if (!items.length) {
      box.innerHTML = '<div style="color:#444;font-size:12px;padding:8px 0">No concerts found</div>';
      return;
    }
    box.innerHTML = items.map(c => `
      <div class="result-item${c.id === setlistConcertId ? ' active' : ''}" onclick="loadConcertSetlist(${c.id})">
        <div class="result-title">${escHtml(c.title || c.youtube_id)}</div>
        <div class="result-sub">${[c.year, c.venue, c.youtube_id].filter(Boolean).join(' · ')}</div>
      </div>`).join('');
  }, 180);
}

async function loadConcertSetlist(concertId) {
  setlistConcertId = concertId;
  document.querySelectorAll('#concert-results .result-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick') === `loadConcertSetlist(${concertId})`);
  });
  const res = await fetch(`/review/concerts/${concertId}/setlist`);
  if (!res.ok) { toast('Concert not found', true); return; }
  const data = await res.json();
  renderSetlistEditor(data);
}

function renderSetlistEditor(data) {
  const c = data.concert;
  const rows = (data.items || []).map(si => {
    const pieceName = si.piece ? si.piece.name : '';
    const pieceSub = si.piece
      ? [si.piece.raga, si.piece.composer, si.piece.talam].filter(Boolean).join(' · ')
      : 'No piece linked';
    return `
      <div class="setlist-edit-row" id="si-row-${si.id}" data-piece-id="${si.piece_id || ''}">
        <div>
          <div class="label" style="margin-bottom:3px">Seq</div>
          <input id="si-seq-${si.id}" type="number" min="1" value="${si.sequence_number}"
            oninput="markSetlistDirty(${si.id})">
        </div>
        <div>
          <div class="label" style="margin-bottom:3px">Time</div>
          <input id="si-ts-${si.id}" value="${fmtTs(si.timestamp_seconds)}"
            placeholder="m:ss" oninput="markSetlistDirty(${si.id})">
        </div>
        <div class="setlist-piece-wrap">
          <div class="label" style="margin-bottom:3px">Piece</div>
          <input id="si-piece-${si.id}" value="${escHtml(pieceName)}"
            placeholder="Search piece…" autocomplete="off"
            oninput="onSetlistPieceSearch(${si.id}, this.value)"
            onkeydown="onSetlistPieceKey(event, ${si.id})">
          <div class="setlist-piece-sub" id="si-piece-sub-${si.id}">${escHtml(pieceSub)}</div>
          <div id="si-sugg-${si.id}" style="display:none"></div>
        </div>
        <div style="padding-top:18px;display:flex;flex-direction:column;gap:4px">
          <button class="btn btn-sm btn-save" onclick="saveSetlistItem(${si.id})">Save</button>
          <button class="btn btn-sm btn-skip" onclick="unlinkSetlistPiece(${si.id})">Unlink</button>
          ${c.youtube_id ? `<a class="btn btn-sm btn-next" style="text-align:center" href="https://youtu.be/${c.youtube_id}?t=${si.timestamp_seconds||0}" target="_blank">▶</a>` : ''}
        </div>
      </div>`;
  }).join('');

  document.getElementById('setlist-edit-form').innerHTML = `
    <div class="section">
      <div class="label">Concert</div>
      <a class="concert-link" href="${c.url}" target="_blank">▶ ${escHtml(c.title || c.youtube_id)}</a>
      <div style="font-size:12px;color:#555;margin-top:4px">${[c.year, c.venue].filter(Boolean).join(' · ')}</div>
    </div>
    <div class="section">
      <div class="label">Setlist (${(data.items||[]).length} items)</div>
      ${rows || '<div style="color:#444;font-size:12px">No setlist items</div>'}
    </div>`;
}

function markSetlistDirty(id) {
  document.getElementById(`si-row-${id}`)?.classList.add('dirty');
}

function parseTimestamp(val) {
  if (val === '' || val == null) return null;
  if (/^\d+$/.test(String(val).trim())) return parseInt(val, 10);
  const parts = String(val).trim().split(':').map(Number);
  if (parts.some(n => Number.isNaN(n))) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}

async function onSetlistPieceSearch(itemId, q) {
  const row = document.getElementById(`si-row-${itemId}`);
  if (row) row.dataset.pieceId = '';
  markSetlistDirty(itemId);
  clearTimeout(setlistPieceTimers[itemId]);
  if (!q || q.length < 2) {
    hideSetlistSuggestions(itemId);
    return;
  }
  setlistPieceTimers[itemId] = setTimeout(async () => {
    const res = await fetch(`/review/pieces/search?q=${encodeURIComponent(q)}&limit=8`);
    const items = await res.json();
    showSetlistSuggestions(itemId, items);
  }, 180);
}

function showSetlistSuggestions(itemId, items) {
  const box = document.getElementById(`si-sugg-${itemId}`);
  if (!box) return;
  if (!items.length) { box.style.display = 'none'; return; }
  setlistSuggestionIdx[itemId] = -1;
  box.style.cssText = 'position:absolute;left:0;right:0;top:100%;background:#1e1e1e;border:1px solid #2e2e2e;border-radius:0 0 6px 6px;z-index:10;max-height:180px;overflow-y:auto;';
  box.innerHTML = items.map((p, i) => {
    const sub = [p.raga, p.composer, p.talam].filter(Boolean).join(' · ');
    return `<div class="suggestion" data-id="${p.id}" data-name="${escHtml(p.name)}" data-sub="${escHtml(sub)}"
         onmousedown="pickSetlistPieceFromEl(${itemId}, this)"
         onmouseover="setlistSuggestionIdx[${itemId}]=${i}">
      <div>${escHtml(p.name)}</div>
      <div class="suggestion-sub">${escHtml(sub)}</div>
    </div>`;
  }).join('');
  box.style.display = 'block';
}

function hideSetlistSuggestions(itemId) {
  const box = document.getElementById(`si-sugg-${itemId}`);
  if (box) { box.style.display = 'none'; setlistSuggestionIdx[itemId] = -1; }
}

function onSetlistPieceKey(e, itemId) {
  const box = document.getElementById(`si-sugg-${itemId}`);
  const items = box ? box.querySelectorAll('.suggestion') : [];
  let idx = setlistSuggestionIdx[itemId] ?? -1;
  if (e.key === 'ArrowDown') {
    e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); setlistSuggestionIdx[itemId] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault(); idx = Math.max(idx - 1, -1); setlistSuggestionIdx[itemId] = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
  } else if (e.key === 'Enter' && idx >= 0) {
    e.preventDefault();
    const el = items[idx];
    if (el) pickSetlistPieceFromEl(itemId, el);
  } else if (e.key === 'Escape') {
    hideSetlistSuggestions(itemId);
  }
}

function pickSetlistPieceFromEl(itemId, el) {
  pickSetlistPiece(itemId, +el.dataset.id, el.dataset.name, el.dataset.sub || '');
}

function pickSetlistPiece(itemId, pieceId, name, sub) {
  const row = document.getElementById(`si-row-${itemId}`);
  const input = document.getElementById(`si-piece-${itemId}`);
  const subEl = document.getElementById(`si-piece-sub-${itemId}`);
  if (row) row.dataset.pieceId = String(pieceId);
  if (input) input.value = name;
  if (subEl) subEl.textContent = sub || 'Selected piece';
  hideSetlistSuggestions(itemId);
  markSetlistDirty(itemId);
}

async function unlinkSetlistPiece(itemId) {
  const row = document.getElementById(`si-row-${itemId}`);
  const input = document.getElementById(`si-piece-${itemId}`);
  const subEl = document.getElementById(`si-piece-sub-${itemId}`);
  if (row) row.dataset.pieceId = '';
  if (input) input.value = '';
  if (subEl) subEl.textContent = 'No piece linked';
  markSetlistDirty(itemId);
  await saveSetlistItem(itemId, true);
}

async function saveSetlistItem(itemId, unlinking=false) {
  const row = document.getElementById(`si-row-${itemId}`);
  const seq = parseInt(document.getElementById(`si-seq-${itemId}`)?.value, 10);
  const ts = parseTimestamp(document.getElementById(`si-ts-${itemId}`)?.value);
  if (Number.isNaN(seq) || seq < 1) { toast('Invalid sequence number', true); return; }
  if (ts === null) { toast('Invalid timestamp (use seconds or m:ss)', true); return; }

  const body = {
    sequence_number: seq,
    timestamp_seconds: ts,
  };

  const pieceInput = document.getElementById(`si-piece-${itemId}`)?.value?.trim();
  if (unlinking || !pieceInput) {
    body.piece_id = null;
  } else if (row?.dataset.pieceId) {
    body.piece_id = parseInt(row.dataset.pieceId, 10);
  } else {
    toast('Pick a piece from suggestions (or Unlink)', true);
    return;
  }

  const res = await fetch(`/review/setlist/${itemId}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
  });
  if (res.ok) {
    toast('✓ Setlist item saved');
    row?.classList.remove('dirty');
    if (setlistConcertId) await loadConcertSetlist(setlistConcertId);
  } else {
    const err = await res.json().catch(() => ({}));
    toast(err.error || 'Save failed', true);
  }
}

// ---- Keyboard shortcuts ----
document.addEventListener('keydown', e => {
  if (currentTab !== 'drafts') return;
  const tag = document.activeElement?.tagName;
  const inInput = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
  if (e.key === '/' && !inInput) { e.preventDefault(); document.getElementById('piece-search')?.focus(); return; }
  if (inInput && e.key !== 'Escape') return;
  if (e.key === 'Escape') { document.activeElement?.blur(); hideSuggestions(); }
  if (e.key === 'j') nextDraft();
  if (e.key === 'k') prevDraft();
  if (e.key === 'Enter') resolveAction();
  if (e.key === 's') statusAction('skip');
  if (e.key === 'x') statusAction('reject');
});

// ---- Utils ----
function fmtTs(s) {
  if (!s && s !== 0) return '?';
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
           : `${m}:${String(sec).padStart(2,'0')}`;
}
function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
let toastTimer;
function toast(msg, isError=false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (isError ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 2500);
}

init();
</script>
</body>
</html>
"""
