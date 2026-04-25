"""Flask server for ESP32 download endpoints.

Usage:
    python -m server
    uv run server
"""

from .app import create_app
from .config import settings

__all__ = ["create_app", "settings"]
