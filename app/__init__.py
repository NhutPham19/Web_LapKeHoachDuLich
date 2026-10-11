from flask import Flask, jsonify
from . import config


def create_app(repo=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DATABASE_URL"] = config.DATABASE_URL
    app.config["OPENWEATHER_API_KEY"] = config.OPENWEATHER_API_KEY
    app.repo = repo

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
