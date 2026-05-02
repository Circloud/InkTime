"""Tests for text_overlay module."""

import pytest
from PIL import Image

from server.text_overlay import (
    render_text_overlay,
    format_date_display,
    TEXT_CANVAS_WIDTH,
    TEXT_CANVAS_HEIGHT,
)
from server.database import PhotoCandidate


def test_render_text_overlay_returns_correct_size():
    """Text overlay should be 480x100."""
    candidate = PhotoCandidate(
        path="/test/photo.jpg",
        memory_score=80.0,
        beauty_score=85.0,
        exif_datetime="2026-05-02",
        caption_json={"zh": "测试文案", "en": "Test caption"},
        location_json={"zh": "深圳", "en": "Shenzhen"},
    )

    result = render_text_overlay(candidate, lang="zh")

    assert result.size == (TEXT_CANVAS_WIDTH, TEXT_CANVAS_HEIGHT)
    assert result.mode == "RGB"


def test_render_text_overlay_uses_white_background():
    """Text overlay background should be white."""
    candidate = PhotoCandidate(
        path="/test/photo.jpg",
        memory_score=80.0,
        beauty_score=85.0,
        exif_datetime="2026-05-02",
    )

    result = render_text_overlay(candidate, lang="zh")

    # Check corners are white
    assert result.getpixel((0, 0)) == (255, 255, 255)
    assert result.getpixel((479, 99)) == (255, 255, 255)


def test_render_text_overlay_has_no_grayscale():
    """Text overlay should only have pure black and pure white (no anti-aliasing)."""
    candidate = PhotoCandidate(
        path="/test/photo.jpg",
        memory_score=80.0,
        beauty_score=85.0,
        exif_datetime="2026-05-02",
        caption_json={"zh": "测试文案"},
    )

    result = render_text_overlay(candidate, lang="zh")

    # Collect all unique colors
    colors = set()
    for y in range(TEXT_CANVAS_HEIGHT):
        for x in range(TEXT_CANVAS_WIDTH):
            colors.add(result.getpixel((x, y)))

    # Should only have pure black and pure white
    assert colors == {(0, 0, 0), (255, 255, 255)}


def test_format_date_display_chinese():
    """Chinese date format should be YYYY.M.D."""
    assert format_date_display("2026-05-02", lang="zh") == "2026.5.2"
    assert format_date_display("2026-12-25", lang="zh") == "2026.12.25"


def test_format_date_display_english():
    """English date format should be Mon D, YYYY."""
    assert format_date_display("2026-05-02", lang="en") == "May 2, 2026"
    assert format_date_display("2026-12-25", lang="en") == "Dec 25, 2026"


def test_format_date_display_invalid():
    """Invalid dates should return empty string for short inputs."""
    assert format_date_display("", lang="zh") == ""
    assert format_date_display("short", lang="zh") == ""  # Less than 10 chars
    assert format_date_display("2026-05-02extra", lang="zh") == "2026-05-02extra"  # Invalid format, passed through
