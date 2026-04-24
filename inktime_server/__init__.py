"""InkTime Flask server for ESP32 e-ink photo frame.

Provides on-demand photo rendering and ESP32 download endpoints.

Usage:
    python -m inktime_server

Or with uv:
    uv run inktime_server
"""

from .app import create_app
from .config import settings

__all__ = ["create_app", "settings"]
