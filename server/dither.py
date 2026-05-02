"""Image processing for 7.3" E6 6-color e-ink display (GDEP073E01).

Uses epaper-dithering library for:
- Measured palette colors (SPECTRA_7_3_6COLOR_V2)
- Perceptual (CIELAB) color matching
- Serpentine scanning
- Dynamic range compression

Only the 4bpp packing is implemented here (panel-specific format).
"""

from __future__ import annotations

from typing import Literal

from PIL import Image

from epaper_dithering import dither_image, DitherMode, SPECTRA_7_3_6COLOR_V2

# =============================================================================
# Display Constants
# =============================================================================
CANVAS_WIDTH = 480
CANVAS_HEIGHT = 800
PHOTO_AREA_HEIGHT = 700  # Top 700px for photo, bottom 100px for text
TOTAL_BYTES = (CANVAS_WIDTH * CANVAS_HEIGHT) // 2  # 192,000 bytes

# =============================================================================
# Dithering Mode Configuration
# =============================================================================
DitherModeType = Literal["floyd_steinberg", "burkes", "atkinson", "sierra", "stucki", "jarvis"]

DITHER_MODE_MAP = {
    "floyd_steinberg": DitherMode.FLOYD_STEINBERG,
    "burkes": DitherMode.BURKES,
    "atkinson": DitherMode.ATKINSON,
    "sierra": DitherMode.SIERRA,
    "stucki": DitherMode.STUCKI,
    "jarvis": DitherMode.JARVIS_JUDICE_NINKE,
}

# =============================================================================
# Palette Index Mapping (built from library's measured palette)
# =============================================================================
# Display controller expects: 0=Black, 1=White, 2=Yellow, 3=Red, 5=Blue, 6=Green
# Library palette uses color names, we map to display indices
_COLOR_NAME_TO_DISPLAY_INDEX = {
    "black": 0,
    "white": 1,
    "yellow": 2,
    "red": 3,
    "blue": 5,
    "green": 6,
}

# Build RGB -> display index mapping from library's measured palette values
_RGB_TO_INDEX: dict[tuple[int, int, int], int] = {
    rgb: _COLOR_NAME_TO_DISPLAY_INDEX[name]
    for name, rgb in SPECTRA_7_3_6COLOR_V2.colors.items()
    if name in _COLOR_NAME_TO_DISPLAY_INDEX
}

# Add pure black and pure white for text rendering (not in measured palette)
# These are used by text_overlay module for crisp text on white background
_RGB_TO_INDEX[(0, 0, 0)] = 0  # Pure black → display black
_RGB_TO_INDEX[(255, 255, 255)] = 1  # Pure white → display white


# =============================================================================
# Dithering
# =============================================================================
def apply_dither(
    img: Image.Image,
    mode: DitherModeType = "burkes",
    tone: float | str = 0.0,
) -> Image.Image:
    """Apply dithering to convert image to 6-color measured palette.

    Args:
        img: Input PIL Image (any mode, converted to RGB)
        mode: Dithering algorithm:
            - "burkes" (default): Good balance of quality and speed
            - "floyd_steinberg": Classic algorithm
            - "atkinson": High contrast, artistic
            - "sierra": High quality
            - "stucki": Very high quality, slower
            - "jarvis": Smooth gradients, slowest
        tone: Dynamic range compression (0.0-1.0 or "auto"):
            - 0.0 (default): No compression, preserves original exposure
            - 0.5: Partial compression
            - 1.0: Full compression to display range
            - "auto": Histogram-based stretching (may over-brighten)

    Returns:
        Dithered PIL Image in RGB mode with measured palette colors
    """
    img = img.convert("RGB")
    dither_mode = DITHER_MODE_MAP.get(mode, DitherMode.BURKES)

    result = dither_image(
        img,
        SPECTRA_7_3_6COLOR_V2,
        mode=dither_mode,
        serpentine=True,
        tone=tone,
    )

    return result.convert("RGB")


# =============================================================================
# 4bpp Packing (panel-specific)
# =============================================================================
def _rgb_to_display_index(rgb: tuple[int, int, int]) -> int:
    """Convert RGB pixel to display color index.

    Args:
        rgb: RGB tuple (r, g, b)

    Returns:
        Display color index (0=black, 1=white, 2=yellow, 3=red, 5=blue, 6=green)
    """
    if rgb in _RGB_TO_INDEX:
        return _RGB_TO_INDEX[rgb]
    return 1  # Default to white for unexpected colors


def pack_to_4bpp(img: Image.Image) -> bytes:
    """Convert dithered 480x800 RGB image to 192KB packed binary.

    Format: High nibble = first pixel, low nibble = second pixel.
    This matches GxEPD2_730c_GDEP073E01 controller's native byte format.

    Args:
        img: Input PIL Image (must be exactly 480x800)

    Returns:
        192,000 bytes of packed pixel data

    Raises:
        RuntimeError: If image size doesn't match canvas dimensions
    """
    img = img.convert("RGB")
    if img.size != (CANVAS_WIDTH, CANVAS_HEIGHT):
        raise RuntimeError(
            f"Image size mismatch: {img.size}, expected ({CANVAS_WIDTH}, {CANVAS_HEIGHT})"
        )

    out = bytearray(TOTAL_BYTES)

    for y in range(CANVAS_HEIGHT):
        x = 0
        while x < CANVAS_WIDTH:
            # Get RGB values and convert to display index
            rgb0 = img.getpixel((x, y))
            rgb1 = img.getpixel((x + 1, y))
            p0 = _rgb_to_display_index(rgb0)
            p1 = _rgb_to_display_index(rgb1)

            # Pack: high nibble = first pixel, low nibble = second
            byte_offset = y * (CANVAS_WIDTH // 2) + x // 2
            out[byte_offset] = ((p0 & 0x0F) << 4) | (p1 & 0x0F)
            x += 2

    return bytes(out)
