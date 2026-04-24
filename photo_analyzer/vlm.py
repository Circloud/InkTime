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
                    "description": "Category: 人物/家庭/旅行/风景/美食/宠物/日常/文档/杂物/其他, can have multiple types",
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
2）判断照片的大致类型：人物/孩子/猫咪/家庭/旅行/风景/美食/宠物/日常/文档/杂物/其他，一张照片可以有不止一个类型。
3）给出 0~100 的"值得回忆度" memory_score（精确到一位小数），
4）给出 0~100 的"美观程度" beauty_score（精确到一位小数），
5）用简短中文 reason 解释原因（不超过 60 字）。

【值得回忆度（memory_score）评分方法】
请先按照值得回忆的程度，先确定照片的'得分区间'，再进行精调：
如何判定值得回忆度（memory_score）的得分区间：
- 垃圾/随手拍/无意义记录：40.0 分以下（常见为 0~25；若还能勉强辨认但无故事，也不要超过 39.9）。
- 稍微有点可回忆价值：以 65.0 分为中心（大多落在 58.1~70.3）。
- 不错的回忆价值：以 75 分为中心（大多落在 68.7~82.4）。
- 特别精彩、强烈值得珍藏：以 85 分为中心（大多落在 79.1~95.9）。

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
如果画面中含有：孩子/猫咪/宠物题材，这些主题更容易产生高回忆价值，请直接以 75 分为中心，并大幅提高评分。

【明显低价值图片的处理】
对以下低价值图片，必须将 memory_score 压低到 0~25（最多不超过 39）：
- 裸露、低俗、色情或违反公序良俗的图片。
- 账单、收据、广告、随手拍的杂物、测试图片、屏幕截图等。

【美观分（beauty_score）评分方法】
美观分只评价视觉：构图、光线、清晰度、色彩、主体突出。
不要被"孩子/猫/旅行"主题绑架美观分：主题不等于好看。"""

VLM_USER_PROMPT = "下面是照片的内容，请结合图像本身完成上述任务。"

# Caption generation prompt (Chinese)
CAPTION_SYSTEM_PROMPT = """你是一位为「电子相框」撰写旁白短句的中文文案助手。
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
- 不要出现"这张照片""这一刻""那天"等指代照片本身的词。"""

CAPTION_USER_PROMPT = "请基于这张照片，生成一句符合规则的中文文案。"


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


def generate_caption(path: Path) -> str | None:
    """Generate a creative caption for display using VLM."""
    try:
        img_b64 = encode_image_to_b64(path)
    except Exception:
        return None

    payload = {
        "model": settings.model_name,
        "messages": [
            {"role": "system", "content": CAPTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CAPTION_USER_PROMPT},
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
