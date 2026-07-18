"""
Review blueprint — interactive draft resolution and record editing.

All /review routes require HTTP Basic Auth (ADMIN_USERNAME / ADMIN_PASSWORD).

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
GET  /review/concerts/<id>/setlist  → editable setlist + artists for a concert
PATCH /review/concerts/<id>         → edit concert metadata / replace lineup
PATCH /review/setlist/<id>          → edit piece/timestamp/sequence
GET  /review/concert-drafts         → paginated contributed concert drafts
GET  /review/concert-drafts/<id>    → contributed concert draft detail
POST /review/concert-drafts/<id>/approve → publish a contributed concert
POST /review/concert-drafts/<id>/reject  → reject a contributed concert
PATCH /review/setlist-drafts/<id>   → edit draft setlist piece/timestamp/sequence
GET  /review/lookup/ragas           → all raga names
GET  /review/lookup/composers       → all composer names
GET  /review/lookup/talams          → all talam names
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, abort, render_template

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


def _unauthorized():
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Review"'},
    )


@review_bp.before_request
def require_admin_auth():
    """HTTP Basic Auth for all /review routes using ADMIN_USERNAME / ADMIN_PASSWORD."""
    expected_user = os.getenv("ADMIN_USERNAME")
    expected_pass = os.getenv("ADMIN_PASSWORD")
    if not expected_user or not expected_pass:
        return Response(
            "Admin credentials are not configured",
            503,
        )

    auth = request.authorization
    if not auth or not auth.username or auth.password is None:
        return _unauthorized()

    user_ok = secrets.compare_digest(auth.username, expected_user)
    pass_ok = secrets.compare_digest(auth.password, expected_pass)
    if not (user_ok and pass_ok):
        return _unauthorized()


def _db():
    from app import db
    return db


def _models():
    from app import (
        db, Concert, Artist, Raga, Talam, Composer,
        Piece, PieceAlias, SetlistItem, IngestDraft,
    )
    return db, Concert, Artist, Raga, Talam, Composer, Piece, PieceAlias, SetlistItem, IngestDraft


def _contribution_models():
    from app import (
        db, Concert, Artist, Raga, Talam, Composer, Piece,
        ConcertArtist, SetlistItem,
        ConcertDraft, ConcertArtistDraft, SetlistItemDraft,
    )
    return (
        db, Concert, Artist, Raga, Talam, Composer, Piece,
        ConcertArtist, SetlistItem,
        ConcertDraft, ConcertArtistDraft, SetlistItemDraft,
    )


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


def _concert_artist_summary(ca, artist) -> dict:
    return {
        "id": ca.id,
        "artist_id": artist.id if artist else ca.artist_id,
        "artist_name": artist.name if artist else None,
        "instrument": ca.instrument,
        "role": ca.role,
    }


ALLOWED_ARTIST_ROLES = frozenset({"main artist", "accompanist"})


def _concert_draft_summary(draft) -> dict:
    return {
        "id": draft.id,
        "youtube_id": draft.youtube_id,
        "title": draft.title,
        "year": draft.year,
        "venue": draft.venue,
        "duration_seconds": draft.duration_seconds,
        "status": draft.status,
        "artist_count": len(draft.concert_artist_drafts),
        "setlist_item_count": len(draft.setlist_item_drafts),
    }


def _concert_draft_detail(draft) -> dict:
    result = _concert_draft_summary(draft)
    result["artists"] = [
        {
            "id": artist_draft.id,
            "artist_id": artist_draft.artist_id,
            "artist_name": (
                artist_draft.artist.name
                if artist_draft.artist
                else artist_draft.artist_name
            ),
            "submitted_artist_name": artist_draft.artist_name,
            "instrument": artist_draft.instrument,
            "role": artist_draft.role,
        }
        for artist_draft in draft.concert_artist_drafts
    ]
    result["setlist"] = [
        _setlist_item_draft_summary(item)
        for item in draft.setlist_item_drafts
    ]
    return result


def _setlist_item_draft_summary(item) -> dict:
    return {
        "id": item.id,
        "concert_draft_id": item.concert_draft_id,
        "piece_id": item.piece_id,
        "piece_name": item.piece.name if item.piece else item.piece_name,
        "submitted_piece_name": item.piece_name,
        "raga_id": item.raga_id,
        "raga_name": item.raga.name if item.raga else item.raga_name,
        "talam_id": item.talam_id,
        "talam_name": item.talam.name if item.talam else item.talam_name,
        "composer_id": item.composer_id,
        "composer_name": (
            item.composer.name if item.composer else item.composer_name
        ),
        "kind": item.piece.kind if item.piece else item.kind,
        "timestamp_seconds": item.timestamp_seconds,
        "sequence_number": item.sequence_number,
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
# Contributed concert draft endpoints
# ---------------------------------------------------------------------------

@review_bp.route("/concert-drafts")
def list_concert_drafts():
    db, *_, ConcertDraft, ConcertArtistDraft, SetlistItemDraft = _contribution_models()
    status = request.args.get("status", "submitted").strip()

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 30)), 1), 100)
    except (TypeError, ValueError):
        return jsonify({"error": "page and per_page must be integers"}), 400

    query = db.session.query(ConcertDraft)
    if status != "all":
        query = query.filter(ConcertDraft.status == status)
    query = query.order_by(ConcertDraft.id)

    total = query.count()
    drafts = query.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_concert_draft_summary(draft) for draft in drafts],
    })


@review_bp.route("/concert-drafts/<int:draft_id>")
def get_concert_draft(draft_id: int):
    db, *_, ConcertDraft, ConcertArtistDraft, SetlistItemDraft = _contribution_models()
    draft = db.session.get(ConcertDraft, draft_id)
    if not draft:
        abort(404)
    return jsonify(_concert_draft_detail(draft))


@review_bp.route("/concert-drafts/<int:draft_id>/approve", methods=["POST"])
def approve_concert_draft(draft_id: int):
    (
        db, Concert, Artist, Raga, Talam, Composer, Piece,
        ConcertArtist, SetlistItem,
        ConcertDraft, ConcertArtistDraft, SetlistItemDraft,
    ) = _contribution_models()

    draft = db.session.get(ConcertDraft, draft_id)
    if not draft:
        abort(404)
    if draft.status != "submitted":
        return jsonify({
            "error": f"Only submitted drafts can be approved; status is {draft.status!r}",
        }), 409

    existing_concert = db.session.query(Concert).filter_by(
        youtube_id=draft.youtube_id
    ).first()
    if existing_concert:
        return jsonify({
            "error": "A concert with this YouTube ID already exists",
            "concert_id": existing_concert.id,
        }), 409

    if not draft.concert_artist_drafts:
        return jsonify({"error": "Draft has no artists"}), 422
    if not draft.setlist_item_drafts:
        return jsonify({"error": "Draft has no setlist items"}), 422

    try:
        concert = Concert(
            youtube_id=draft.youtube_id,
            title=draft.title,
            year=draft.year,
            venue=draft.venue,
            duration_seconds=draft.duration_seconds,
        )
        db.session.add(concert)
        db.session.flush()

        for artist_draft in draft.concert_artist_drafts:
            artist = _promote_named_draft_reference(
                db.session,
                Artist,
                artist_draft.artist_id,
                artist_draft.artist_name,
                "artist",
                required=True,
            )
            artist_draft.artist_id = artist.id
            db.session.add(ConcertArtist(
                concert_id=concert.id,
                artist_id=artist.id,
                instrument=artist_draft.instrument,
                role=artist_draft.role,
            ))

        for item_draft in draft.setlist_item_drafts:
            piece = db.session.get(Piece, item_draft.piece_id) if item_draft.piece_id else None
            if item_draft.piece_id and not piece:
                raise ValueError(
                    f"setlist item {item_draft.id}: piece_id "
                    f"{item_draft.piece_id} does not exist"
                )

            if not piece:
                raga = _promote_named_draft_reference(
                    db.session, Raga, item_draft.raga_id,
                    item_draft.raga_name, "raga",
                )
                talam = _promote_named_draft_reference(
                    db.session, Talam, item_draft.talam_id,
                    item_draft.talam_name, "talam",
                )
                composer = _promote_named_draft_reference(
                    db.session, Composer, item_draft.composer_id,
                    item_draft.composer_name, "composer",
                )
                piece = _promote_draft_piece(
                    db.session, Piece, item_draft,
                    raga_id=raga.id if raga else None,
                    talam_id=talam.id if talam else None,
                    composer_id=composer.id if composer else None,
                )
                item_draft.piece_id = piece.id
                item_draft.raga_id = raga.id if raga else None
                item_draft.talam_id = talam.id if talam else None
                item_draft.composer_id = composer.id if composer else None

            db.session.add(SetlistItem(
                concert_id=concert.id,
                piece_id=piece.id,
                timestamp_seconds=item_draft.timestamp_seconds,
                sequence_number=item_draft.sequence_number,
            ))

        draft.status = "approved"
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "draft_id": draft.id,
        "status": draft.status,
        "concert": _concert_summary(concert),
    }), 201


@review_bp.route("/concert-drafts/<int:draft_id>/reject", methods=["POST"])
def reject_concert_draft(draft_id: int):
    db, *_, ConcertDraft, ConcertArtistDraft, SetlistItemDraft = _contribution_models()
    draft = db.session.get(ConcertDraft, draft_id)
    if not draft:
        abort(404)
    if draft.status != "submitted":
        return jsonify({
            "error": f"Only submitted drafts can be rejected; status is {draft.status!r}",
        }), 409

    draft.status = "rejected"
    db.session.commit()
    return jsonify({"draft_id": draft.id, "status": draft.status})


@review_bp.route("/setlist-drafts/<int:item_id>", methods=["PATCH"])
def patch_setlist_item_draft(item_id: int):
    """
    Body (all optional):
      piece_id           — existing piece id, or null to unlink
      piece_name         — display/name when unlinked or creating later
      timestamp_seconds  — int >= 0
      sequence_number    — int >= 1 (must be unique within concert draft)
    """
    (
        db, Concert, Artist, Raga, Talam, Composer, Piece,
        ConcertArtist, SetlistItem, ConcertDraft, ConcertArtistDraft, SetlistItemDraft,
    ) = _contribution_models()

    item = db.session.get(SetlistItemDraft, item_id)
    if not item:
        abort(404)

    draft = db.session.get(ConcertDraft, item.concert_draft_id)
    if draft and draft.status != "submitted":
        return jsonify({
            "error": f"Only submitted drafts can be edited; status is {draft.status!r}",
        }), 409

    data = request.get_json(force=True) or {}

    if "piece_id" in data:
        piece_id = data["piece_id"]
        if piece_id is None:
            item.piece_id = None
            if "piece_name" in data:
                name = (data["piece_name"] or "").strip()
                if not name:
                    return jsonify({"error": "piece_name cannot be empty when unlinking"}), 400
                item.piece_name = name
        else:
            piece = db.session.get(Piece, piece_id)
            if not piece:
                return jsonify({"error": "piece_id not found"}), 400
            item.piece_id = piece.id
            item.piece_name = piece.name
            item.raga_id = piece.raga_id
            item.talam_id = piece.talam_id
            item.composer_id = piece.composer_id
            item.raga_name = piece.raga.name if piece.raga else item.raga_name
            item.talam_name = piece.talam.name if piece.talam else item.talam_name
            item.composer_name = (
                piece.composer.name if piece.composer else item.composer_name
            )
            item.kind = piece.kind or item.kind
    elif "piece_name" in data:
        name = (data["piece_name"] or "").strip()
        if not name:
            return jsonify({"error": "piece_name cannot be empty"}), 400
        item.piece_name = name

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
            db.session.query(SetlistItemDraft)
            .filter(
                SetlistItemDraft.concert_draft_id == item.concert_draft_id,
                SetlistItemDraft.sequence_number == seq,
                SetlistItemDraft.id != item.id,
            )
            .first()
        )
        if conflict:
            return jsonify({
                "error": f"sequence_number {seq} already used by setlist draft {conflict.id}",
            }), 400
        item.sequence_number = seq

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    db.session.refresh(item)
    return jsonify(_setlist_item_draft_summary(item))


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
    from sqlalchemy import case

    from app import ConcertArtist, Artist

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
    artist_rows = (
        db.session.query(ConcertArtist, Artist)
        .join(Artist, ConcertArtist.artist_id == Artist.id)
        .filter(ConcertArtist.concert_id == concert_id)
        .order_by(
            case((ConcertArtist.role == "main artist", 0), else_=1),
            Artist.name,
        )
        .all()
    )
    return jsonify({
        "concert": _concert_summary(concert),
        "artists": [_concert_artist_summary(ca, a) for ca, a in artist_rows],
        "items": [_setlist_item_summary(si) for si in items],
    })


@review_bp.route("/concerts/<int:concert_id>", methods=["PATCH"])
def patch_concert(concert_id: int):
    """
    Body (all optional):
      title, year, venue, duration_seconds, youtube_id
      artists — full lineup replacement:
        [{"artist_id": int|null, "artist_name": str, "role": str, "instrument": str|null}, ...]

    Artist rows resolve by artist_id when set; otherwise case-insensitive name
    match or create. Does not rename existing Artist rows.
    """
    from app import ConcertArtist

    db, Concert, Artist, *_ = _models()
    concert = db.session.get(Concert, concert_id)
    if not concert:
        abort(404)

    data = request.get_json(force=True) or {}

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify({"error": "title cannot be empty"}), 400
        concert.title = title

    if "year" in data:
        year = data["year"]
        if year is None or year == "":
            concert.year = None
        else:
            try:
                year = int(year)
            except (TypeError, ValueError):
                return jsonify({"error": "year must be an integer"}), 400
            concert.year = year

    if "venue" in data:
        venue = data["venue"]
        concert.venue = (venue or "").strip() or None

    if "duration_seconds" in data:
        duration = data["duration_seconds"]
        if duration is None or duration == "":
            concert.duration_seconds = None
        else:
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                return jsonify({"error": "duration_seconds must be an integer"}), 400
            if duration < 0:
                return jsonify({"error": "duration_seconds must be >= 0"}), 400
            concert.duration_seconds = duration

    if "youtube_id" in data:
        youtube_id = (data["youtube_id"] or "").strip()
        if not youtube_id:
            return jsonify({"error": "youtube_id cannot be empty"}), 400
        conflict = (
            db.session.query(Concert)
            .filter(Concert.youtube_id == youtube_id, Concert.id != concert.id)
            .first()
        )
        if conflict:
            return jsonify({
                "error": "A concert with this YouTube ID already exists",
                "concert_id": conflict.id,
            }), 409
        concert.youtube_id = youtube_id

    if "artists" in data:
        artists = data["artists"]
        if not isinstance(artists, list):
            return jsonify({"error": "artists must be an array"}), 400
        if not artists:
            return jsonify({"error": "at least one artist is required"}), 400

        resolved = []
        seen_keys = set()
        has_main = False
        try:
            for i, row in enumerate(artists):
                if not isinstance(row, dict):
                    return jsonify({"error": f"artist {i + 1}: invalid object"}), 400
                name = (row.get("artist_name") or "").strip()
                artist_id = row.get("artist_id") or None
                if artist_id is not None:
                    try:
                        artist_id = int(artist_id)
                    except (TypeError, ValueError):
                        return jsonify({"error": f"artist {i + 1}: artist_id must be an integer"}), 400
                role = (row.get("role") or "").strip() or "main artist"
                if role not in ALLOWED_ARTIST_ROLES:
                    return jsonify({
                        "error": f"artist {i + 1}: role must be 'main artist' or 'accompanist'",
                    }), 400
                instrument = row.get("instrument")
                instrument = (instrument or "").strip() or None

                artist = _promote_named_draft_reference(
                    db.session,
                    Artist,
                    artist_id,
                    name,
                    "artist",
                    required=True,
                )
                key = (artist.id, instrument or "", role)
                if key in seen_keys:
                    return jsonify({
                        "error": (
                            f"artist {i + 1}: duplicate lineup entry for "
                            f"{artist.name!r} with the same instrument and role"
                        ),
                    }), 400
                seen_keys.add(key)
                if role == "main artist":
                    has_main = True
                resolved.append((artist, instrument, role))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not has_main:
            return jsonify({"error": "at least one main artist is required"}), 400

        (
            db.session.query(ConcertArtist)
            .filter_by(concert_id=concert.id)
            .delete(synchronize_session=False)
        )
        for artist, instrument, role in resolved:
            db.session.add(ConcertArtist(
                concert_id=concert.id,
                artist_id=artist.id,
                instrument=instrument,
                role=role,
            ))

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    from sqlalchemy import case

    artist_rows = (
        db.session.query(ConcertArtist, Artist)
        .join(Artist, ConcertArtist.artist_id == Artist.id)
        .filter(ConcertArtist.concert_id == concert.id)
        .order_by(
            case((ConcertArtist.role == "main artist", 0), else_=1),
            Artist.name,
        )
        .all()
    )
    return jsonify({
        "concert": _concert_summary(concert),
        "artists": [_concert_artist_summary(ca, a) for ca, a in artist_rows],
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


def _promote_named_draft_reference(
    session,
    model,
    entity_id,
    submitted_name,
    label,
    *,
    required=False,
):
    """Reuse a selected catalog row, or create the contributor's new named row."""
    if entity_id:
        row = session.get(model, entity_id)
        if not row:
            raise ValueError(f"{label}_id {entity_id} does not exist")
        return row

    name = (submitted_name or "").strip()
    if not name:
        if required:
            raise ValueError(f"{label} name is required")
        return None

    from sqlalchemy import func
    row = (
        session.query(model)
        .filter(func.lower(model.name) == name.lower())
        .order_by(model.id)
        .first()
    )
    if row:
        return row

    row = model(name=name)
    session.add(row)
    session.flush()
    return row


def _promote_draft_piece(
    session,
    Piece,
    item_draft,
    *,
    raga_id,
    talam_id,
    composer_id,
):
    """Create a new contributed piece, reusing an exact catalog match if present."""
    name = (item_draft.piece_name or "").strip()
    if not name:
        raise ValueError(f"setlist item {item_draft.id}: piece name is required")

    from sqlalchemy import func
    query = session.query(Piece).filter(
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

    piece = Piece(
        name=name,
        kind=item_draft.kind,
        raga_id=raga_id,
        talam_id=talam_id,
        composer_id=composer_id,
    )
    session.add(piece)
    session.flush()
    return piece


def _normalize(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower().strip()
