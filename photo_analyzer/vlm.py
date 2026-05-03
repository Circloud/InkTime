"""VLM API client for photo analysis."""

import base64
import io
import json
import logging
from pathlib import Path

import requests
from PIL import Image, ImageOps

from .config import settings
from .models import ExifInfo, VlmResponse

logger = logging.getLogger(__name__)

# JSON schema for photo analysis response
PHOTO_ANALYSIS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "photo_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Photo description in Chinese (80-200 characters)",
                },
                "photo_type": {
                    "type": "string",
                    "description": "Category: 人物/孩子/猫咪/狗狗/学校/家庭/旅行/风景/美食/宠物/日常/新发现/文档/杂物/其他, can have multiple types",
                },
                "memory_score": {
                    "type": "number",
                    "description": "Worth remembering score (0-100, 1 decimal place)",
                },
                "beauty_score": {
                    "type": "number",
                    "description": "Visual quality score (0-100, 1 decimal place)",
                },
                "reason": {
                    "type": "string",
                    "description": "Brief explanation in Chinese (max 60 characters)",
                },
            },
            "required": ["description", "photo_type", "memory_score", "beauty_score", "reason"],
        },
    },
}

# JSON schema for caption response
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
                    "description": "Creative one-liner caption in Chinese (8-30 characters)",
                },
            },
            "required": ["caption"],
        },
    },
}

# Main analysis prompt for photo scoring (Chinese)
VLM_SYSTEM_PROMPT = """你是一个"个人相册照片评估助手"，擅长理解真实照片的内容，并从回忆价值和美观角度打分。
你会收到一张照片，你的任务是：
1）用中文详细描述照片内容（80~200 字），
2）判断照片的大致类型：人物/孩子/猫咪/狗狗/学校/家庭/旅行/风景/美食/宠物/日常/新发现/文档/杂物/其他，一张照片可以有不止一个类型。
3）给出 0~100 的"值得回忆度" memory_score（精确到一位小数），
4）给出 0~100 的"美观程度" beauty_score（精确到一位小数），
5）用简短中文 解释原因（不超过 60 字）。
q
【值得回忆度（memory_score）评分方法】
请先按照值得回忆的程度，先确定照片的'得分区间'，再进行精调：
如何判定值得回忆度（memory_score）的得分区间：
- 垃圾/随手拍/手机截图/无意义记录：40.0 分以下（常见为 0~25；若还能勉强辨认但无故事，也不要超过 40）。
- 稍微有点可回忆价值：以 65.0 分为中心（大多落在 55~73）。
- 不错的回忆价值：以 75 分为中心（大多落在 70~80）。
- 特别精彩、强烈值得珍藏：以 85 分为中心（大多落在 75~95）。
- 极其珍贵、难以复制、带来强烈情感价值的“人生照片”：95~100 分（非常罕见，通常需要满足多条加分项叠加后达到这个区间）。

如何继续精调 memory_score 得分（若同时符合几条加分项，加分可叠加）：
- 人物与关系：画面中含有面积较大的人脸，有人物互动，或属于合影 → 大幅提高评分；
- 事件性：生日/聚会/仪式/舞台/明显事件 → 少许提高评分；
- 稀缺性与不可复现：明显"这一刻很难再来一次" → 大幅提高评分；
- 情绪强度：笑、哭、惊喜、拥抱、互动、氛围强 → 少许提高评分；
- 信息密度：画面能讲清楚发生了什么 → 微微提高评分；
- 优美风景：画面中含有壮丽的自然风光，或精美、有秩序感的构图 → 少许提高评分；
- 旅行意义：异地、地标、旅途情景 → 少许提高评分。
- 画质：画面不清晰、模糊、有残影、虚焦 → 微微降低评分。

【重点照片的处理】
如果画面中含有：孩子/小狗/猫咪/宠物题材，这些主题更容易产生高回忆价值，请直接以 75 分为中心，并大幅提高评分。

【明显低价值图片的处理】
对以下低价值图片，必须将 memory_score 压低到 0~25（最多不超过 40）：
- 裸体、低俗、色情或违反公序良俗的图片。
- 账单、收据、广告、PPT照片、纯粹备忘性质的照片等。
- 屏幕截图，包括但不限于聊天截图、微信朋友圈截图、QQ动态截图、游戏截图等，这些均为其他人的生活碎片，对照片持有者本身没有回忆价值（除非截图内容具有明确的故事性，例如某些特定的聊天记录）。

【美观分（beauty_score）评分方法】
- 美观分只评价视觉要素：构图、光线、清晰度、色彩、主体突出，不评价照片内容的好坏。
- 不要被"孩子/猫/旅行"常见高分主题绑架美观分：主题不等于好看。"""

VLM_USER_PROMPT = "下面是照片的内容，请结合图像本身完成上述任务。"

# Language-specific caption prompts
CAPTION_PROMPTS = {
    "zh": {
        "system": """你是一位为「电子相框」撰写旁白短句的中文文案助手。
你的目标不是描述画面，而是为画面补上一点"画外之意"。

创作原则：
1. 避免使用以下陈词滥调式的词语（但不绝对禁止）：世界、生活、日子、梦、时光、岁月、温柔、治愈、刚刚好、悄悄、慢慢 等。
2. 严禁使用如下句式：……里……着整个世界；……里……着整个夏天；……得像……（简单的比喻）；……比……还……；……得比……更……。
3. 只基于图片中能确定的信息进行联想，不要虚构时间、人物关系、事件背景。
4. 文案应自然、有趣，带一点幽默或者诗意，但请避免过度煽情、鸡汤、矫情的表述。
5. 不要复述画面内容本身，而是写"看完画面后，心中的一句独白"。
6. 可以尝试从以下角度进行创作：
   - 捕捉画面中的微妙情绪
   - 轻微自嘲或冷幽默
   - 对时间、记忆、瞬间的含蓄感受
   - 看似平淡却别有余味的一句话
7. 避免小学生作文式的、套路式的模板化表达。

格式要求：
- 只输出一句中文短句，不需要任何其他解释，句末须加标点。
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
4. AVOID overused sentence structures:
   - "Sometimes..." as an opening — EXTREMELY overused, find another way
   - "The [noun] [verb]..." as an opening — too repetitive
   - "A [adjective] [noun]..." as an opening — generic
   - "Sunlight catches/catching..." — overused
   - "Waiting for..." — overused
   - "Ready for..." — overused
5. Avoid overused phrases: "a moment in time," "memories," "beautiful day," "life is..."
6. One of these tones often works well:
   - Subtle emotion in everyday moments
   - Light self-deprecation or dry humor
   - A quiet observation that lingers
   - A seemingly plain yet subtly meaningful sentence

Format:
- Output exactly one short sentence in English. No explanations or additional text.
- Aim for 5–15 words, maximum 20 words.
- Don't reference "this photo", "this picture", or similar phrases that point to the image itself.""",
        "user": "Based on this photo, write a caption that fits the rules above.",
    },
}


def encode_image_to_b64(path: Path) -> str:
    """Read image, optionally resize, and encode as base64 JPEG."""
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

        # Resize if needed
        w, h = img.size
        long_edge = max(w, h)
        if settings.vlm_max_long_edge and long_edge > settings.vlm_max_long_edge:
            scale = float(settings.vlm_max_long_edge) / float(long_edge)
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            img = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92, optimize=True)
        return base64.b64encode(out.getvalue()).decode("utf-8")

    except Exception:
        # Fallback: return original bytes if PIL fails
        return base64.b64encode(data).decode("utf-8")


def _build_headers() -> dict[str, str]:
    """Build HTTP headers for VLM API request."""
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def _parse_vlm_response(content: str) -> VlmResponse:
    """Parse VLM JSON response into VlmResponse object."""
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse VLM response as JSON: {content[:200]}")
        raise ValueError("VLM did not return valid JSON")

    return VlmResponse(
        description=str(obj.get("description", "")).strip(),
        photo_type=str(obj.get("photo_type", "")).strip(),
        memory_score=float(obj.get("memory_score", 0.0)),
        beauty_score=float(obj.get("beauty_score", 0.0)),
        reason=str(obj.get("reason", "")).strip(),
    )


def analyze_photo(path: Path) -> tuple[VlmResponse, ExifInfo]:
    """Analyze a photo using VLM and extract EXIF metadata.

    Returns tuple of (VlmResponse, ExifInfo).
    """
    from .exif import read_exif  # Avoid circular import

    # Encode image
    try:
        img_b64 = encode_image_to_b64(path)
    except Exception as e:
        raise RuntimeError(f"Failed to read image: {e}")

    # Extract EXIF
    exif_info = read_exif(path)

    # Build request payload with structured output
    payload = {
        "model": settings.model_name,
        "messages": [
            {"role": "system", "content": VLM_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VLM_USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                ],
            },
        ],
        "temperature": 0.2,
        "stream": False,
        "response_format": PHOTO_ANALYSIS_SCHEMA,
    }

    # Call VLM API
    resp = requests.post(
        settings.api_url,
        headers=_build_headers(),
        json=payload,
        timeout=settings.timeout,
    )

    if not resp.ok:
        logger.error(f"VLM API error: HTTP {resp.status_code}")
        logger.debug(f"Response: {resp.text[:500]}")
        raise RuntimeError(f"VLM request failed: HTTP {resp.status_code}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        logger.error(f"Unexpected VLM response structure: {data}")
        raise RuntimeError(f"Failed to parse VLM response: {e}")

    vlm_response = _parse_vlm_response(content)
    return vlm_response, exif_info


def generate_caption(path: Path, lang: str = "zh") -> str | None:
    """Generate a creative caption for display using VLM.

    Args:
        path: Path to the image file
        lang: Language code for caption generation (e.g., 'zh', 'en')

    Returns:
        Generated caption string, or None if generation failed
    """
    prompts = CAPTION_PROMPTS.get(lang)
    if not prompts:
        logger.warning(f"No caption prompts defined for language: {lang}")
        return None

    try:
        img_b64 = encode_image_to_b64(path)
    except Exception:
        return None

    payload = {
        "model": settings.model_name,
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

    try:
        resp = requests.post(
            settings.api_url,
            headers=_build_headers(),
            json=payload,
            timeout=min(120, settings.timeout),
        )
    except Exception:
        return None

    if not resp.ok:
        return None

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        obj = json.loads(content)
        caption = obj.get("caption", "")
    except Exception:
        return None

    if not isinstance(caption, str):
        caption = str(caption)

    return caption.strip() or None
