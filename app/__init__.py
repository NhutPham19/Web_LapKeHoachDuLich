from flask import Flask, jsonify, render_template
from . import config


def create_app(repo=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DATABASE_URL"] = config.DATABASE_URL
    app.config["OPENWEATHER_API_KEY"] = config.OPENWEATHER_API_KEY

    if repo is None:
        from .db import PgRepo
        app.repo = PgRepo()
    else:
        app.repo = repo

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

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
