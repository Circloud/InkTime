"""Flask application factory.

Creates and configures the Flask application with all blueprints.
"""

from flask import Flask, Response

from .config import settings
from .routes import api_bp


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(api_bp)

    # Add security headers
    @app.after_request
    def add_headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # Health check
    @app.route("/health")
    def health() -> dict:
        return {"status": "healthy"}

    # Root info
    @app.route("/")
    def index() -> dict:
        return {
            "name": "InkTime Server",
            "version": "2.0.0",
            "endpoints": {
                "photo": "/api/photo",
                "status": "/api/status",
                "health": "/health",
            },
        }

    return app
