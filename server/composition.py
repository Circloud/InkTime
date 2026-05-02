"""Canvas composition for 7.3" E6 6-color e-ink display (GDEP073E01).

Two-pass rendering for optimal quality:
1. Dither photo area only (error diffusion for smooth gradients)
2. Render text area separately (dithered with B/W palette for smooth edges)
3. Composite both into final canvas
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from PIL import Image, ImageOps

from .database import PhotoCandidate
from .dither import apply_dither, pack_to_4bpp, CANVAS_WIDTH, CANVAS_HEIGHT, PHOTO_AREA_HEIGHT
from .text_overlay import render_text_overlay


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
    """Render photo with text overlay to 192KB 4bpp binary.

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

    # 3. Render text overlay (crisp black on white)
    text_overlay = render_text_overlay(
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
        dither_mode=text_dither_mode,
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

    # 3. Render text overlay (crisp black on white)
    text_overlay = render_text_overlay(
        candidate,
        lang=lang,
        font_path_zh=Path(font_path_zh) if font_path_zh else None,
        font_path_en=Path(font_path_en) if font_path_en else None,
        dither_mode=text_dither_mode,
    )

    # 4. Composite: photo on top, text on bottom
    final_canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255))
    final_canvas.paste(dithered_photo, (0, 0))
    final_canvas.paste(text_overlay, (0, PHOTO_AREA_HEIGHT))

    # 5. Return as PNG
    buffer = BytesIO()
    final_canvas.save(buffer, format="PNG")
    return buffer.getvalue()
