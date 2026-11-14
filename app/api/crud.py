"""Generic JSON CRUD routes over a ``Repo``."""

from __future__ import annotations

from flask import jsonify, request

from api.auth import require_admin
from repo import ConflictError, NamedRepo, NotFoundError

PUBLIC_READ_LIMIT = "600 per minute"
DEFAULT_LIMIT = 200
MAX_LIMIT = 2000
_RESERVED_ARGS = frozenset({"limit", "offset", "order_by"})


def row_to_dict(row) -> dict:
    """Column values only; relationships are not expanded."""
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


def register_crud(app, path: str, repo, public_read: bool, limiter):
    """Register list/create/update/delete, plus autocomplete for named repos.

    ``strict_slashes=False`` so ``/concerts`` and ``/concerts/`` both work.
    """
    slug = path.replace("-", "_")

    def create_row():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400
        try:
            row = repo.create(**data)
        except ValueError as exc:
            return _json_error(exc, 400)
        except ConflictError as exc:
            return _json_error(exc, 409)
        return jsonify(row_to_dict(row)), 201

    def list_rows():
        try:
            raw_limit = request.args.get("limit")
            limit = (
                DEFAULT_LIMIT if raw_limit is None
                else _parse_non_negative_int(raw_limit, "limit")
            )
            if limit > MAX_LIMIT:
                limit = MAX_LIMIT
            raw_offset = request.args.get("offset")
            offset = (
                0 if raw_offset is None
                else _parse_non_negative_int(raw_offset, "offset")
            )
            order_by = request.args.get("order_by") or None
            filters = {
                key: request.args.getlist(key)
                for key in request.args
                if key not in _RESERVED_ARGS
            }
            rows = repo.list(
                filters,
                limit=limit,
                offset=offset,
                order_by=order_by,
            )
        except ValueError as exc:
            return _json_error(exc, 400)
        return jsonify([row_to_dict(row) for row in rows])

    def update_row(row_id: int):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400
        try:
            row = repo.update(row_id, **data)
        except ValueError as exc:
            return _json_error(exc, 400)
        except NotFoundError as exc:
            return _json_error(exc, 404)
        except ConflictError as exc:
            return _json_error(exc, 409)
        return jsonify(row_to_dict(row))

    def delete_row(row_id: int):
        # Snapshot before delete: commit expires the instance, and a
        # deleted row cannot be refreshed.
        try:
            found = repo.get_many([row_id])
            if not found:
                raise NotFoundError(
                    f"{repo.model.__tablename__} {row_id} not found"
                )
            payload = row_to_dict(found[0])
            repo.delete(row_id)
        except NotFoundError as exc:
            return _json_error(exc, 404)
        except ConflictError as exc:
            return _json_error(exc, 409)
        return jsonify(payload)

    create_row.__name__ = f"create_{slug}"
    list_rows.__name__ = f"list_{slug}"
    update_row.__name__ = f"update_{slug}"
    delete_row.__name__ = f"delete_{slug}"

    create_view = require_admin(create_row)
    update_view = require_admin(update_row)
    delete_view = require_admin(delete_row)
    list_view = list_rows
    if public_read:
        list_view = limiter.limit(PUBLIC_READ_LIMIT)(list_rows)
    else:
        list_view = require_admin(list_rows)

    collection = f"/{path}/"
    app.add_url_rule(
        collection,
        endpoint=f"create_{slug}",
        view_func=create_view,
        methods=["POST"],
        strict_slashes=False,
    )
    app.add_url_rule(
        collection,
        endpoint=f"list_{slug}",
        view_func=list_view,
        methods=["GET"],
        strict_slashes=False,
    )
    app.add_url_rule(
        f"/{path}/<int:row_id>",
        endpoint=f"update_{slug}",
        view_func=update_view,
        methods=["PUT"],
        strict_slashes=False,
    )
    app.add_url_rule(
        f"/{path}/<int:row_id>",
        endpoint=f"delete_{slug}",
        view_func=delete_view,
        methods=["DELETE"],
        strict_slashes=False,
    )

    if not isinstance(repo, NamedRepo):
        return

    def autocomplete(prefix: str):
        try:
            raw_limit = request.args.get("limit")
            limit = (
                10 if raw_limit is None
                else _parse_non_negative_int(raw_limit, "limit")
            )
            rows = repo.autocomplete(prefix, limit=limit)
        except ValueError as exc:
            return _json_error(exc, 400)
        return jsonify([row_to_dict(row) for row in rows])

    autocomplete.__name__ = f"autocomplete_{slug}"
    autocomplete_view = autocomplete
    if public_read:
        autocomplete_view = limiter.limit(PUBLIC_READ_LIMIT)(autocomplete)
    else:
        autocomplete_view = require_admin(autocomplete)
    app.add_url_rule(
        f"/{path}/autocomplete/<string:prefix>",
        endpoint=f"autocomplete_{slug}",
        view_func=autocomplete_view,
        methods=["GET"],
        strict_slashes=False,
    )


def _json_error(exc, status: int):
    return jsonify({"error": str(exc)}), status


def _parse_non_negative_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value
