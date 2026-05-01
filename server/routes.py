"""ESP32 API endpoints.

Routes:
    GET /api/photo       - Get next photo binary (192KB), server tracks index
    GET /api/status      - Get server status
"""

from flask import Blueprint, Response

from .cache import cache

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/photo")
def get_photo() -> Response:
    """Get next photo in sequence.

    ESP32 calls this endpoint to download photos.
    Server tracks the current index and increments after each request.
    Index wraps around when reaching the end of the photo list.

    Returns:
        200 OK with photo binary and headers
        204 No Content if no photos available
        500 Internal Server Error on cache error
    """
    try:
        cached = cache.get_next()
    except RuntimeError:
        # No photos available
        return Response(status=204)

    return Response(
        cached.binary,
        mimetype="application/octet-stream",
        headers={
            "X-Photo-Date": cached.candidate.exif_datetime,
            "X-Photo-Score": f"{cached.candidate.memory_score:.1f}",
            "X-Photo-Index": str(cache.current_index),
            "X-Photo-Total": str(cache.count),
        },
    )


@api_bp.route("/status")
def status() -> dict:
    """Get server status."""
    return {
        "status": "ok",
        "cache_date": str(cache.current_date) if cache.current_date else None,
        "photo_count": cache.count,
        "current_index": cache.current_index,
    }
