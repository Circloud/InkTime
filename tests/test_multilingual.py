"""Tests for multilingual support."""

import json
import sqlite3
from pathlib import Path

import pytest

from photo_analyzer.models import PhotoRecord
from server.composition import format_date_display
from server.database import PhotoCandidate


class TestDateFormatting:
    """Tests for language-specific date formatting."""

    def test_chinese_numeric_format(self):
        """Chinese should use numeric format: YYYY.M.D"""
        result = format_date_display("2026-04-27", lang="zh")
        assert result == "2026.4.27"

    def test_english_short_format(self):
        """English should use short format: Mon D, YYYY"""
        result = format_date_display("2026-04-27", lang="en")
        assert result == "Apr 27, 2026"

    def test_invalid_date_too_short_returns_empty(self):
        """Date string too short (< 10 chars) should return empty."""
        result = format_date_display("invalid", lang="zh")
        assert result == ""

    def test_invalid_date_format_returns_original(self):
        """Invalid date format (correct length but wrong format) should return original."""
        result = format_date_display("not-a-date!", lang="zh")
        assert result == "not-a-date!"

    def test_empty_date_returns_empty(self):
        """Empty date string should return empty."""
        result = format_date_display("", lang="zh")
        assert result == ""


class TestPhotoRecordJsonFields:
    """Tests for JSON field handling in PhotoRecord."""

    def test_caption_json_serialization(self):
        """Caption JSON should store multiple languages."""
        record = PhotoRecord(
            path="/test/photo.jpg",
            caption_json={"zh": "美好回忆", "en": "Sweet memories"},
        )
        assert record.caption_json["zh"] == "美好回忆"
        assert record.caption_json["en"] == "Sweet memories"

    def test_location_json_serialization(self):
        """Location JSON should store multiple languages."""
        record = PhotoRecord(
            path="/test/photo.jpg",
            location_json={"zh": "深圳", "en": "Shenzhen"},
        )
        assert record.location_json["zh"] == "深圳"
        assert record.location_json["en"] == "Shenzhen"

    def test_from_analysis_with_json_fields(self):
        """from_analysis should accept JSON fields."""
        from photo_analyzer.models import VlmResponse, ExifInfo

        vlm = VlmResponse(
            description="A test photo",
            photo_type="风景",
            memory_score=85.0,
            beauty_score=90.0,
            reason="Beautiful landscape",
        )
        exif = ExifInfo(width=1920, height=1080, datetime="2024:07:15 10:30:00")

        record = PhotoRecord.from_analysis(
            path="/test/photo.jpg",
            vlm_response=vlm,
            exif_info=exif,
            caption_json={"zh": "测试", "en": "Test"},
            location_json={"zh": "深圳", "en": "Shenzhen"},
        )

        assert record.caption_json == {"zh": "测试", "en": "Test"}
        assert record.location_json == {"zh": "深圳", "en": "Shenzhen"}


class TestDatabaseJsonQueries:
    """Tests for JSON field queries in SQLite."""

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> sqlite3.Connection:
        """Create a temporary database with JSON fields."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE photo_records (
                path TEXT PRIMARY KEY,
                caption_json TEXT,
                location_json TEXT
            )
        """)
        conn.commit()
        yield conn
        conn.close()

    def test_save_and_load_json_fields(self, temp_db: sqlite3.Connection):
        """JSON fields should be saved and loaded correctly."""
        record = PhotoRecord(
            path="/test/photo.jpg",
            caption_json={"zh": "测试", "en": "Test"},
            location_json={"zh": "深圳", "en": "Shenzhen"},
        )

        # Save
        temp_db.execute(
            "INSERT INTO photo_records (path, caption_json, location_json) VALUES (?, ?, ?)",
            (
                record.path,
                json.dumps(record.caption_json, ensure_ascii=False),
                json.dumps(record.location_json, ensure_ascii=False),
            ),
        )
        temp_db.commit()

        # Load
        row = temp_db.execute(
            "SELECT caption_json, location_json FROM photo_records WHERE path = ?",
            ("/test/photo.jpg",),
        ).fetchone()

        caption_json = json.loads(row[0])
        location_json = json.loads(row[1])

        assert caption_json["zh"] == "测试"
        assert caption_json["en"] == "Test"
        assert location_json["zh"] == "深圳"

    def test_find_missing_language(self, temp_db: sqlite3.Connection):
        """Should find photos missing a specific language caption."""
        # Insert photos with different language coverage
        temp_db.execute(
            "INSERT INTO photo_records (path, caption_json) VALUES (?, ?)",
            ("/photo1.jpg", json.dumps({"zh": "测试", "en": "Test"})),
        )
        temp_db.execute(
            "INSERT INTO photo_records (path, caption_json) VALUES (?, ?)",
            ("/photo2.jpg", json.dumps({"zh": "只有中文"})),
        )
        temp_db.execute(
            "INSERT INTO photo_records (path, caption_json) VALUES (?, ?)",
            ("/photo3.jpg", json.dumps({"en": "English only"})),
        )
        temp_db.commit()

        # Find photos missing English
        rows = temp_db.execute(
            """
            SELECT path FROM photo_records
            WHERE caption_json IS NULL
               OR json_extract(caption_json, '$.en') IS NULL
            """
        ).fetchall()
        missing_en = [row[0] for row in rows]

        assert "/photo2.jpg" in missing_en
        assert "/photo1.jpg" not in missing_en
        assert "/photo3.jpg" not in missing_en


class TestPhotoCandidateLanguageExtraction:
    """Tests for language extraction from PhotoCandidate."""

    def test_get_caption_for_language(self):
        """Should get caption for specific language."""
        candidate = PhotoCandidate(
            path="/test/photo.jpg",
            memory_score=85.0,
            beauty_score=90.0,
            exif_datetime="2024-07-15",
            caption_json={"zh": "测试", "en": "Test"},
            location_json={"zh": "深圳", "en": "Shenzhen"},
        )

        assert candidate.caption_json.get("zh") == "测试"
        assert candidate.caption_json.get("en") == "Test"

    def test_fallback_to_first_language(self):
        """Should fallback to first available language if requested language missing."""
        candidate = PhotoCandidate(
            path="/test/photo.jpg",
            memory_score=85.0,
            beauty_score=90.0,
            exif_datetime="2024-07-15",
            caption_json={"zh": "只有中文"},
            location_json={"zh": "深圳"},
        )

        # Request English, but only Chinese available
        caption = candidate.caption_json.get("en", "") or next(iter(candidate.caption_json.values()), "")
        assert caption == "只有中文"
