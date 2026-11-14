"""Admin HTTP Basic Auth.

Moved from the review blueprint. The realm stays ``Review`` so browsers
reuse cached credentials.
"""

from __future__ import annotations

import os
import secrets
from functools import wraps

from flask import Response, request


def admin_auth_response():
    """Return an error response when admin auth fails, else None."""
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
    return None


def require_admin(view):
    """Require ``ADMIN_USERNAME`` / ``ADMIN_PASSWORD`` basic auth."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        denied = admin_auth_response()
        if denied is not None:
            return denied
        return view(*args, **kwargs)
    return wrapper


def _unauthorized():
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Review"'},
    )
