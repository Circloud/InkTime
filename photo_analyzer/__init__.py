"""Photo analysis package for InkTime e-ink photo frame.

This package provides photo analysis functionality including:
- VLM-powered photo scoring and captioning
- EXIF metadata extraction
- GPS to city name resolution
- SQLite database storage

Usage:
    python -m photo_analyzer

Or with uv:
    uv run photo_analyzer
"""

from .config import settings
from .models import ExifInfo, PhotoRecord, VlmResponse

__all__ = ["settings", "ExifInfo", "PhotoRecord", "VlmResponse"]
