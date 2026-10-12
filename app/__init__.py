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
        app.config["PREFERRED_URL_SCHEME"] = "https"
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        except Exception:
            pass

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

    def destination_img_url(dest, width=640) -> str:
        """
        Helper Jinja2 render ảnh cho điểm đến:
        1. Có image_public_id và CLOUDINARY_CLOUD_NAME: dùng Cloudinary transform URL.
        2. Không có public_id nhưng có image_url hợp lệ (bắt đầu bằng http): dùng image_url cũ.
        3. Fallback theo 4 category của hệ thống (1: Thiên nhiên, 2: Văn hóa, 3: Ẩm thực, 4: Giải trí).
        """
        cloud_name = config.CLOUDINARY_CLOUD_NAME
        pub_id = getattr(dest, "image_public_id", None) or (dest.get("image_public_id") if isinstance(dest, dict) else None)
        if pub_id and cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/c_fill,ar_16:9,g_auto,f_auto,q_auto,w_{width}/{pub_id}"

        img_url = getattr(dest, "image_url", "") or (dest.get("image_url", "") if isinstance(dest, dict) else "")
        if img_url and str(img_url).startswith("http"):
            return str(img_url)

        cat_id = getattr(dest, "category_id", 0) or (dest.get("category_id", 0) if isinstance(dest, dict) else 0)
        cat_map = {
            1: "/static/images/placeholders/thien_nhien.svg",
            2: "/static/images/placeholders/van_hoa.svg",
            3: "/static/images/placeholders/am_thuc.svg",
            4: "/static/images/placeholders/giai_tri.svg",
        }
        return cat_map.get(cat_id, "/static/images/placeholders/default.svg")

    app.jinja_env.globals["dest_img_url"] = destination_img_url

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

    @app.errorhandler(404)
    def handle_not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found", "message": "Tài nguyên không tồn tại"}), 404
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def handle_server_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "internal_error", "message": "Lỗi máy chủ nội bộ"}), 500
        return render_template("500.html"), 500

    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    from .routes.ratings import ratings_bp
    from .routes.trips import trips_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(trips_bp)
    app.register_blueprint(ratings_bp)
    app.register_blueprint(admin_bp)

    return app

