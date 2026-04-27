"""Tests for cache persistence to disk."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from server.cache import CachedPhoto, CacheMetadata
from server.database import PhotoCandidate


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def test_image_path(tmp_path: Path) -> Path:
    """Copy a real test image to temp directory."""
    # Find a test image from photo_analyzer/test
    source_dir = Path(__file__).parent.parent / "photo_analyzer" / "test"
    test_images = list(source_dir.glob("*.jpg")) + list(source_dir.glob("*.png"))
    if not test_images:
        pytest.skip("No test images available in photo_analyzer/test")

    source = test_images[0]
    dest = tmp_path / "test_image.jpg"
    shutil.copy2(source, dest)
    return dest


@pytest.fixture
def sample_candidate(test_image_path: Path) -> PhotoCandidate:
    """Create a sample PhotoCandidate using a real test image."""
    return PhotoCandidate(
        path=str(test_image_path),
        memory_score=85.5,
        beauty_score=90.0,
        exif_datetime="2024-07-15",
        location_city="深圳",
        caption="测试文案",
    )


@pytest.fixture
def sample_cached_photo(sample_candidate: PhotoCandidate) -> CachedPhoto:
    """Create a sample CachedPhoto for testing."""
    return CachedPhoto(
        candidate=sample_candidate,
        binary=b"\x00\x01\x02\x03" * 48000,  # 192KB dummy data
    )


class TestCacheMetadata:
    """Tests for CacheMetadata serialization."""

    def test_to_json_creates_valid_file(
        self, temp_cache_dir: Path, sample_cached_photo: CachedPhoto
    ):
        """Metadata should serialize to valid JSON file."""
        metadata = CacheMetadata(
            date="2026-04-27",
            photos=[
                {
                    "index": 0,
                    "path": sample_cached_photo.candidate.path,
                    "memory_score": sample_cached_photo.candidate.memory_score,
                    "beauty_score": sample_cached_photo.candidate.beauty_score,
                    "exif_datetime": sample_cached_photo.candidate.exif_datetime,
                    "location_city": sample_cached_photo.candidate.location_city,
                    "caption": sample_cached_photo.candidate.caption,
                    "binary_file": "photo_0.bin",
                    "preview_file": "photo_0.png",
                }
            ],
        )

        metadata.save(temp_cache_dir)

        json_path = temp_cache_dir / "metadata.json"
        assert json_path.exists()

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["date"] == "2026-04-27"
        assert len(data["photos"]) == 1
        assert data["photos"][0]["path"] == sample_cached_photo.candidate.path

    def test_from_json_loads_correctly(
        self, temp_cache_dir: Path, sample_cached_photo: CachedPhoto
    ):
        """Metadata should deserialize from JSON file."""
        # Write metadata
        metadata = CacheMetadata(
            date="2026-04-27",
            photos=[
                {
                    "index": 0,
                    "path": sample_cached_photo.candidate.path,
                    "memory_score": sample_cached_photo.candidate.memory_score,
                    "beauty_score": sample_cached_photo.candidate.beauty_score,
                    "exif_datetime": sample_cached_photo.candidate.exif_datetime,
                    "location_city": sample_cached_photo.candidate.location_city,
                    "caption": sample_cached_photo.candidate.caption,
                    "binary_file": "photo_0.bin",
                    "preview_file": "photo_0.png",
                }
            ],
        )
        metadata.save(temp_cache_dir)

        # Load metadata
        loaded = CacheMetadata.load(temp_cache_dir)

        assert loaded is not None
        assert loaded.date == "2026-04-27"
        assert len(loaded.photos) == 1
        assert loaded.photos[0]["path"] == sample_cached_photo.candidate.path

    def test_load_returns_none_if_no_file(self, temp_cache_dir: Path):
        """Load should return None if metadata.json doesn't exist."""
        result = CacheMetadata.load(temp_cache_dir)
        assert result is None


class TestDiskPersistence:
    """Tests for disk save/load operations."""

    def test_save_creates_all_files(
        self, temp_cache_dir: Path, sample_cached_photo: CachedPhoto
    ):
        """Save should create metadata.json, .bin, and .png files."""
        from server.cache import save_cache_to_disk

        photos = [sample_cached_photo]
        save_cache_to_disk(temp_cache_dir, date(2026, 4, 27), photos)

        assert (temp_cache_dir / "metadata.json").exists()
        assert (temp_cache_dir / "photo_0.bin").exists()
        assert (temp_cache_dir / "photo_0.png").exists()

    def test_load_reconstructs_cached_photos(
        self, temp_cache_dir: Path, sample_cached_photo: CachedPhoto
    ):
        """Load should reconstruct CachedPhoto objects from disk."""
        from server.cache import save_cache_to_disk, load_cache_from_disk

        photos = [sample_cached_photo]
        save_cache_to_disk(temp_cache_dir, date(2026, 4, 27), photos)

        loaded_date, loaded_photos = load_cache_from_disk(temp_cache_dir)

        assert loaded_date == date(2026, 4, 27)
        assert len(loaded_photos) == 1
        assert loaded_photos[0].candidate.path == sample_cached_photo.candidate.path
        assert loaded_photos[0].binary == sample_cached_photo.binary

    def test_clear_removes_all_files(
        self, temp_cache_dir: Path, sample_cached_photo: CachedPhoto
    ):
        """Clear should remove all cache files."""
        from server.cache import save_cache_to_disk, clear_cache_dir

        photos = [sample_cached_photo]
        save_cache_to_disk(temp_cache_dir, date(2026, 4, 27), photos)

        clear_cache_dir(temp_cache_dir)

        assert not (temp_cache_dir / "metadata.json").exists()
        assert not (temp_cache_dir / "photo_0.bin").exists()
        assert not (temp_cache_dir / "photo_0.png").exists()
