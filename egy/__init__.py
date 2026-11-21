"""EgyFreelancers application factory."""
import os
from pathlib import Path
from flask import Flask
from . import db, security


def create_app(test_config=None):
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, instance_path=str(root / "instance"), template_folder=str(root / "templates"), static_folder=str(root / "static"))
    env = os.environ.get("EGY_ENV", "development")
    prod = env == "production"

    app.config.update(
        ENV_NAME=env,
        SECRET_KEY=os.environ.get("EGY_SECRET_KEY", ""),
        MASTER_KEY=os.environ.get("EGY_MASTER_KEY", ""),
        DB_PATH=os.environ.get("EGY_DB_PATH", str(root / "instance" / "egyfreelancers.db")),
        UPLOAD_DIR=os.environ.get("EGY_UPLOAD_DIR", str(root / "instance" / "uploads")),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        SESSION_COOKIE_NAME="__Host-egy" if prod else "egy",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=prod,
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
        JSON_SORT_KEYS=False,
        TESTING=False,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    if not app.config["SECRET_KEY"] or not app.config["MASTER_KEY"]:
        if prod:
            raise RuntimeError("EGY_SECRET_KEY and EGY_MASTER_KEY must be set in production.")
        # Dev only: persistent random keys kept in instance/ so data survives restarts.
        security.load_dev_keys(app)

    hops = int(os.environ.get("EGY_TRUSTED_PROXIES", "0"))
    if hops:  # behind nginx/Cloudflare: trust exactly N proxy hops so rate limits see the real client IP
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    security.init_crypto(app)
    db.init_app(app)
    security.init_app(app)

    from . import routes_public, routes_auth, routes_api, routes_account, routes_admin
    for m in (routes_public, routes_auth, routes_api, routes_account, routes_admin):
        app.register_blueprint(m.bp)

    @app.context_processor
    def shared():
        from .constants import CATEGORIES, PAYMENTS
        return {"categories": CATEGORIES, "payments": PAYMENTS}

    return app
