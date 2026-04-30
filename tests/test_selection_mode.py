"""Tests for selection mode configuration and behavior."""

import pytest
from pathlib import Path
from pydantic import ValidationError

from photo_analyzer.config import Settings
from server.config import ServerSettings


class TestConfigValidation:
    """Test configuration validation for selection_mode."""

    def test_missing_selection_mode_raises_error(self):
        """Missing SELECTION_MODE should raise ValidationError."""
        # Create Settings without reading from .env file
        # _env_file=None disables reading from .env
        with pytest.raises(ValidationError, match="SELECTION_MODE is required"):
            Settings(_env_file=None, image_dirs_str="./photos")

    def test_invalid_selection_mode_raises_error(self):
        """Invalid SELECTION_MODE value should raise ValidationError."""
        with pytest.raises(ValidationError):
            Settings(selection_mode="invalid", image_dirs_str="./photos")

    def test_date_mode_requires_image_dirs(self):
        """Date mode with empty IMAGE_DIRS should raise error."""
        with pytest.raises(ValidationError, match="IMAGE_DIRS is required"):
            Settings(selection_mode="date", image_dirs_str="")

    def test_curated_mode_requires_curated_dirs(self):
        """Curated mode with empty CURATED_DIRS should raise error."""
        with pytest.raises(ValidationError, match="CURATED_DIRS is required"):
            Settings(selection_mode="curated", curated_dirs_str="")

    def test_date_mode_config_valid(self):
        """Date mode with IMAGE_DIRS should be valid."""
        settings = Settings(
            selection_mode="date",
            image_dirs_str="./photos",
        )
        assert settings.selection_mode == "date"
        assert len(settings.image_dirs) == 1

    def test_curated_mode_config_valid(self):
        """Curated mode with CURATED_DIRS should be valid."""
        settings = Settings(
            selection_mode="curated",
            curated_dirs_str="./curated",
        )
        assert settings.selection_mode == "curated"
        assert len(settings.curated_dirs) == 1

    def test_multiple_curated_dirs_parsed(self):
        """Multiple CURATED_DIRS should be parsed correctly."""
        settings = Settings(
            selection_mode="curated",
            curated_dirs_str="./dir1, ./dir2, /absolute/dir3",
        )
        assert len(settings.curated_dirs) == 3


class TestCuratedSelection:
    """Test curated mode selection logic."""

    def test_get_all_photos_ordered_returns_sorted(self, tmp_path, monkeypatch):
        """get_all_photos_ordered should return photos sorted by filename."""
        import sqlite3
        from server.database import get_all_photos_ordered

        # Create test database
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE photo_records (
                path TEXT PRIMARY KEY,
                memory_score REAL,
                beauty_score REAL,
                exif_datetime TEXT,
                location_json TEXT,
                caption_json TEXT,
                enhanced_caption_json TEXT
            )
        """)

        # Insert test photos with unsorted paths
        conn.execute("INSERT INTO photo_records VALUES ('/z_photo.jpg', 80, 70, '2025-01-01', '{}', '{}', '{}')")
        conn.execute("INSERT INTO photo_records VALUES ('/a_photo.jpg', 90, 80, '2025-01-02', '{}', '{}', '{}')")
        conn.execute("INSERT INTO photo_records VALUES ('/m_photo.jpg', 70, 60, '2025-01-03', '{}', '{}', '{}')")
        conn.commit()
        conn.close()

        # Monkeypatch settings
        from server import config as server_config
        monkeypatch.setattr(server_config.settings, "curated_db_path", db_path)
        monkeypatch.setattr(server_config.settings, "selection_mode", "curated")

        candidates = get_all_photos_ordered()

        assert len(candidates) == 3
        # Should be sorted by filename: a, m, z
        assert candidates[0].path == "/a_photo.jpg"
        assert candidates[1].path == "/m_photo.jpg"
        assert candidates[2].path == "/z_photo.jpg"

    def test_curated_mode_includes_low_score_photos(self, tmp_path, monkeypatch):
        """Curated mode should include photos below memory threshold."""
        import sqlite3
        from server.selector import select_curated_photos
        from server import config as server_config

        # Create test database with low-score photo
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE photo_records (
                path TEXT PRIMARY KEY,
                memory_score REAL,
                beauty_score REAL,
                exif_datetime TEXT,
                location_json TEXT,
                caption_json TEXT,
                enhanced_caption_json TEXT
            )
        """)
        conn.execute("INSERT INTO photo_records VALUES ('/low_score.jpg', 30, 50, '2025-01-01', '{}', '{}', '{}')")
        conn.commit()
        conn.close()

        monkeypatch.setattr(server_config.settings, "curated_db_path", db_path)
        monkeypatch.setattr(server_config.settings, "selection_mode", "curated")

        candidates = select_curated_photos()
        assert len(candidates) == 1
        assert candidates[0].memory_score == 30

    def test_curated_mode_includes_photos_without_date(self, tmp_path, monkeypatch):
        """Curated mode should include photos without exif_datetime."""
        import sqlite3
        from server.selector import select_curated_photos
        from server import config as server_config

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE photo_records (
                path TEXT PRIMARY KEY,
                memory_score REAL,
                beauty_score REAL,
                exif_datetime TEXT,
                location_json TEXT,
                caption_json TEXT,
                enhanced_caption_json TEXT
            )
        """)
        conn.execute("INSERT INTO photo_records VALUES ('/no_date.jpg', 80, 70, NULL, '{}', '{}', '{}')")
        conn.commit()
        conn.close()

        monkeypatch.setattr(server_config.settings, "curated_db_path", db_path)
        monkeypatch.setattr(server_config.settings, "selection_mode", "curated")

        candidates = select_curated_photos()
        assert len(candidates) == 1
        assert candidates[0].exif_datetime == ""

    def test_empty_curated_db_raises_error(self, tmp_path, monkeypatch):
        """Empty curated database should raise ValueError."""
        import sqlite3
        from server.selector import select_curated_photos
        from server import config as server_config

        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE photo_records (
                path TEXT PRIMARY KEY,
                memory_score REAL,
                beauty_score REAL,
                exif_datetime TEXT,
                location_json TEXT,
                caption_json TEXT,
                enhanced_caption_json TEXT
            )
        """)
        conn.commit()
        conn.close()

        monkeypatch.setattr(server_config.settings, "curated_db_path", db_path)
        monkeypatch.setattr(server_config.settings, "selection_mode", "curated")

        with pytest.raises(ValueError, match="No photos found"):
            select_curated_photos()
