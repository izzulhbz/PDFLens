"""HTTP API: one Flask blueprint per area."""

from flask import Flask

from app.api import auth, health


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
