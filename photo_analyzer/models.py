"""Data models for photo analysis."""

from dataclasses import dataclass


@dataclass
class ExifInfo:
    """EXIF metadata extracted from an image."""

    width: int | None = None
    height: int | None = None
    datetime: str | None = None  # Original EXIF datetime string
    model: str | None = None  # Camera/device model
    gps_lat: float | None = None
    gps_lon: float | None = None


@dataclass
class VlmResponse:
    """Parsed response from VLM API."""

    description: str  # Photo description (80-200 chars)
    photo_type: str  # Category: 人物/家庭/旅行/风景/...
    memory_score: float  # Worth remembering (0-100)
    beauty_score: float  # Visual quality (0-100)
    reason: str  # Score explanation


@dataclass
class PhotoRecord:
    """Complete photo analysis record for database storage."""

    path: str  # Primary key (absolute path)
    description: str | None = None
    photo_type: str | None = None
    memory_score: float | None = None
    beauty_score: float | None = None
    reason: str | None = None
    caption: str | None = None  # Creative one-liner for display
    width: int | None = None
    height: int | None = None
    exif_datetime: str | None = None  # YYYY-MM-DD format
    exif_model: str | None = None
    exif_gps_lat: float | None = None
    exif_gps_lon: float | None = None
    location_city: str = ""  # City from GPS lookup

    @classmethod
    def from_analysis(
        cls,
        path: str,
        vlm_response: VlmResponse,
        exif_info: ExifInfo,
        caption: str | None,
        location_city: str,
        travel_bonus_applied: bool = False,
    ) -> "PhotoRecord":
        """Create a PhotoRecord from VLM response and EXIF info."""
        memory_score = vlm_response.memory_score
        if travel_bonus_applied:
            memory_score = min(memory_score + 5.0, 100.0)

        return cls(
            path=path,
            description=vlm_response.description,
            photo_type=vlm_response.photo_type,
            memory_score=memory_score,
            beauty_score=vlm_response.beauty_score,
            reason=vlm_response.reason,
            caption=caption,
            width=exif_info.width,
            height=exif_info.height,
            exif_datetime=exif_info.datetime,
            exif_model=exif_info.model,
            exif_gps_lat=exif_info.gps_lat,
            exif_gps_lon=exif_info.gps_lon,
            location_city=location_city,
        )
