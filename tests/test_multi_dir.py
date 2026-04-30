"""Tests for multi-directory photo source support."""

import tempfile
from pathlib import Path

import pytest

from photo_analyzer.config import Settings
from photo_analyzer.database import count_records, delete_orphaned_records, init_database


class TestConfigParsing:
    """Test IMAGE_DIRS configuration parsing."""

    def test_single_dir_string(self):
        """Single directory as string should become list with one Path."""
        settings = Settings(image_dirs_str="./photos")
        assert len(settings.image_dirs) == 1
        assert settings.image_dirs[0] == Path("./photos")

    def test_multiple_dirs_comma_separated(self):
        """Comma-separated string should become list of Paths."""
        settings = Settings(image_dirs_str="./photos, ./more-photos, /absolute/path")
        assert len(settings.image_dirs) == 3
        assert settings.image_dirs[0] == Path("./photos")
        assert settings.image_dirs[1] == Path("./more-photos")
        assert settings.image_dirs[2] == Path("/absolute/path")

    def test_empty_string_uses_default(self):
        """Empty string should fall back to default (only in curated mode)."""
        # In date mode, empty IMAGE_DIRS raises error
        # In curated mode, empty IMAGE_DIRS falls back to default
        settings = Settings(selection_mode="curated", curated_dirs_str="./curated", image_dirs_str="")
        assert len(settings.image_dirs) == 1
        assert settings.image_dirs[0] == Path("./photo_analyzer/test")

    def test_whitespace_handling(self):
        """Whitespace around paths should be trimmed."""
        settings = Settings(image_dirs_str="  ./photos  ,  ./other  ")
        assert len(settings.image_dirs) == 2
        assert settings.image_dirs[0] == Path("./photos")
        assert settings.image_dirs[1] == Path("./other")


class TestListImages:
    """Test multi-directory scanning."""

    def test_multiple_dirs_scanned(self, tmp_path):
        """Should scan all configured directories."""
        from photo_analyzer.__main__ import list_images

        # Create two directories with images
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        # Create dummy image files
        (dir1 / "photo1.jpg").touch()
        (dir1 / "photo2.png").touch()
        (dir2 / "photo3.jpg").touch()
        (dir2 / "photo4.png").touch()

        images = list_images([dir1, dir2])

        assert len(images) == 4
        assert any("photo1.jpg" in str(p) for p in images)
        assert any("photo3.jpg" in str(p) for p in images)

    def test_nonexistent_dir_skipped(self, tmp_path, caplog):
        """Non-existent directory should be skipped with warning."""
        import logging
        from photo_analyzer.__main__ import list_images

        caplog.set_level(logging.WARNING)

        existing_dir = tmp_path / "exists"
        existing_dir.mkdir()
        (existing_dir / "photo.jpg").touch()

        nonexistent = tmp_path / "does_not_exist"

        images = list_images([existing_dir, nonexistent])

        assert len(images) == 1
        assert "does not exist" in caplog.text

    def test_recursive_scanning(self, tmp_path):
        """Should scan subdirectories recursively."""
        from photo_analyzer.__main__ import list_images

        subdir = tmp_path / "photos" / "2024" / "jan"
        subdir.mkdir(parents=True)
        (subdir / "nested.jpg").touch()

        images = list_images([tmp_path / "photos"])

        assert len(images) == 1
        assert "nested.jpg" in str(images[0])

    def test_all_images_included(self, tmp_path):
        """All image files should be included."""
        from photo_analyzer.__main__ import list_images

        (tmp_path / "photo.jpg").touch()
        (tmp_path / "screenshot_123.png").touch()

        images = list_images([tmp_path])

        assert len(images) == 2


class TestOrphanDeletion:
    """Test orphan record deletion without prefix filter."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        yield conn
        conn.close()

    def test_delete_records_not_in_paths(self, temp_db, tmp_path):
        """Records for files not in existing_paths should be deleted."""
        from photo_analyzer.models import PhotoRecord

        # Insert test records
        record1 = PhotoRecord(path=str(tmp_path / "photo1.jpg"), description="test1")
        record2 = PhotoRecord(path=str(tmp_path / "photo2.jpg"), description="test2")
        record3 = PhotoRecord(path=str(tmp_path / "photo3.jpg"), description="test3")

        from photo_analyzer.database import save_photo
        save_photo(temp_db, record1)
        save_photo(temp_db, record2)
        save_photo(temp_db, record3)

        assert count_records(temp_db) == 3

        # Delete records where only photo1 and photo2 are in existing_paths
        existing = [str(tmp_path / "photo1.jpg"), str(tmp_path / "photo2.jpg")]
        deleted = delete_orphaned_records(temp_db, existing)

        assert deleted == 1
        assert count_records(temp_db) == 2

    def test_delete_from_removed_directory(self, temp_db, tmp_path):
        """Records from directories removed from config should be deleted."""
        from photo_analyzer.models import PhotoRecord
        from photo_analyzer.database import save_photo

        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        # Create files on disk
        (dir1 / "photo1.jpg").touch()
        (dir2 / "photo2.jpg").touch()

        # Insert records for both directories
        record1 = PhotoRecord(path=str(dir1 / "photo1.jpg"), description="in dir1")
        record2 = PhotoRecord(path=str(dir2 / "photo2.jpg"), description="in dir2")
        save_photo(temp_db, record1)
        save_photo(temp_db, record2)

        # Simulate config only having dir1 (dir2 removed)
        existing = [str(dir1 / "photo1.jpg")]
        deleted = delete_orphaned_records(temp_db, existing)

        assert deleted == 1
        assert count_records(temp_db) == 1

    def test_no_orphans_returns_zero(self, temp_db, tmp_path):
        """Should return 0 if no records to delete."""
        from photo_analyzer.models import PhotoRecord
        from photo_analyzer.database import save_photo

        (tmp_path / "photo.jpg").touch()
        record = PhotoRecord(path=str(tmp_path / "photo.jpg"), description="test")
        save_photo(temp_db, record)

        existing = [str(tmp_path / "photo.jpg")]
        deleted = delete_orphaned_records(temp_db, existing)

        assert deleted == 0
        assert count_records(temp_db) == 1

    def test_empty_existing_paths_deletes_all(self, temp_db, tmp_path):
        """Empty existing_paths should delete all records."""
        from photo_analyzer.models import PhotoRecord
        from photo_analyzer.database import save_photo

        record = PhotoRecord(path=str(tmp_path / "photo.jpg"), description="test")
        save_photo(temp_db, record)

        deleted = delete_orphaned_records(temp_db, [])

        assert deleted == 1
        assert count_records(temp_db) == 0
