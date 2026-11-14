"""HTTP API: generic CRUD, workflows, and the admin review shell."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, render_template

from api.auth import admin_auth_response
from api.crud import register_crud
from api.workflows import register_workflows
from repo import (
    artists,
    composers,
    concert_artist_drafts,
    concert_artists,
    concert_drafts,
    concerts,
    ingest_drafts,
    piece_aliases,
    pieces,
    ragas,
    setlist_item_drafts,
    setlist_items,
    talams,
)

_APP_DIR = Path(__file__).resolve().parent.parent

# (url path, repo, public GET + autocomplete)
_ENTITIES = (
    ("concerts", concerts, True),
    ("artists", artists, True),
    ("composers", composers, True),
    ("ragas", ragas, True),
    ("talams", talams, True),
    ("pieces", pieces, True),
    ("concert-artists", concert_artists, True),
    ("setlist-items", setlist_items, True),
    ("piece-aliases", piece_aliases, False),
    ("concert-drafts", concert_drafts, False),
    ("setlist-item-drafts", setlist_item_drafts, False),
    ("concert-artist-drafts", concert_artist_drafts, False),
    ("ingest-drafts", ingest_drafts, False),
)

# admin review SPA: /review/ and /review/static/<file> from app/templates and app/static
review_bp = Blueprint(
    "review",
    __name__,
    url_prefix="/review",
    template_folder=str(_APP_DIR / "templates"),
    static_folder=str(_APP_DIR / "static"),
    static_url_path="/static",
)


def register_api(app, limiter):
    """Register CRUD resources, workflows, and the /review/ shell."""
    for path, repo, public_read in _ENTITIES:
        register_crud(app, path, repo, public_read, limiter)
    register_workflows(app, limiter)
    app.register_blueprint(review_bp)


@review_bp.route("/")
def review_index():
    return render_template("review.html")


@review_bp.before_request
def _review_admin():
    return admin_auth_response()
