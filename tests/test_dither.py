"""Tests for dithering with epaper-dithering library."""

import pytest
from PIL import Image
from epaper_dithering import SPECTRA_7_3_6COLOR_V2

from server.dither import apply_dither, pack_to_4bpp, CANVAS_WIDTH, CANVAS_HEIGHT


def test_apply_dither_returns_correct_size():
    """Dithering should return image with same dimensions."""
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT))
    for x in range(CANVAS_WIDTH):
        for y in range(CANVAS_HEIGHT):
            r = int(255 * x / CANVAS_WIDTH)
            g = int(255 * y / CANVAS_HEIGHT)
            b = 128
            img.putpixel((x, y), (r, g, b))

    result = apply_dither(img)

    assert result.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    assert result.mode == "RGB"


def test_apply_dither_uses_only_palette_colors():
    """Dithered image should only contain measured palette colors from library."""
    img = Image.new("RGB", (100, 100))
    for x in range(100):
        for y in range(100):
            img.putpixel((x, y), (x * 2, y * 2, 128))

    result = apply_dither(img)

    # Collect unique colors
    unique_colors = set(result.get_flattened_data())

    # Expected colors come directly from the library's measured palette
    expected_colors = set(SPECTRA_7_3_6COLOR_V2.colors.values())

    # All colors in result should be in expected set
    for color in unique_colors:
        assert color in expected_colors, f"Unexpected color: {color}"


def test_pack_to_4bpp_returns_correct_size():
    """Packing should produce 192KB for 480x800 image."""
    # Use colors from the library's measured palette
    colors = list(SPECTRA_7_3_6COLOR_V2.colors.values())
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT))

    for i, color in enumerate(colors):
        for x in range(80):
            for y in range(100):
                img.putpixel((i * 80 + x, y), color)

    result = pack_to_4bpp(img)

    expected_size = (CANVAS_WIDTH * CANVAS_HEIGHT) // 2  # 192,000 bytes
    assert len(result) == expected_size


def test_pack_to_4bpp_valid_indices():
    """Verify packed bytes contain valid display indices (0-3, 5-6, no 4)."""
    # Dither a gradient image
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT))
    for x in range(CANVAS_WIDTH):
        for y in range(CANVAS_HEIGHT):
            gray = int(255 * x / CANVAS_WIDTH)
            img.putpixel((x, y), (gray, gray, gray))

    dithered = apply_dither(img)
    packed = pack_to_4bpp(dithered)

    # Verify all bytes are valid 4bpp values
    valid_indices = {0, 1, 2, 3, 5, 6}  # Display indices (4 is skipped)
    for byte in packed:
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        assert high in valid_indices, f"Invalid high nibble: {high}"
        assert low in valid_indices, f"Invalid low nibble: {low}"


def test_full_pipeline_produces_192kb():
    """Test full dithering + packing pipeline produces correct output size."""
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT))
    for x in range(CANVAS_WIDTH):
        for y in range(CANVAS_HEIGHT):
            r = int(255 * x / CANVAS_WIDTH)
            g = int(255 * (CANVAS_HEIGHT - y) / CANVAS_HEIGHT)
            b = int(128 + 64 * (x - CANVAS_WIDTH/2) / CANVAS_WIDTH)
            img.putpixel((x, y), (r, g, b))

    dithered = apply_dither(img)
    packed = pack_to_4bpp(dithered)

    assert len(packed) == 192000
