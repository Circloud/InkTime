"""Text overlay rendering for e-ink display.

Renders text on a standalone 480x100 white canvas for crisp edges.
This module handles text layout independently from photo processing.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from epaper_dithering import dither_image, DitherMode, ColorPalette

from .database import PhotoCandidate


# =============================================================================
# Pure Black/White Palette for Text Dithering
# =============================================================================
# This palette ensures text gets pure black/white output with error diffusion
# for smooth edges (not jagged like hard binarization)
_BW_PALETTE = ColorPalette(
    colors={'black': (0, 0, 0), 'white': (255, 255, 255)},
    accent='black'
)


# =============================================================================
# Text Canvas Dimensions
# =============================================================================
TEXT_CANVAS_WIDTH = 480
TEXT_CANVAS_HEIGHT = 100

# =============================================================================
# Text Layout Constants (relative to text canvas, y=0 at top)
# =============================================================================
TEXT_PADDING_X = 24
CAPTION_TOP_Y = 10  # Caption starts 10px from top
DATE_LOCATION_Y = 64  # Date/location line (was 764 on full canvas, 764-700=64)
CAPTION_LINE_HEIGHT = 24

# Font sizes (English fonts appear larger at same point size)
CAPTION_FONT_SIZE_ZH = 22
CAPTION_FONT_SIZE_EN = 18
DATE_LOCATION_FONT_SIZE_ZH = 20
DATE_LOCATION_FONT_SIZE_EN = 16

# Month names for English formatting
MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


# =============================================================================
# Text Utilities
# =============================================================================
def format_date_display(date_str: str, lang: str = "zh") -> str:
    """Convert 'YYYY-MM-DD' to display format based on language."""
    if not date_str or len(date_str) < 10:
        return ""

    parts = date_str.split("-")
    if len(parts) < 3:
        return date_str

    try:
        year = parts[0]
        month = int(parts[1])
        day = int(parts[2])

        if lang == "en":
            return f"{MONTH_ABBR.get(month, str(month))} {day}, {year}"
        else:
            return f"{year}.{month}.{day}"
    except (ValueError, IndexError):
        return date_str


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
    lang: str = "zh",
) -> list[str]:
    """Wrap text to fit within max_width, returning up to max_lines."""
    if not text:
        return []

    lines: list[str] = []

    if lang == "en":
        words = text.split(" ")
        line = ""

        for word in words:
            test = line + " " + word if line else word
            width = draw.textlength(test, font=font)

            if width <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                    if len(lines) >= max_lines:
                        break
                    line = word
                else:
                    lines.append(word)
                    if len(lines) >= max_lines:
                        break
                    line = ""

        if line and len(lines) < max_lines:
            lines.append(line)
    else:
        line = ""
        for char in text:
            test = line + char
            width = draw.textlength(test, font=font)

            if width <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                    if len(lines) >= max_lines:
                        break
                line = char

        if line and len(lines) < max_lines:
            lines.append(line)

    return lines


def load_font(size: int, font_path: Path | None = None) -> ImageFont.FreeTypeFont:
    """Load font at specified size, falling back to default if unavailable."""
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def _dither_text_area(img: Image.Image) -> Image.Image:
    """Apply error-diffusion dithering to text area with pure black/white palette.

    This produces smooth text edges (not jagged like hard binarization).
    Error diffusion naturally handles anti-aliased grayscale pixels.

    Args:
        img: RGB image with anti-aliased text

    Returns:
        RGB image with only pure black (0,0,0) and pure white (255,255,255)
    """
    # Apply Floyd-Steinberg dithering with B/W palette
    dithered = dither_image(
        img,
        _BW_PALETTE,
        mode=DitherMode.FLOYD_STEINBERG,
        serpentine=True,
    )
    return dithered.convert("RGB")


# =============================================================================
# Main Entry Point
# =============================================================================
def render_text_overlay(
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Path | None = None,
    font_path_en: Path | None = None,
) -> Image.Image:
    """Render text overlay on a 480x100 white canvas.

    Uses error-diffusion dithering with pure black/white palette for smooth edges.
    The result should be composited onto the final canvas after photo dithering.

    Args:
        candidate: Photo metadata for text content
        lang: Display language code ('zh' or 'en')
        font_path_zh: Path to Chinese font
        font_path_en: Path to English font

    Returns:
        RGB image (480x100) with black text on white background
    """
    # Create white text canvas
    canvas = Image.new("RGB", (TEXT_CANVAS_WIDTH, TEXT_CANVAS_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Select font based on language
    font_path = font_path_zh if lang == "zh" else font_path_en
    if not font_path:
        font_path = font_path_zh or font_path_en

    # Select font sizes based on language
    caption_size = CAPTION_FONT_SIZE_ZH if lang == "zh" else CAPTION_FONT_SIZE_EN
    meta_size = DATE_LOCATION_FONT_SIZE_ZH if lang == "zh" else DATE_LOCATION_FONT_SIZE_EN

    font_caption = load_font(caption_size, font_path)
    font_meta = load_font(meta_size, font_path)

    text_width = TEXT_CANVAS_WIDTH - 2 * TEXT_PADDING_X

    # Get caption: prefer enhanced, fallback to original
    caption = ""
    if candidate.enhanced_caption_json:
        caption = candidate.enhanced_caption_json.get(lang, "")
    if not caption and candidate.caption_json:
        caption = candidate.caption_json.get(lang, "")
        if not caption:
            caption = next(iter(candidate.caption_json.values()), "")

    # Draw caption (1-2 lines)
    if caption:
        lines = wrap_text(draw, caption, font_caption, text_width, max_lines=2, lang=lang)
        y = CAPTION_TOP_Y
        for line in lines:
            draw.text((TEXT_PADDING_X, y), line, font=font_caption, fill=(0, 0, 0))
            y += CAPTION_LINE_HEIGHT

    # Draw date (left-aligned)
    date_str = format_date_display(candidate.exif_datetime, lang)
    if date_str:
        draw.text((TEXT_PADDING_X, DATE_LOCATION_Y), date_str, font=font_meta, fill=(0, 0, 0))

    # Get location
    location = ""
    if candidate.location_json:
        location = candidate.location_json.get(lang, "")
        if not location:
            location = next(iter(candidate.location_json.values()), "")

    # Draw location (right-aligned)
    if location:
        loc_width = draw.textlength(location, font=font_meta)
        loc_x = TEXT_PADDING_X + text_width - loc_width
        if loc_x < TEXT_PADDING_X:
            loc_x = TEXT_PADDING_X
        draw.text((loc_x, DATE_LOCATION_Y), location, font=font_meta, fill=(0, 0, 0))

    # Apply error-diffusion dithering with pure black/white palette
    # This creates smooth text edges (not jagged like hard binarization)
    canvas = _dither_text_area(canvas)

    return canvas
