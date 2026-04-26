"""SQLite database operations for photo scores."""

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
    caption           TEXT,

    -- Image dimensions (from PIL Image.size, NOT from EXIF)
    width             INTEGER,
    height            INTEGER,

    -- EXIF fields (directly extracted from image metadata)
    exif_datetime     TEXT,
    exif_model        TEXT,
    exif_gps_lat      REAL,
    exif_gps_lon      REAL,

    -- Computed field (NOT from EXIF)
    location_city     TEXT
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
        (path, description, photo_type, memory_score, beauty_score, reason, caption,
         width, height, exif_datetime, exif_model, exif_gps_lat, exif_gps_lon, location_city)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.path,
            record.description,
            record.photo_type,
            record.memory_score,
            record.beauty_score,
            record.reason,
            record.caption,
            record.width,
            record.height,
            record.exif_datetime,
            record.exif_model,
            record.exif_gps_lat,
            record.exif_gps_lon,
            record.location_city,
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


def count_records(conn: sqlite3.Connection, prefix: str) -> int:
    """Count records with paths starting with the given prefix."""
    row = conn.execute(
        "SELECT COUNT(*) FROM photo_records WHERE path LIKE ?",
        (prefix + "%",),
    ).fetchone()
    return row[0] if row else 0


def delete_orphaned_records(
    conn: sqlite3.Connection,
    existing_paths: list[str],
    prefix: str,
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

    before = count_records(conn, prefix)

    conn.execute(
        """
        DELETE FROM photo_records
        WHERE path LIKE ?
          AND NOT EXISTS (
                SELECT 1 FROM _temp_existing_paths t
                WHERE t.path = photo_records.path
          )
        """,
        (prefix + "%",),
    )
    conn.commit()

    after = count_records(conn, prefix)
    return before - after


def init_database(db_path: Path) -> sqlite3.Connection:
    """Initialize database connection and create table if needed."""
    conn = sqlite3.connect(db_path)
    ensure_table(conn)
    logger.info(f"Database initialized: {db_path}")
    return conn
