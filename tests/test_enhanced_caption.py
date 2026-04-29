"""Tests for enhanced caption functionality."""

import json
import sqlite3
from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock

from photo_analyzer.database import ensure_table, save_photo
from photo_analyzer.models import PhotoRecord


def test_enhanced_caption_json_field():
    """Test that enhanced_caption_json can be stored and retrieved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(db_path)
        ensure_table(conn)

        record = PhotoRecord(
            path="/test/photo.jpg",
            description="Test photo",
            photo_type="风景",
            memory_score=75.0,
            beauty_score=80.0,
            reason="Nice view",
            caption_json={"zh": "原始文案"},
            enhanced_caption_json={"zh": "增强文案"},
            width=800,
            height=600,
        )

        save_photo(conn, record)

        row = conn.execute(
            "SELECT enhanced_caption_json FROM photo_records WHERE path = ?",
            ("/test/photo.jpg",),
        ).fetchone()

        assert row is not None
        enhanced = json.loads(row[0])
        assert enhanced == {"zh": "增强文案"}

        conn.close()


def test_generate_enhanced_caption_success():
    """Test successful enhanced caption generation."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"caption": "An enhanced creative caption"}'
            }
        }]
    }

    with patch("server.enhanced_caption.requests.post", return_value=mock_response):
        with patch("server.enhanced_caption.encode_image_to_b64", return_value="base64data"):
            with patch("server.enhanced_caption.settings") as mock_settings:
                mock_settings.enhanced_caption_enabled = True
                mock_settings.enhanced_base_url = "https://api.example.com/v1/chat/completions"
                mock_settings.enhanced_api_key = "test-key"
                mock_settings.enhanced_model_name = "gpt-4o-mini"
                mock_settings.enhanced_timeout = 60
                mock_settings.enhanced_retry_times = 3

                from server.enhanced_caption import generate_enhanced_caption
                result = generate_enhanced_caption(Path("/test/photo.jpg"), "en")

    assert result == "An enhanced creative caption"


def test_generate_enhanced_caption_api_failure():
    """Test that API failure returns None."""
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 500

    with patch("server.enhanced_caption.requests.post", return_value=mock_response):
        with patch("server.enhanced_caption.encode_image_to_b64", return_value="base64data"):
            with patch("server.enhanced_caption.settings") as mock_settings:
                mock_settings.enhanced_caption_enabled = True
                mock_settings.enhanced_base_url = "https://api.example.com/v1/chat/completions"
                mock_settings.enhanced_api_key = "test-key"
                mock_settings.enhanced_model_name = "gpt-4o-mini"
                mock_settings.enhanced_timeout = 60
                mock_settings.enhanced_retry_times = 3

                from server.enhanced_caption import generate_enhanced_caption
                result = generate_enhanced_caption(Path("/test/photo.jpg"), "en")

    assert result is None


def test_generate_enhanced_caption_disabled():
    """Test that disabled feature returns None immediately."""
    with patch("server.enhanced_caption.settings") as mock_settings:
        mock_settings.enhanced_caption_enabled = False
        from server.enhanced_caption import generate_enhanced_caption
        result = generate_enhanced_caption(Path("/test/photo.jpg"), "en")

    assert result is None


def test_enhanced_caption_end_to_end():
    """Test full flow: save photo, update enhanced caption, retrieve."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        ensure_table(conn)

        # Save photo with original caption
        record = PhotoRecord(
            path="/test/photo.jpg",
            description="Test photo",
            photo_type="风景",
            memory_score=75.0,
            beauty_score=80.0,
            reason="Nice view",
            caption_json={"zh": "原始文案", "en": "Original caption"},
            enhanced_caption_json={},
            width=800,
            height=600,
        )
        save_photo(conn, record)

        # Verify initial state (empty dict is saved as None)
        row = conn.execute(
            "SELECT enhanced_caption_json FROM photo_records WHERE path = ?",
            ("/test/photo.jpg",),
        ).fetchone()
        assert row[0] is None or json.loads(row[0]) == {}

        # Import update function
        from server.database import update_enhanced_caption

        # Update enhanced caption for English
        update_enhanced_caption(conn, "/test/photo.jpg", "en", "Enhanced English caption")

        # Verify update
        row = conn.execute(
            "SELECT enhanced_caption_json FROM photo_records WHERE path = ?",
            ("/test/photo.jpg",),
        ).fetchone()
        enhanced = json.loads(row[0])
        assert enhanced == {"en": "Enhanced English caption"}

        # Update another language
        update_enhanced_caption(conn, "/test/photo.jpg", "zh", "增强中文文案")

        # Verify both languages
        row = conn.execute(
            "SELECT enhanced_caption_json FROM photo_records WHERE path = ?",
            ("/test/photo.jpg",),
        ).fetchone()
        enhanced = json.loads(row[0])
        assert enhanced == {"en": "Enhanced English caption", "zh": "增强中文文案"}

        conn.close()
