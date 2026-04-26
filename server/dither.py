"""Low-level image processing for 7.3" E6 6-color e-ink display (GDEP073E01).

Provides Floyd-Steinberg dithering and 4bpp packing functions.
These are pure image transformations with no knowledge of text or layout.

Hardware constants are hardcoded here since they're tied to the display panel.
"""

from __future__ import annotations

from typing import Tuple

from PIL import Image

# =============================================================================
# Display Constants (hardcoded for GDEP073E01 panel)
# =============================================================================
CANVAS_WIDTH = 480
CANVAS_HEIGHT = 800
TOTAL_BYTES = (CANVAS_WIDTH * CANVAS_HEIGHT) // 2  # 192,000 bytes (4bpp packed)

# 6-Color Palette (E6 display - GDEP073E01)
# Color indices match display controller LUT
# Note: Index 4 is skipped (not used by E6)
PALETTE_6 = [
    (0, 0, 0),        # 0 Black
    (255, 255, 255),  # 1 White
    (255, 255, 0),    # 2 Yellow
    (255, 0, 0),      # 3 Red
    (0, 0, 255),      # 5 Blue
    (0, 255, 0),      # 6 Green
]
PALETTE_6_INDEX = [0, 1, 2, 3, 5, 6]  # Note: 4 is skipped


# =============================================================================
# Color Conversion
# =============================================================================
def nearest_palette_index(r: float, g: float, b: float) -> int:
    """Find nearest color in 6-color palette by Euclidean distance.

    Args:
        r: Red component (0-255)
        g: Green component (0-255)
        b: Blue component (0-255)

    Returns:
        Palette index (0, 1, 2, 3, 5, or 6)
    """
    best_i = 0
    best_dist = float("inf")
    for i, (pr, pg, pb) in enumerate(PALETTE_6):
        dr = r - pr
        dg = g - pg
        db = b - pb
        dist = dr * dr + dg * dg + db * db
        if dist < best_dist:
            best_dist = dist
            best_i = i
    return PALETTE_6_INDEX[best_i]


def rgb_to_palette_index(r: int, g: int, b: int) -> int:
    """Convert RGB to palette index with exact match lookup first.

    Args:
        r: Red component (0-255)
        g: Green component (0-255)
        b: Blue component (0-255)

    Returns:
        Palette index (0, 1, 2, 3, 5, or 6)
    """
    # Exact matches (fast path)
    if (r, g, b) == (0, 0, 0):
        return 0  # Black
    if (r, g, b) == (255, 255, 255):
        return 1  # White
    if (r, g, b) == (255, 255, 0):
        return 2  # Yellow
    if (r, g, b) == (255, 0, 0):
        return 3  # Red
    if (r, g, b) == (0, 0, 255):
        return 5  # Blue
    if (r, g, b) == (0, 255, 0):
        return 6  # Green
    # Fallback to nearest color search
    return nearest_palette_index(r, g, b)


def _index_to_rgb(idx: int) -> Tuple[int, int, int]:
    """Convert palette index to RGB tuple.

    Args:
        idx: Palette index (0, 1, 2, 3, 5, or 6)

    Returns:
        RGB tuple
    """
    colors = {
        0: (0, 0, 0),        # Black
        1: (255, 255, 255),  # White
        2: (255, 255, 0),    # Yellow
        3: (255, 0, 0),      # Red
        5: (0, 0, 255),      # Blue
        6: (0, 255, 0),      # Green
    }
    return colors.get(idx, (255, 255, 255))


# =============================================================================
# Floyd-Steinberg Dithering
# =============================================================================
def apply_dither(img: Image.Image) -> Image.Image:
    """Apply Floyd-Steinberg dithering to convert image to 6-color palette.

    Error diffusion pattern:
              *   7/16
        3/16 5/16 1/16

    Args:
        img: Input PIL Image (any mode, will be converted to RGB)

    Returns:
        Dithered PIL Image in RGB mode with colors from 6-color palette
    """
    img = img.convert("RGB")
    w, h = img.size
    pixels = img.load()

    # Error buffers for current and next row
    err_r = [0.0] * w
    err_g = [0.0] * w
    err_b = [0.0] * w
    next_err_r = [0.0] * w
    next_err_g = [0.0] * w
    next_err_b = [0.0] * w

    for y in range(h):
        for x in range(w):
            # Get pixel and add accumulated error
            r, g, b = pixels[x, y]
            r = max(0.0, min(255.0, r + err_r[x]))
            g = max(0.0, min(255.0, g + err_g[x]))
            b = max(0.0, min(255.0, b + err_b[x]))

            # Find nearest palette color
            idx = nearest_palette_index(r, g, b)
            pr, pg, pb = _index_to_rgb(idx)
            pixels[x, y] = (pr, pg, pb)

            # Calculate quantization error
            er = r - pr
            eg = g - pg
            eb = b - pb

            # Distribute error to neighboring pixels (Floyd-Steinberg)
            if x + 1 < w:
                err_r[x + 1] += er * (7.0 / 16.0)
                err_g[x + 1] += eg * (7.0 / 16.0)
                err_b[x + 1] += eb * (7.0 / 16.0)
            if y + 1 < h:
                if x > 0:
                    next_err_r[x - 1] += er * (3.0 / 16.0)
                    next_err_g[x - 1] += eg * (3.0 / 16.0)
                    next_err_b[x - 1] += eb * (3.0 / 16.0)
                next_err_r[x] += er * (5.0 / 16.0)
                next_err_g[x] += eg * (5.0 / 16.0)
                next_err_b[x] += eb * (5.0 / 16.0)
                if x + 1 < w:
                    next_err_r[x + 1] += er * (1.0 / 16.0)
                    next_err_g[x + 1] += eg * (1.0 / 16.0)
                    next_err_b[x + 1] += eb * (1.0 / 16.0)

        # Swap error buffers for next row
        if y + 1 < h:
            for i in range(w):
                err_r[i] = next_err_r[i]
                err_g[i] = next_err_g[i]
                err_b[i] = next_err_b[i]
                next_err_r[i] = 0.0
                next_err_g[i] = 0.0
                next_err_b[i] = 0.0

    return img


# =============================================================================
# 4bpp Packing
# =============================================================================
def _pack_two_pixels(p0: int, p1: int) -> int:
    """Pack two 4-bit pixel indices into one byte.

    Format: high nibble = first pixel, low nibble = second pixel
    This matches the E6 display controller's native byte format.

    Args:
        p0: First pixel index (0-15)
        p1: Second pixel index (0-15)

    Returns:
        Packed byte value
    """
    return ((p0 & 0x0F) << 4) | (p1 & 0x0F)


def pack_to_4bpp(img: Image.Image) -> bytes:
    """Convert dithered 480x800 RGB image to 192KB packed binary.

    GxEPD2 expects row-major format:
    - Each row (480 pixels) packed into 240 bytes
    - High nibble = left pixel, low nibble = right pixel

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

    out = bytearray(TOTAL_BYTES)  # 192,000 bytes

    for y in range(CANVAS_HEIGHT):  # 0 to 799
        x = 0
        while x < CANVAS_WIDTH:  # 0 to 479
            p0 = rgb_to_palette_index(*img.getpixel((x, y)))
            p1 = rgb_to_palette_index(*img.getpixel((x + 1, y)))
            byte_offset = y * (CANVAS_WIDTH // 2) + x // 2
            out[byte_offset] = _pack_two_pixels(p0, p1)
            x += 2

    return bytes(out)
