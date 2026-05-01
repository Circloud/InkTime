"""Tests for server API routes."""

import pytest
from datetime import date
from unittest.mock import MagicMock, PropertyMock

from server.app import create_app
from server.cache import CachedPhoto, DailyPhotoCache, CacheMetadata
from server.database import PhotoCandidate


@pytest.fixture
def app():
    """Create test Flask app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestPhotoEndpoint:
    """Tests for GET /api/photo endpoint."""

    def test_returns_204_when_no_photos(self, client, monkeypatch):
        """Should return 204 No Content when cache is empty."""
        from server import routes

        # Create mock cache with no photos
        mock_cache = MagicMock(spec=DailyPhotoCache)
        mock_cache.get_next.side_effect = RuntimeError("No photos available")
        mock_cache.current_date = date.today()
        mock_cache.count = 0
        mock_cache.current_index = 0

        monkeypatch.setattr(routes, "cache", mock_cache)

        response = client.get("/api/photo")

        assert response.status_code == 204

    def test_returns_photo_binary_with_headers(self, client, monkeypatch):
        """Should return photo binary with correct headers."""
        from server import routes

        # Create mock cached photo
        candidate = PhotoCandidate(
            path="/path/to/photo.jpg",
            memory_score=85.5,
            beauty_score=90.0,
            exif_datetime="2024-07-15",
            location_json={"zh": "深圳"},
            caption_json={"zh": "测试"},
        )
        cached_photo = CachedPhoto(candidate=candidate, binary=b"\x00" * 192000)

        # Create mock cache
        mock_cache = MagicMock(spec=DailyPhotoCache)
        mock_cache.get_next.return_value = cached_photo
        mock_cache.current_date = date.today()
        mock_cache.count = 1
        mock_cache.current_index = 1  # After increment

        monkeypatch.setattr(routes, "cache", mock_cache)

        response = client.get("/api/photo")

        assert response.status_code == 200
        assert len(response.data) == 192000
        assert response.headers["X-Photo-Date"] == "2024-07-15"
        assert response.headers["X-Photo-Score"] == "85.5"
        assert response.headers["X-Photo-Index"] == "1"
        assert response.headers["X-Photo-Total"] == "1"

    def test_status_includes_current_index(self, client, tmp_path, monkeypatch):
        """Status endpoint should include current_index."""
        from server import routes

        mock_cache = MagicMock(spec=DailyPhotoCache)
        mock_cache.current_date = date.today()
        mock_cache.count = 5
        mock_cache.current_index = 2

        monkeypatch.setattr(routes, "cache", mock_cache)

        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["current_index"] == 2
        assert data["photo_count"] == 5
