"""Canvas rendering for 7.3" E6 6-color e-ink display (GDEP073E01).

Two-pass rendering for optimal quality:
1. Dither photo area only (error diffusion for smooth gradients)
2. Render text area separately (dithered with B/W palette for smooth edges)
3. Composite both into final canvas
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from PIL import Image, ImageDraw, ImageFont, ImageOps
from epaper_dithering import dither_image, DitherMode, ColorPalette

from .database import PhotoCandidate
from .dither import apply_dither, pack_to_4bpp, CANVAS_WIDTH, CANVAS_HEIGHT, PHOTO_AREA_HEIGHT, DITHER_MODE_MAP


# =============================================================================
# Text Area Dimensions
# =============================================================================
TEXT_CANVAS_HEIGHT = 100  # Bottom 100px for text

# =============================================================================
# Text Layout Constants (relative to text canvas, y=0 at top)
# =============================================================================
TEXT_PADDING_X = 24
CAPTION_TOP_Y = 10  # Caption starts 10px from top
DATE_LOCATION_Y = 64  # Date/location line
CAPTION_LINE_HEIGHT = 24

# Font sizes (English fonts appear larger at same point size)
CAPTION_FONT_SIZE_ZH = 22
CAPTION_FONT_SIZE_EN = 18
DATE_LOCATION_FONT_SIZE_ZH = 20
DATE_LOCATION_FONT_SIZE_EN = 16

# Month names for English date formatting
MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

# =============================================================================
# Pure Black/White Palette for Text Dithering
# =============================================================================
_BW_PALETTE = ColorPalette(
    colors={'black': (0, 0, 0), 'white': (255, 255, 255)},
    accent='black'
)


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


# =============================================================================
# Photo Processing
# =============================================================================
def resize_photo_for_display(img: Image.Image) -> Image.Image:
    """Resize and crop photo to fill the photo area (480x700).

    Auto-rotates landscape photos 90 degrees to better fill portrait canvas.
    Uses CSS 'background-size: cover' approach.
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
# Text Area Rendering
# =============================================================================
def _dither_text_area(img: Image.Image, mode: str = "atkinson") -> Image.Image:
    """Apply error-diffusion dithering to text area with pure black/white palette.

    Args:
        img: RGB image with anti-aliased text
        mode: Dithering algorithm (atkinson, floyd_steinberg, burkes, etc.)

    Returns:
        RGB image with only pure black (0,0,0) and pure white (255,255,255)
    """
    dither_mode = DITHER_MODE_MAP.get(mode, DitherMode.ATKINSON)

    dithered = dither_image(
        img,
        _BW_PALETTE,
        mode=dither_mode,
        serpentine=True,
    )
    return dithered.convert("RGB")


def _render_text_area(
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Path | None = None,
    font_path_en: Path | None = None,
    dither_mode: str = "atkinson",
) -> Image.Image:
    """Render text area on a 480x100 white canvas.

    Uses error-diffusion dithering with pure black/white palette for smooth edges.

    Args:
        candidate: Photo metadata for text content
        lang: Display language code ('zh' or 'en')
        font_path_zh: Path to Chinese font
        font_path_en: Path to English font
        dither_mode: Dithering algorithm for text (default: atkinson)

    Returns:
        RGB image (480x100) with black text on white background
    """
    # Create white text canvas
    canvas = Image.new("RGB", (CANVAS_WIDTH, TEXT_CANVAS_HEIGHT), (255, 255, 255))
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

    text_width = CANVAS_WIDTH - 2 * TEXT_PADDING_X

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
    canvas = _dither_text_area(canvas, mode=dither_mode)

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
    photo_dither_mode: str = "burkes",
    photo_tone: float = 0.0,
    text_dither_mode: str = "atkinson",
) -> bytes:
    """Render photo with text area to 192KB 4bpp binary.

    Uses two-pass rendering for optimal quality:
    1. Dither photo area only (error diffusion for smooth gradients)
    2. Render text area separately (dithered with B/W palette for smooth edges)
    3. Composite both into final canvas
    """
    # Load photo with EXIF orientation
    img = Image.open(photo_path)
    img = ImageOps.exif_transpose(img).convert("RGB")

    # 1. Resize photo to 480x700
    photo_area = resize_photo_for_display(img)

    # 2. Dither photo area only
    dithered_photo = apply_dither(photo_area, mode=photo_dither_mode, tone=photo_tone)

    # 3. Render text area
    text_area = _render_text_area(
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
        dither_mode=text_dither_mode,
    )

    # 4. Composite: photo on top, text on bottom
    final_canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255))
    final_canvas.paste(dithered_photo, (0, 0))
    final_canvas.paste(text_area, (0, PHOTO_AREA_HEIGHT))

    # 5. Pack to 4bpp binary
    return pack_to_4bpp(final_canvas)


def render_preview(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Union[str, Path, None] = None,
    font_path_en: Union[str, Path, None] = None,
    photo_dither_mode: str = "burkes",
    photo_tone: float = 0.0,
    text_dither_mode: str = "atkinson",
) -> bytes:
    """Generate PNG preview of the composed layout.

    Uses two-pass rendering for optimal quality.
    """
    from io import BytesIO

    # Load photo with EXIF orientation
    img = Image.open(photo_path)
    img = ImageOps.exif_transpose(img).convert("RGB")

    # 1. Resize photo to 480x700
    photo_area = resize_photo_for_display(img)

    # 2. Dither photo area only
    dithered_photo = apply_dither(photo_area, mode=photo_dither_mode, tone=photo_tone)

    # 3. Render text area
    text_area = _render_text_area(
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
        dither_mode=text_dither_mode,
    )

    # 4. Composite: photo on top, text on bottom
    final_canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255))
    final_canvas.paste(dithered_photo, (0, 0))
    final_canvas.paste(text_area, (0, PHOTO_AREA_HEIGHT))

    # 5. Return as PNG
    buffer = BytesIO()
    final_canvas.save(buffer, format="PNG")
    return buffer.getvalue()
