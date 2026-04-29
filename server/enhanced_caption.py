"""Enhanced caption generation using online VLM API.

This module generates improved captions using a more capable online model
(e.g., GPT-4o) for photos selected for daily display. It runs in parallel
during cache refresh to minimize latency.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path

import requests
from PIL import Image, ImageOps

from .config import settings

logger = logging.getLogger(__name__)

# JSON schema for caption response (same as photo_analyzer/vlm.py)
CAPTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "caption_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "caption": {
                    "type": "string",
                    "description": "Creative one-liner caption (8-30 characters for zh, 5-20 words for en)",
                },
            },
            "required": ["caption"],
        },
    },
}

# Language-specific caption prompts (copied from photo_analyzer/vlm.py)
CAPTION_PROMPTS = {
    "zh": {
        "system": """你是一位为「电子相框」撰写旁白短句的中文文案助手。
你的目标不是描述画面，而是为画面补上一点"画外之意"。

创作原则：
1. 避免使用以下词语：世界、梦、时光、岁月、温柔、治愈、刚刚好、悄悄、慢慢 等（但不是绝对禁止）。
2. 严禁使用如下句式：……里……着整个世界；……里……着整个夏天；……得像……（简单的比喻）；……比……还……；……得比……更……。
3. 只基于图片中能确定的信息进行联想，不要虚构时间、人物关系、事件背景。
4. 文案应自然、有趣，带一点幽默或者诗意，但请避免煽情、鸡汤。
5. 不要复述画面内容本身，而是写"看完画面后，心里多出来的一句话"。
6. 可以偏向以下风格之一：
   - 日常中的微妙情绪
   - 轻微自嘲或冷幽默
   - 对时间、记忆、瞬间的含蓄感受
   - 看似平淡但有余味的一句判断
7. 避免小学生作文式的、套路式的模板化表达。

格式要求：
- 只输出一句中文短句，不要换行，不要引号，不要任何解释。
- 建议长度 8～24 个汉字，最多不超过 30 个汉字。
- 不要出现"这张照片""这一刻""那天"等指代照片本身的词。""",
        "user": "请基于这张照片，生成一句符合规则的中文文案。",
    },
    "en": {
        "system": """You are a caption writer for a digital photo frame. Your job is not to describe the image, but to add a touch of "beyond the frame."

Writing principles:
1. Be natural, witty, or quietly poetic — but avoid clichés and inspirational quotes.
2. Don't simply describe what's visible. Write what comes to mind after seeing it.
3. Base your caption only on what you can verify in the image. Don't invent details.
4. Avoid overused phrases like "a moment in time," "memories," "beautiful day," or "life is..."
5. One of these tones often works well:
   - Subtle emotion in everyday moments
   - Light self-deprecation or dry humor
   - A quiet observation that lingers

Format:
- Output exactly one short sentence in English.
- No quotation marks. No explanations.
- Aim for 5–15 words, maximum 20 words.
- Don't reference "this photo" or "this moment." """,
        "user": "Based on this photo, write a caption that fits the rules above.",
    },
}


def encode_image_to_b64(path: Path) -> str:
    """Read image, optionally resize, and encode as base64 JPEG.

    Same logic as photo_analyzer/vlm.py but duplicated here to avoid
    cross-package dependency for server module.
    """
    data = path.read_bytes()

    try:
        img = Image.open(io.BytesIO(data))

        # Handle EXIF rotation
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Convert to RGB
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if needed (max 2560px long edge)
        w, h = img.size
        long_edge = max(w, h)
        max_long_edge = 2560
        if long_edge > max_long_edge:
            scale = float(max_long_edge) / float(long_edge)
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            img = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92, optimize=True)
        return base64.b64encode(out.getvalue()).decode("utf-8")

    except Exception:
        # Fallback: return original bytes if PIL fails
        return base64.b64encode(data).decode("utf-8")


def generate_enhanced_caption(path: Path, lang: str) -> str | None:
    """Generate an enhanced caption for a photo using online VLM.

    Args:
        path: Path to the image file
        lang: Language code for caption generation (e.g., 'zh', 'en')

    Returns:
        Generated caption string, or None if generation failed or disabled
    """
    # Check if feature is enabled
    if not settings.enhanced_caption_enabled:
        return None

    # Check for required config
    if not settings.enhanced_base_url or not settings.enhanced_api_key:
        logger.warning("Enhanced caption API not configured (missing base_url or api_key)")
        return None

    # Get language-specific prompts
    prompts = CAPTION_PROMPTS.get(lang)
    if not prompts:
        logger.warning(f"No caption prompts defined for language: {lang}")
        return None

    # Encode image
    try:
        img_b64 = encode_image_to_b64(path)
    except Exception as e:
        logger.error(f"Failed to encode image {path}: {e}")
        return None

    # Build request payload
    payload = {
        "model": settings.enhanced_model_name,
        "messages": [
            {"role": "system", "content": prompts["system"]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompts["user"]},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                ],
            },
        ],
        "temperature": 0.7,
        "max_tokens": 64,
        "stream": False,
        "response_format": CAPTION_SCHEMA,
    }

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.enhanced_api_key}",
    }

    # Call API with retry
    max_retries = settings.enhanced_retry_times
    last_error: str | None = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                settings.enhanced_base_url,
                headers=headers,
                json=payload,
                timeout=settings.enhanced_timeout,
            )

            if not resp.ok:
                last_error = f"HTTP {resp.status_code}"
                if attempt < max_retries:
                    logger.warning(f"Enhanced caption API error (attempt {attempt}/{max_retries}): {last_error}, retrying...")
                    continue
                else:
                    logger.error(f"Enhanced caption API error after {max_retries} attempts: {last_error}")
                    return None

            # Parse response
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            obj = json.loads(content)
            caption = obj.get("caption", "")

            if not isinstance(caption, str):
                caption = str(caption)

            return caption.strip() or None

        except requests.RequestException as e:
            last_error = str(e)
            if attempt < max_retries:
                logger.warning(f"Enhanced caption API request failed (attempt {attempt}/{max_retries}): {e}, retrying...")
            else:
                logger.error(f"Enhanced caption API request failed after {max_retries} attempts: {e}")
                return None
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse enhanced caption response: {e}")
            return None

    return None
