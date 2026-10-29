import os
from datetime import timedelta

from flask import Flask

from . import auth, db, views


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    produzione = os.environ.get("SCADENZO_ENV") == "production"
    secret = os.environ.get("SECRET_KEY")
    if produzione and not secret:
        raise RuntimeError("In produzione serve la variabile d'ambiente SECRET_KEY.")

    app.config.update(
        SECRET_KEY=secret or "solo-per-sviluppo-locale",
        DATABASE=os.environ.get(
            "DATABASE_PATH", os.path.join(app.instance_path, "scadenzo.sqlite")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=produzione,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    if config:
        app.config.update(config)

    app.teardown_appcontext(db.close_db)
    app.before_request(auth.carica_utente)
    app.before_request(auth.verifica_csrf)
    app.jinja_env.globals["csrf_token"] = auth.csrf_token

    @app.after_request
    def intestazioni_sicurezza(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'")
        return resp

    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)

    with app.app_context():
        db.init_db()

    return app
