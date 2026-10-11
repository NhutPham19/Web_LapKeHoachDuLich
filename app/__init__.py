import secrets
from flask import Flask, jsonify, render_template, request, session
from . import config


def create_app(repo=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DATABASE_URL"] = config.DATABASE_URL
    app.config["OPENWEATHER_API_KEY"] = config.OPENWEATHER_API_KEY

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if config.IS_PRODUCTION:
        app.config["SESSION_COOKIE_SECURE"] = True

    if repo is None:
        from .db import PgRepo
        app.repo = PgRepo()
    else:
        app.repo = repo

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.context_processor
    def inject_csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"]}

    @app.before_request
    def check_csrf():
        # Đảm bảo session có csrf_token nếu chưa có
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            expected = session.get("csrf_token")
            if not expected or not token or not secrets.compare_digest(token, expected):
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({"error": "CSRF token không hợp lệ hoặc đã hết hạn"}), 403
                return render_template("login.html", error="Phiên làm việc hết hạn hoặc token CSRF không hợp lệ"), 403

    @app.get("/health")
    def health():
        try:
            if hasattr(app.repo, "ping_db") and app.repo.ping_db():
                return jsonify({"status": "ok", "db": "connected"}), 200
            return jsonify({"status": "error", "db": "disconnected"}), 503
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 503

    @app.get("/")
    def index():
        return render_template("index.html")

    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    from .routes.ratings import ratings_bp
    from .routes.trips import trips_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(trips_bp)
    app.register_blueprint(ratings_bp)
    app.register_blueprint(admin_bp)

    return app

