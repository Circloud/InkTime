"""Canvas composition for 7.3" E6 6-color e-ink display (GDEP073E01).

Two-pass rendering for optimal quality:
1. Dither photo area only (error diffusion for smooth gradients)
2. Render text area separately (crisp edges, no dithering)
3. Composite both into final canvas
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from PIL import Image, ImageOps

from .database import PhotoCandidate
from .dither import apply_dither, pack_to_4bpp
from .text_overlay import render_text_overlay


# =============================================================================
# Display Constants (hardcoded for GDEP073E01 panel)
# =============================================================================
CANVAS_WIDTH = 480
CANVAS_HEIGHT = 800
PHOTO_AREA_HEIGHT = 700  # Top 700px for photo, bottom 100px for text


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
# Canvas Composition (for backward compatibility / RGB preview)
# =============================================================================
def compose_canvas(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Union[str, Path, None] = None,
    font_path_en: Union[str, Path, None] = None,
) -> Image.Image:
    """Compose the full 480x800 canvas with photo and text overlay.

    This function is kept for backward compatibility and RGB preview purposes.
    For production rendering, use render() which applies two-pass dithering.
    """
    # Load photo with EXIF orientation
    img = Image.open(photo_path)
    img = ImageOps.exif_transpose(img).convert("RGB")

    # Create white canvas
    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255))

    # Resize and paste photo to top area
    photo_area = resize_photo_for_display(img)
    canvas.paste(photo_area, (0, 0))

    # Render and paste text overlay (bottom 100px)
    text_overlay = render_text_overlay(
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
    )
    canvas.paste(text_overlay, (0, PHOTO_AREA_HEIGHT))

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
    dither_mode: str = "burkes",
    tone: float = 0.0,
) -> bytes:
    """Render photo with text overlay to 192KB 4bpp binary.

    Uses two-pass rendering for optimal quality:
    1. Dither photo area only (error diffusion for smooth gradients)
    2. Render text area separately (crisp edges, no dithering)
    3. Composite both into final canvas
    """
    # Load photo with EXIF orientation
    img = Image.open(photo_path)
    img = ImageOps.exif_transpose(img).convert("RGB")

    # 1. Resize photo to 480x700
    photo_area = resize_photo_for_display(img)

    # 2. Dither photo area only
    dithered_photo = apply_dither(photo_area, mode=dither_mode, tone=tone)

    # 3. Render text overlay (crisp black on white)
    text_overlay = render_text_overlay(
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
    )

    # 4. Composite: photo on top, text on bottom
    final_canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255))
    final_canvas.paste(dithered_photo, (0, 0))
    final_canvas.paste(text_overlay, (0, PHOTO_AREA_HEIGHT))

    # 5. Pack to 4bpp binary
    return pack_to_4bpp(final_canvas)


def render_preview(
    photo_path: Union[str, Path],
    candidate: PhotoCandidate,
    lang: str = "zh",
    font_path_zh: Union[str, Path, None] = None,
    font_path_en: Union[str, Path, None] = None,
    dither_mode: str = "burkes",
    tone: float = 0.0,
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
    dithered_photo = apply_dither(photo_area, mode=dither_mode, tone=tone)

    # 3. Render text overlay (crisp black on white)
    text_overlay = render_text_overlay(
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
    )

    # 4. Composite: photo on top, text on bottom
    final_canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255))
    final_canvas.paste(dithered_photo, (0, 0))
    final_canvas.paste(text_overlay, (0, PHOTO_AREA_HEIGHT))

    # 5. Return as PNG
    buffer = BytesIO()
    final_canvas.save(buffer, format="PNG")
    return buffer.getvalue()
