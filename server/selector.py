"""Photo selection algorithm with offset expansion.

Selection order = ranking order:
1. Smaller offset from target date first (exact match -> +1 day -> -1 day -> +2 day -> ...)
2. Within each date, recent years first, then higher memory score
3. Returns exactly `quantity` photos, or raises if not enough candidates
"""

from __future__ import annotations

from datetime import date, timedelta

from .config import settings
from .database import PhotoCandidate, get_photos_for_month_day


def generate_date_sequence(target: date, max_offset: int = 365) -> list[date]:
    """Generate dates in selection order: target, then +-1, +-2, etc.

    Example for target=2026-04-24:
    [2026-04-24, 2026-04-25, 2026-04-23, 2026-04-26, 2026-04-22, ...]
    """
    dates = [target]
    for offset in range(1, max_offset + 1):
        dates.append(target + timedelta(days=offset))
        dates.append(target - timedelta(days=offset))
    return dates


def select_photos_for_date(
    target_date: date,
    quantity: int | None = None,
    min_memory_score: float | None = None,
) -> list[PhotoCandidate]:
    """Select photos for a given date using offset expansion.

    Args:
        target_date: The target date (e.g., today)
        quantity: Number of photos to select (default from settings)
        min_memory_score: Minimum memory score threshold

    Returns:
        List of exactly `quantity` PhotoCandidates

    Raises:
        ValueError: If not enough photos found after searching
    """
    if quantity is None:
        quantity = settings.daily_photo_quantity
    if min_memory_score is None:
        min_memory_score = settings.memory_threshold

    selected: list[PhotoCandidate] = []
    seen_paths: set[str] = set()

    # Generate dates in selection order
    date_sequence = generate_date_sequence(target_date)

    for check_date in date_sequence:
        if len(selected) >= quantity:
            break

        # Get photos for this MM-DD
        candidates = get_photos_for_month_day(
            month=check_date.month,
            day=check_date.day,
            min_memory_score=min_memory_score,
        )

        # Add candidates not already selected
        for photo in candidates:
            if photo.path not in seen_paths:
                selected.append(photo)
                seen_paths.add(photo.path)
                if len(selected) >= quantity:
                    break

    if len(selected) < quantity:
        raise ValueError(
            f"Could not find {quantity} photos. "
            f"Found {len(selected)} after searching {len(date_sequence)} dates."
        )

    return selected[:quantity]


def select_photos_for_today() -> list[PhotoCandidate]:
    """Select photos for today's date."""
    return select_photos_for_date(date.today())
