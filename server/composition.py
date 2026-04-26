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

# Font sizes
CAPTION_FONT_SIZE = 22
DATE_LOCATION_FONT_SIZE = 20


# =============================================================================
# Text Utilities
# =============================================================================
def format_date_display(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'YYYY.M.D' format.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Formatted date string like '2026.4.26'
    """
    if not date_str or len(date_str) < 10:
        return ""

    parts = date_str.split("-")
    if len(parts) < 3:
        return date_str

    try:
        year = parts[0]
        month = str(int(parts[1]))  # Remove leading zero
        day = str(int(parts[2]))  # Remove leading zero
        return f"{year}.{month}.{day}"
    except (ValueError, IndexError):
        return date_str


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    """Wrap text to fit within max_width, returning up to max_lines.

    Args:
        draw: PIL ImageDraw instance
        text: Text to wrap
        font: Font to use for measuring
        max_width: Maximum width in pixels
        max_lines: Maximum number of lines

    Returns:
        List of wrapped lines (up to max_lines)
    """
    if not text:
        return []

    lines: list[str] = []
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
    font_path: Path | None = None,
) -> None:
    """Draw text overlay on the bottom 100px of canvas.

    Layout:
    - Caption: 1-2 lines starting at y=710
    - Date: left-aligned at y=754
    - Location: right-aligned at y=754

    Args:
        canvas: RGB canvas to draw on (modified in-place)
        candidate: Photo metadata for text content
        font_path: Optional path to TTF font file
    """
    draw = ImageDraw.Draw(canvas)

    # Load fonts
    font_caption = load_font(CAPTION_FONT_SIZE, font_path)
    font_meta = load_font(DATE_LOCATION_FONT_SIZE, font_path)

    text_width = CANVAS_WIDTH - 2 * TEXT_PADDING_X

    # Draw caption (1-2 lines)
    caption = candidate.caption or ""
    if caption:
        lines = wrap_text(draw, caption, font_caption, text_width, max_lines=2)
        y = TEXT_AREA_TOP
        for line in lines:
            draw.text((TEXT_PADDING_X, y), line, font=font_caption, fill=(0, 0, 0))
            y += CAPTION_LINE_HEIGHT

    # Draw date (left-aligned)
    date_str = format_date_display(candidate.exif_datetime)
    if date_str:
        draw.text((TEXT_PADDING_X, DATE_LOCATION_Y), date_str, font=font_meta, fill=(0, 0, 0))

    # Draw location (right-aligned)
    location = candidate.location_city.strip() if candidate.location_city else ""
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
    font_path: Union[str, Path, None] = None,
) -> Image.Image:
    """Compose the full 480x800 canvas with photo and text overlay.

    Args:
        photo_path: Path to the photo file
        candidate: Photo metadata for text content
        font_path: Optional path to TTF font file for Chinese text

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
    font_path_obj = Path(font_path) if font_path else None
    draw_text_area(canvas, candidate, font_path_obj)

    return canvas


# =============================================================================
# Main Entry Point
# =============================================================================
def render(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    font_path: Union[str, Path, None] = None,
) -> bytes:
    """Render photo with text overlay to 192KB 4bpp binary.

    This is the main entry point for generating e-ink display data
    with the full layout (photo + caption + date + location).

    Args:
        photo_path: Path to the photo file
        candidate: Photo metadata for text content
        font_path: Optional path to TTF font file

    Returns:
        192,000 bytes of 4bpp packed pixel data for ESP32 display
    """
    # Compose canvas with photo and text
    canvas = compose_canvas(photo_path, candidate, font_path)

    # Apply 6-color dithering
    dithered = apply_dither(canvas)

    # Pack to 4bpp binary
    return pack_to_4bpp(dithered)


def render_preview(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    font_path: Union[str, Path, None] = None,
) -> bytes:
    """Generate PNG preview of the composed layout.

    Args:
        photo_path: Path to the photo file
        candidate: Photo metadata for text content
        font_path: Optional path to TTF font file

    Returns:
        PNG image data as bytes
    """
    from io import BytesIO

    # Compose canvas with photo and text
    canvas = compose_canvas(photo_path, candidate, font_path)

    # Apply dithering
    dithered = apply_dither(canvas)

    # Return as PNG
    buffer = BytesIO()
    dithered.save(buffer, format="PNG")
    return buffer.getvalue()
