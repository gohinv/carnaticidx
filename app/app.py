"""Flask entrypoint: config, extensions, API routes, and the public index page.

Run with gunicorn as ``app:app``; ingest scripts use ``from app import app``.
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

from api import register_api
from dbmodel import db

REQUIRED_PRODUCTION_ENV = (
    "DATABASE_URI",
    "SECRET_KEY",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
)

limiter = Limiter(key_func=get_remote_address, default_limits=[])
migrate = Migrate()


def create_app() -> Flask:
    load_dotenv()
    is_production = _is_production()
    if is_production:
        _require_env(REQUIRED_PRODUCTION_ENV)

    app = Flask(
        __name__,
        template_folder='../client',
        static_folder='../client',
        static_url_path='',
    )
    _configure(app, is_production)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    register_api(app, limiter)
    app.add_url_rule('/', 'index', _index)
    app.register_error_handler(429, _rate_limit_exceeded)

    if is_production:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    return app


def _is_production() -> bool:
    return os.getenv("FLASK_ENV") == "production"


def _require_env(names):
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


def _configure(app: Flask, is_production: bool) -> None:
    if is_production:
        app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    else:
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-only')
    app.config['TEMPLATES_AUTO_RELOAD'] = not is_production
    app.jinja_env.auto_reload = not is_production
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')
    app.config['RATELIMIT_STORAGE_URI'] = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')


def _index():
    return render_template(
        'index.html',
        turnstile_site_key=os.getenv('TURNSTILE_SITE_KEY', ''),
        turnstile_disabled=os.getenv('TURNSTILE_DISABLED') == '1',
    )


def _rate_limit_exceeded(_error):
    return jsonify({"error": "Too many requests. Please try again later."}), 429


app = create_app()

if __name__ == '__main__':
    app.run(debug=not _is_production())
