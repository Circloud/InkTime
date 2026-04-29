"""SQLite database operations for photo scores."""

import json
import logging
import sqlite3
from pathlib import Path

from .models import PhotoRecord

logger = logging.getLogger(__name__)

# SQL schema for photo_records table
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS photo_records (
    -- Primary key
    path              TEXT PRIMARY KEY,

    -- VLM-generated content
    description       TEXT,
    photo_type        TEXT,
    memory_score      REAL,
    beauty_score      REAL,
    reason            TEXT,
    caption_json      TEXT,  -- JSON: {"zh": "...", "en": "..."}
    enhanced_caption_json TEXT,  -- JSON: {"zh": "...", "en": "..."}

    -- Image dimensions (from PIL Image.size, NOT from EXIF)
    width             INTEGER,
    height            INTEGER,

    -- EXIF fields (directly extracted from image metadata)
    exif_datetime     TEXT,
    exif_model        TEXT,
    exif_gps_lat      REAL,
    exif_gps_lon      REAL,

    -- Computed field (NOT from EXIF)
    location_json     TEXT  -- JSON: {"zh": "深圳", "en": "Shenzhen"}
)
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create the photo_records table if it doesn't exist."""
    conn.execute(SCHEMA_SQL)
    conn.commit()
    logger.debug("Database table ensured")


def save_photo(conn: sqlite3.Connection, record: PhotoRecord) -> None:
    """Insert or replace a photo record in the database."""
    conn.execute(
        """
        INSERT OR REPLACE INTO photo_records
        (path, description, photo_type, memory_score, beauty_score, reason, caption_json,
         enhanced_caption_json, width, height, exif_datetime, exif_model, exif_gps_lat, exif_gps_lon, location_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.path,
            record.description,
            record.photo_type,
            record.memory_score,
            record.beauty_score,
            record.reason,
            json.dumps(record.caption_json, ensure_ascii=False) if record.caption_json else None,
            json.dumps(record.enhanced_caption_json, ensure_ascii=False) if record.enhanced_caption_json else None,
            record.width,
            record.height,
            record.exif_datetime,
            record.exif_model,
            record.exif_gps_lat,
            record.exif_gps_lon,
            json.dumps(record.location_json, ensure_ascii=False) if record.location_json else None,
        ),
    )
    conn.commit()


def get_analyzed_paths(conn: sqlite3.Connection, paths: list[str]) -> set[str]:
    """Get the set of paths that already have records in the database."""
    if not paths:
        return set()

    placeholders = ",".join("?" for _ in paths)
    rows = conn.execute(
        f"SELECT path FROM photo_records WHERE path IN ({placeholders})",
        paths,
    ).fetchall()
    return {row[0] for row in rows}


def get_photos_missing_language(conn: sqlite3.Connection, lang: str) -> list[str]:
    """Find photo paths that don't have a caption in the specified language.

    Args:
        conn: Database connection
        lang: Language code to check (e.g., 'zh', 'en')

    Returns:
        List of paths missing the specified language caption
    """
    rows = conn.execute(
        """
        SELECT path FROM photo_records
        WHERE caption_json IS NULL
           OR json_extract(caption_json, ?) IS NULL
        """,
        (f'$.{lang}',),
    ).fetchall()
    return [row[0] for row in rows]


def count_records(conn: sqlite3.Connection) -> int:
    """Count total records in database."""
    row = conn.execute("SELECT COUNT(*) FROM photo_records").fetchone()
    return row[0] if row else 0


def delete_orphaned_records(
    conn: sqlite3.Connection,
    existing_paths: list[str],
) -> int:
    """Delete records that no longer have corresponding files on disk.

    Returns the number of deleted records.
    """
    conn.execute("DROP TABLE IF EXISTS _temp_existing_paths")
    conn.execute("CREATE TEMP TABLE _temp_existing_paths (path TEXT PRIMARY KEY)")

    # Batch insert
    chunk_size = 2000
    for i in range(0, len(existing_paths), chunk_size):
        chunk = existing_paths[i : i + chunk_size]
        conn.executemany(
            "INSERT OR IGNORE INTO _temp_existing_paths(path) VALUES (?)",
            [(p,) for p in chunk],
        )

    before = count_records(conn)

    conn.execute(
        """
        DELETE FROM photo_records
        WHERE NOT EXISTS (
                SELECT 1 FROM _temp_existing_paths t
                WHERE t.path = photo_records.path
          )
        """
    )
    conn.commit()

    after = count_records(conn)
    return before - after


def init_database(db_path: Path) -> sqlite3.Connection:
    """Initialize database connection and create table if needed."""
    conn = sqlite3.connect(db_path)
    ensure_table(conn)
    logger.info(f"Database initialized: {db_path}")
    return conn
