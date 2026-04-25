"""ESP32 API endpoints.

Routes:
    GET /api/photo/<index>  - Get rendered photo binary (192KB)
    GET /api/status         - Get server status
"""

from flask import Blueprint, Response, abort

from .cache import cache

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/photo/<int:index>")
def get_photo(index: int) -> Response:
    """Get rendered photo by index.

    ESP32 calls this endpoint to download photos.
    Index wraps: 0, 1, 2, 0, 1, 2, ...
    """
    try:
        cached = cache.get(index)
    except IndexError:
        abort(404)
    except RuntimeError:
        abort(500)

    return Response(
        cached.binary,
        mimetype="application/octet-stream",
        headers={
            "X-Photo-Date": cached.candidate.exif_datetime,
            "X-Photo-Score": f"{cached.candidate.memory_score:.1f}",
        },
    )


@api_bp.route("/status")
def status() -> dict:
    """Get server status."""
    return {
        "status": "ok",
        "cache_date": str(cache.current_date) if cache.current_date else None,
        "photo_count": cache.count,
    }
