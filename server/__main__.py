"""CLI entry point for the Flask server.

Usage:
    python -m server
    uv run server
"""

from .app import create_app
from .cache import cache
from .config import settings


def main() -> None:
    """Run the Flask development server."""
    app = create_app()

    print(f"[InkTime] Starting server...")
    print(f"[InkTime] Host: {settings.flask_host}")
    print(f"[InkTime] Port: {settings.flask_port}")

    # Warm up cache at startup for proactive error detection
    try:
        cache.get_all()
        print(f"[InkTime] Cache ready: {cache.count} photos")
    except Exception as e:
        print(f"[InkTime] Warning: Cache warmup failed: {e}")

    app.run(
        host=settings.flask_host,
        port=settings.flask_port,
        debug=settings.debug,
    )


if __name__ == "__main__":
    main()
