"""CLI entry point for running the InkTime server.

Usage:
    python -m inktime_server
    uv run inktime_server
"""

from .app import create_app
from .config import settings


def main() -> None:
    """Run the Flask development server."""
    app = create_app()

    print(f"[InkTime] Starting server...")
    print(f"[InkTime] Host: {settings.flask_host}")
    print(f"[InkTime] Port: {settings.flask_port}")
    print(f"[InkTime] API: http://{settings.flask_host}:{settings.flask_port}/api/photo/0")

    app.run(
        host=settings.flask_host,
        port=settings.flask_port,
        debug=settings.debug,
    )


if __name__ == "__main__":
    main()
