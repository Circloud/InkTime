"""In-memory cache for daily photo selection.

Date-based lazy refresh: photos are selected and rendered on first request
of each day, then cached in memory for subsequent requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .database import PhotoCandidate
from .composition import render
from .selector import select_photos_for_date
from .config import settings


@dataclass
class CachedPhoto:
    """A cached rendered photo."""

    candidate: PhotoCandidate
    binary: bytes  # 192KB rendered data


class DailyPhotoCache:
    """Cache for daily photo selection with date-based refresh."""

    def __init__(self) -> None:
        self._date: date | None = None
        self._photos: list[CachedPhoto] = []

    def get(self, index: int) -> CachedPhoto:
        """Get photo by index (0-indexed). Triggers refresh if new day.

        Args:
            index: Photo index (0, 1, 2, ...)

        Returns:
            CachedPhoto with candidate info and rendered binary

        Raises:
            IndexError: If index out of range
            RuntimeError: If no photos could be rendered
        """
        today = date.today()

        # Refresh if new day or empty
        if self._date != today or not self._photos:
            self._refresh(today)

        if index < 0 or index >= len(self._photos):
            raise IndexError(f"Photo index {index} out of range (0-{len(self._photos)-1})")

        return self._photos[index]

    def get_all(self) -> list[CachedPhoto]:
        """Get all cached photos. Triggers refresh if new day."""
        today = date.today()
        if self._date != today or not self._photos:
            self._refresh(today)
        return self._photos

    def _refresh(self, target_date: date) -> None:
        """Refresh cache with new photo selection for target date."""
        # Select photos
        candidates = select_photos_for_date(target_date)

        # Render all photos with layout (photo + text overlay)
        photos: list[CachedPhoto] = []
        for candidate in candidates:
            try:
                binary = render(
                    candidate.path,
                    candidate,
                    font_path=settings.font_path,
                )
                photos.append(CachedPhoto(candidate=candidate, binary=binary))
            except Exception as e:
                # Skip photos that fail to render
                print(f"Warning: Failed to render {candidate.path}: {e}")
                continue

        if not photos:
            raise RuntimeError("No photos could be rendered")

        self._date = target_date
        self._photos = photos

    @property
    def current_date(self) -> date | None:
        """Get the date of current cache."""
        return self._date

    @property
    def count(self) -> int:
        """Get number of cached photos."""
        return len(self._photos)


# Global cache instance
cache = DailyPhotoCache()
