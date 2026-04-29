"""Database queries for photo selection.

Uses the schema from photo_analyzer (individual columns, not JSON blob).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Iterator

from .config import settings


@dataclass
class PhotoCandidate:
    """A photo candidate for daily selection."""

    path: str
    memory_score: float
    beauty_score: float
    exif_datetime: str  # YYYY-MM-DD format
    location_json: dict[str, str] = field(default_factory=dict)  # {"zh": "深圳", "en": "Shenzhen"}
    caption_json: dict[str, str] = field(default_factory=dict)  # {"zh": "...", "en": "..."}
    enhanced_caption_json: dict[str, str] = field(default_factory=dict)  # {"zh": "...", "en": "..."}

    @property
    def date(self) -> date | None:
        """Parse exif_datetime to date object."""
        try:
            return date.fromisoformat(self.exif_datetime)
        except (ValueError, TypeError):
            return None

    @property
    def year(self) -> int | None:
        """Extract year from exif_datetime."""
        d = self.date
        return d.year if d else None

    @property
    def month_day(self) -> str | None:
        """Extract MM-DD from exif_datetime."""
        if self.exif_datetime and len(self.exif_datetime) >= 10:
            return self.exif_datetime[5:10]  # "MM-DD"
        return None


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Get database connection with automatic cleanup.

    Usage:
        with get_db() as conn:
            rows = conn.execute("SELECT ...").fetchall()
    """
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_candidate(row: sqlite3.Row) -> PhotoCandidate:
    """Convert a database row to PhotoCandidate."""
    # Parse JSON fields
    caption_json = {}
    if row["caption_json"]:
        try:
            caption_json = json.loads(row["caption_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    enhanced_caption_json = {}
    if "enhanced_caption_json" in row.keys() and row["enhanced_caption_json"]:
        try:
            enhanced_caption_json = json.loads(row["enhanced_caption_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    location_json = {}
    if row["location_json"]:
        try:
            location_json = json.loads(row["location_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    return PhotoCandidate(
        path=row["path"],
        memory_score=row["memory_score"] or 0.0,
        beauty_score=row["beauty_score"] or 0.0,
        exif_datetime=row["exif_datetime"] or "",
        location_json=location_json,
        caption_json=caption_json,
        enhanced_caption_json=enhanced_caption_json,
    )


def get_photos_for_month_day(
    month: int,
    day: int,
    min_memory_score: float | None = None,
) -> list[PhotoCandidate]:
    """Get all photos for a specific MM-DD with memory score above threshold.

    Results are sorted by year (descending) and memory_score (descending).
    """
    if min_memory_score is None:
        min_memory_score = settings.memory_threshold

    pattern = f"%-{month:02d}-{day:02d}"

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT path, memory_score, beauty_score, exif_datetime, location_json, caption_json, enhanced_caption_json
            FROM photo_records
            WHERE exif_datetime LIKE ?
              AND memory_score >= ?
              AND exif_datetime IS NOT NULL
            ORDER BY exif_datetime DESC, memory_score DESC
            """,
            (pattern, min_memory_score),
        ).fetchall()

    return [_row_to_candidate(row) for row in rows]


def get_photo_by_path(path: str) -> PhotoCandidate | None:
    """Get a single photo by its path."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT path, memory_score, beauty_score, exif_datetime, location_json, caption_json, enhanced_caption_json
            FROM photo_records
            WHERE path = ?
            """,
            (path,),
        ).fetchone()

    if not row:
        return None

    return _row_to_candidate(row)


def count_photos() -> int:
    """Count total photos in database."""
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM photo_records").fetchone()[0]


def get_available_month_days() -> list[str]:
    """Get list of all MM-DD values that have photos with exif_datetime."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT substr(exif_datetime, 6, 5) as md
            FROM photo_records
            WHERE exif_datetime IS NOT NULL AND length(exif_datetime) >= 10
            ORDER BY md
            """
        ).fetchall()

    return [row["md"] for row in rows if row["md"]]


def update_enhanced_caption(
    conn: sqlite3.Connection,
    path: str,
    lang: str,
    caption: str,
) -> None:
    """Update enhanced_caption_json for a specific photo and language.

    Args:
        conn: Database connection
        path: Photo path (primary key)
        lang: Language code (e.g., 'zh', 'en')
        caption: Enhanced caption text
    """
    # Get existing enhanced_caption_json
    row = conn.execute(
        "SELECT enhanced_caption_json FROM photo_records WHERE path = ?",
        (path,),
    ).fetchone()

    if not row:
        return

    # Parse existing or start fresh
    existing = {}
    if row[0]:
        try:
            existing = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            pass

    # Update the language
    existing[lang] = caption

    # Save back
    conn.execute(
        "UPDATE photo_records SET enhanced_caption_json = ? WHERE path = ?",
        (json.dumps(existing, ensure_ascii=False), path),
    )
    conn.commit()
