"""Canvas composition for 7.3" E6 6-color e-ink display (GDEP073E01).

Handles photo resizing, text overlay, and final canvas assembly.
This is the high-level entry point for rendering photos with layout.

Hardware constants are hardcoded here since they're tied to the display panel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .database import PhotoCandidate
from .dither import apply_dither, pack_to_4bpp

# =============================================================================
# Display Constants (hardcoded for GDEP073E01 panel)
# =============================================================================
CANVAS_WIDTH = 480
CANVAS_HEIGHT = 800

# =============================================================================
# Layout Constants
# =============================================================================
TEXT_AREA_HEIGHT = 100  # Bottom text area height in pixels
PHOTO_AREA_HEIGHT = CANVAS_HEIGHT - TEXT_AREA_HEIGHT  # 700px

# Text positioning
TEXT_PADDING_X = 24  # Horizontal padding for text
TEXT_AREA_TOP = CANVAS_HEIGHT - TEXT_AREA_HEIGHT + 10  # y = 710
CAPTION_LINE_HEIGHT = 24  # Line height for caption
DATE_LOCATION_Y = TEXT_AREA_TOP + 54  # y = 754

# Font sizes (English fonts appear larger at same point size, so use smaller values)
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
    """Convert 'YYYY-MM-DD' to display format based on language.

    Args:
        date_str: Date string in YYYY-MM-DD format
        lang: Language code ('zh' for numeric, 'en' for short format)

    Returns:
        Formatted date string
    """
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
            # English format: "Apr 27, 2026"
            return f"{MONTH_ABBR.get(month, str(month))} {day}, {year}"
        else:
            # Chinese/numeric format: "2026.4.27"
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
    """Wrap text to fit within max_width, returning up to max_lines.

    Args:
        draw: PIL ImageDraw instance
        text: Text to wrap
        font: Font to use for measuring
        max_width: Maximum width in pixels
        max_lines: Maximum number of lines
        lang: Language code ('zh' for char-by-char, 'en' for word-boundary)

    Returns:
        List of wrapped lines (up to max_lines)
    """
    if not text:
        return []

    lines: list[str] = []

    if lang == "en":
        # English: break at word boundaries
        words = text.split(" ")
        line = ""

        for word in words:
            if line:
                test = line + " " + word
            else:
                test = word

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
                    # Single word too long, force break
                    lines.append(word)
                    if len(lines) >= max_lines:
                        break
                    line = ""

        if line and len(lines) < max_lines:
            lines.append(line)
    else:
        # Chinese: character by character
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
    """Load font at specified size, falling back to default if unavailable.

    Args:
        size: Font size in pixels
        font_path: Optional path to TTF font file

    Returns:
        PIL Font object
    """
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass

    # Fallback to PIL default font
    return ImageFont.load_default()


# =============================================================================
# Photo Processing
# =============================================================================
def resize_photo_for_display(img: Image.Image) -> Image.Image:
    """Resize and crop photo to fill the photo area (480x700).

    Auto-rotates landscape photos 90 degrees to better fill portrait canvas.
    Uses CSS 'background-size: cover' approach.

    Args:
        img: Input PIL Image (any size)

    Returns:
        Resized and cropped image (exactly 480x700)
    """
    img_w, img_h = img.size

    # Auto-rotate landscape photos for portrait canvas
    if img_w > img_h and PHOTO_AREA_HEIGHT > CANVAS_WIDTH:
        img = img.rotate(90, expand=True)
        img_w, img_h = img.size

    # Scale to cover photo area
    scale = max(CANVAS_WIDTH / img_w, PHOTO_AREA_HEIGHT / img_h)
    draw_w = int(img_w * scale)
    draw_h = int(img_h * scale)

    img_resized = img.resize((draw_w, draw_h), Image.LANCZOS)

    # Center crop to exact photo area size
    left = max(0, (draw_w - CANVAS_WIDTH) // 2)
    top = max(0, (draw_h - PHOTO_AREA_HEIGHT) // 2)

    return img_resized.crop((left, top, left + CANVAS_WIDTH, top + PHOTO_AREA_HEIGHT))


# =============================================================================
# Text Overlay
# =============================================================================
def draw_text_area(
    canvas: Image.Image,
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Path | None = None,
    font_path_en: Path | None = None,
) -> None:
    """Draw text overlay on the bottom 100px of canvas.

    Args:
        canvas: RGB canvas to draw on (modified in-place)
        candidate: Photo metadata for text content
        lang: Display language code
        font_path_zh: Path to Chinese font
        font_path_en: Path to English font
    """
    draw = ImageDraw.Draw(canvas)

    # Select font based on language
    font_path = font_path_zh if lang == "zh" else font_path_en
    if not font_path:
        # Fallback to the other font if primary not available
        font_path = font_path_zh or font_path_en

    # Select font sizes based on language (English fonts appear larger)
    caption_size = CAPTION_FONT_SIZE_ZH if lang == "zh" else CAPTION_FONT_SIZE_EN
    meta_size = DATE_LOCATION_FONT_SIZE_ZH if lang == "zh" else DATE_LOCATION_FONT_SIZE_EN

    # Load fonts
    font_caption = load_font(caption_size, font_path)
    font_meta = load_font(meta_size, font_path)

    text_width = CANVAS_WIDTH - 2 * TEXT_PADDING_X

    # Get caption: prefer enhanced, fallback to original
    caption = ""
    # Try enhanced caption first
    if candidate.enhanced_caption_json:
        caption = candidate.enhanced_caption_json.get(lang, "")
    # Fallback to original caption
    if not caption and candidate.caption_json:
        caption = candidate.caption_json.get(lang, "")
        if not caption:
            # Fallback to first available language
            caption = next(iter(candidate.caption_json.values()), "")

    # Draw caption (1-2 lines)
    if caption:
        lines = wrap_text(draw, caption, font_caption, text_width, max_lines=2, lang=lang)
        y = TEXT_AREA_TOP
        for line in lines:
            draw.text((TEXT_PADDING_X, y), line, font=font_caption, fill=(0, 0, 0))
            y += CAPTION_LINE_HEIGHT

    # Draw date (left-aligned)
    date_str = format_date_display(candidate.exif_datetime, lang)
    if date_str:
        draw.text((TEXT_PADDING_X, DATE_LOCATION_Y), date_str, font=font_meta, fill=(0, 0, 0))

    # Get location for display language (fallback to first available)
    location = ""
    if candidate.location_json:
        location = candidate.location_json.get(lang, "")
        if not location:
            # Fallback to first available language
            location = next(iter(candidate.location_json.values()), "")

    # Draw location (right-aligned)
    if location:
        loc_width = draw.textlength(location, font=font_meta)
        loc_x = TEXT_PADDING_X + text_width - loc_width
        if loc_x < TEXT_PADDING_X:
            loc_x = TEXT_PADDING_X
        draw.text((loc_x, DATE_LOCATION_Y), location, font=font_meta, fill=(0, 0, 0))


# =============================================================================
# Canvas Composition
# =============================================================================
def compose_canvas(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Union[str, Path, None] = None,
    font_path_en: Union[str, Path, None] = None,
) -> Image.Image:
    """Compose the full 480x800 canvas with photo and text overlay.

    Args:
        photo_path: Path to the photo file
        candidate: Photo metadata for text content
        lang: Display language code
        font_path_zh: Path to Chinese font
        font_path_en: Path to English font

    Returns:
        RGB image (480x800) ready for dithering
    """
    # Load photo with EXIF orientation
    img = Image.open(photo_path)
    img = ImageOps.exif_transpose(img).convert("RGB")

    # Create white canvas
    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255))

    # Resize and paste photo to top area
    photo_area = resize_photo_for_display(img)
    canvas.paste(photo_area, (0, 0))

    # Draw text overlay
    draw_text_area(
        canvas,
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
    )

    return canvas


# =============================================================================
# Main Entry Point
# =============================================================================
def render(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Union[str, Path, None] = None,
    font_path_en: Union[str, Path, None] = None,
) -> bytes:
    """Render photo with text overlay to 192KB 4bpp binary.

    Args:
        photo_path: Path to the photo file
        candidate: Photo metadata for text content
        lang: Display language code
        font_path_zh: Path to Chinese font
        font_path_en: Path to English font

    Returns:
        192,000 bytes of 4bpp packed pixel data for ESP32 display
    """
    # Compose canvas with photo and text
    canvas = compose_canvas(photo_path, candidate, lang, font_path_zh, font_path_en)

    # Apply 6-color dithering
    dithered = apply_dither(canvas)

    # Pack to 4bpp binary
    return pack_to_4bpp(dithered)


def render_preview(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Union[str, Path, None] = None,
    font_path_en: Union[str, Path, None] = None,
) -> bytes:
    """Generate PNG preview of the composed layout.

    Args:
        photo_path: Path to the photo file
        candidate: Photo metadata for text content
        lang: Display language code
        font_path_zh: Path to Chinese font
        font_path_en: Path to English font

    Returns:
        PNG image data as bytes
    """
    from io import BytesIO

    # Compose canvas with photo and text
    canvas = compose_canvas(photo_path, candidate, lang, font_path_zh, font_path_en)

    # Apply dithering
    dithered = apply_dither(canvas)

    # Return as PNG
    buffer = BytesIO()
    dithered.save(buffer, format="PNG")
    return buffer.getvalue()
