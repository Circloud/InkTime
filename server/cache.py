"""In-memory cache for daily photo selection with disk persistence.

Date-based lazy refresh: photos are selected and rendered on first request
of each day, then cached in memory for subsequent requests.

Cache is persisted to disk so server restarts don't trigger re-render
on the same day. On a new day, cache is cleared and regenerated.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .database import PhotoCandidate, get_db, update_enhanced_caption
from .composition import render, render_preview
from .enhanced_caption import generate_enhanced_caption
from .selector import select_photos_for_today
from .config import settings


def _generate_missing_enhanced_captions(
    candidates: list[PhotoCandidate],
    lang: str,
) -> None:
    """Generate enhanced captions in parallel for photos missing them.

    Only generates if:
    - Feature is enabled
    - Photo doesn't have enhanced caption for the language

    Failed generations are silently skipped (will use original caption).
    """
    if not settings.enhanced_caption_enabled:
        return

    # Find candidates missing enhanced caption for this language
    missing = [
        c for c in candidates
        if not c.enhanced_caption_json.get(lang)
    ]

    if not missing:
        return

    print(f"[InkTime] Generating enhanced captions for {len(missing)} photos...")

    def _generate_and_save(candidate: PhotoCandidate) -> None:
        """Generate and save enhanced caption for a single photo."""
        try:
            caption = generate_enhanced_caption(Path(candidate.path), lang)
            if caption:
                with get_db() as conn:
                    update_enhanced_caption(conn, candidate.path, lang, caption)
                # Update in-memory object
                candidate.enhanced_caption_json[lang] = caption
                print(f"[InkTime] Enhanced caption saved for {candidate.path}")
        except Exception as e:
            print(f"Warning: Failed to generate enhanced caption for {candidate.path}: {e}")

    # Execute in parallel
    with ThreadPoolExecutor(max_workers=min(3, len(missing))) as executor:
        futures = {executor.submit(_generate_and_save, c): c for c in missing}

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                candidate = futures[future]
                print(f"Warning: Enhanced caption task failed for {candidate.path}: {e}")


@dataclass
class CachedPhoto:
    """A cached rendered photo."""

    candidate: PhotoCandidate
    binary: bytes  # 192KB rendered data


@dataclass
class CacheMetadata:
    """Metadata for persisted cache, serialized to JSON."""

    date: str  # ISO format: "2026-04-27"
    rendered_lang: str  # Language used for rendering, e.g., "zh"
    enhanced_caption_enabled: bool  # Whether enhanced captions were enabled
    selection_mode: str = "date"  # Selection mode used for this cache
    current_index: int = 0  # Current photo index for sequential display
    photos: list[dict[str, Any]] = field(default_factory=list)

    def save(self, cache_dir: Path) -> None:
        """Save metadata to cache_dir/metadata.json."""
        cache_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = cache_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump({
                "date": self.date,
                "rendered_lang": self.rendered_lang,
                "enhanced_caption_enabled": self.enhanced_caption_enabled,
                "selection_mode": self.selection_mode,
                "current_index": self.current_index,
                "photos": self.photos
            }, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, cache_dir: Path) -> "CacheMetadata | None":
        """Load metadata from cache_dir/metadata.json. Returns None if not found."""
        metadata_path = cache_dir / "metadata.json"
        if not metadata_path.exists():
            return None

        with open(metadata_path, encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            date=data["date"],
            rendered_lang=data.get("rendered_lang", "zh"),  # Default for old cache
            enhanced_caption_enabled=data.get("enhanced_caption_enabled", False),  # Default for old cache
            selection_mode=data.get("selection_mode", "date"),  # Default for old cache
            current_index=data.get("current_index", 0),  # Default for old cache
            photos=data["photos"]
        )


def save_cache_to_disk(
    cache_dir: Path,
    target_date: date,
    rendered_lang: str,
    photos: list[CachedPhoto],
) -> None:
    """Save cache to disk: metadata.json + .bin + .png files.

    Args:
        cache_dir: Directory to save cache files
        target_date: Date of the cache
        rendered_lang: Language used for rendering
        photos: List of cached photos to persist
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Build metadata
    photo_entries: list[dict[str, Any]] = []
    for i, photo in enumerate(photos):
        binary_file = f"photo_{i}.bin"
        preview_file = f"photo_{i}.png"

        # Write binary file
        (cache_dir / binary_file).write_bytes(photo.binary)

        # Write preview PNG
        preview_data = render_preview(
            photo.candidate.path,
            photo.candidate,
            lang=rendered_lang,
            font_path_zh=settings.font_path_zh,
            font_path_en=settings.font_path_en,
        )
        (cache_dir / preview_file).write_bytes(preview_data)

        # Build metadata entry (store full JSON including enhanced_caption_json)
        photo_entries.append({
            "index": i,
            "path": photo.candidate.path,
            "memory_score": photo.candidate.memory_score,
            "beauty_score": photo.candidate.beauty_score,
            "exif_datetime": photo.candidate.exif_datetime,
            "location_json": photo.candidate.location_json,
            "caption_json": photo.candidate.caption_json,
            "enhanced_caption_json": photo.candidate.enhanced_caption_json,
            "binary_file": binary_file,
            "preview_file": preview_file,
        })

    # Save metadata
    metadata = CacheMetadata(
        date=target_date.isoformat(),
        rendered_lang=rendered_lang,
        enhanced_caption_enabled=settings.enhanced_caption_enabled,
        selection_mode=settings.selection_mode,
        current_index=0,  # New cache starts at index 0
        photos=photo_entries
    )
    metadata.save(cache_dir)


def load_cache_from_disk(cache_dir: Path) -> tuple[date | None, str, bool, list[CachedPhoto]]:
    """Load cache from disk if it exists and matches today.

    Args:
        cache_dir: Directory containing cache files

    Returns:
        Tuple of (date, rendered_lang, enhanced_caption_enabled, list of CachedPhoto).
        Returns (None, "", False, []) if no valid cache.
    """
    metadata = CacheMetadata.load(cache_dir)
    if not metadata:
        return None, "", False, []

    # Parse date
    try:
        cache_date = date.fromisoformat(metadata.date)
    except ValueError:
        return None, "", False, []

    # Reconstruct CachedPhoto objects
    photos: list[CachedPhoto] = []
    for entry in metadata.photos:
        # Reconstruct PhotoCandidate
        candidate = PhotoCandidate(
            path=entry["path"],
            memory_score=entry["memory_score"],
            beauty_score=entry["beauty_score"],
            exif_datetime=entry["exif_datetime"],
            location_json=entry.get("location_json", {}),
            caption_json=entry.get("caption_json", {}),
            enhanced_caption_json=entry.get("enhanced_caption_json", {}),
        )

        # Load binary
        binary_path = cache_dir / entry["binary_file"]
        if not binary_path.exists():
            continue  # Skip if binary missing
        binary = binary_path.read_bytes()

        photos.append(CachedPhoto(candidate=candidate, binary=binary))

    return cache_date, metadata.rendered_lang, metadata.enhanced_caption_enabled, photos


def clear_cache_dir(cache_dir: Path) -> None:
    """Delete all files in cache directory.

    Args:
        cache_dir: Directory to clear
    """
    if not cache_dir.exists():
        return

    for file in cache_dir.iterdir():
        if file.is_file():
            file.unlink()


class DailyPhotoCache:
    """Cache for daily photo selection with disk persistence."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or settings.cache_dir
        self._date: date | None = None
        self._rendered_lang: str = ""
        self._photos: list[CachedPhoto] = []
        self._current_index: int = 0

        # Try to load from disk on init
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load cache from disk if it exists and is valid."""
        cache_date, rendered_lang, enhanced_enabled, photos = load_cache_from_disk(self._cache_dir)

        if not cache_date or not photos:
            return

        # Load metadata for mode check
        metadata = CacheMetadata.load(self._cache_dir)
        cached_mode = metadata.selection_mode if metadata else "date"

        today = date.today()

        # Check if cache matches current settings
        # Note: Date check only applies to date mode (curated photos don't change daily)
        if cache_date != today and settings.selection_mode == "date":
            print(f"[InkTime] Clearing old cache from {cache_date}")
            clear_cache_dir(self._cache_dir)
        elif rendered_lang != settings.default_language:
            print(f"[InkTime] Language changed from {rendered_lang} to {settings.default_language}")
            clear_cache_dir(self._cache_dir)
        elif enhanced_enabled != settings.enhanced_caption_enabled:
            print(f"[InkTime] Enhanced caption setting changed")
            clear_cache_dir(self._cache_dir)
        elif cached_mode != settings.selection_mode:
            print(f"[InkTime] Selection mode changed from {cached_mode} to {settings.selection_mode}")
            clear_cache_dir(self._cache_dir)
        else:
            # Cache is valid
            self._date = cache_date
            self._rendered_lang = rendered_lang
            self._photos = photos
            self._current_index = metadata.current_index if metadata else 0
            print(f"[InkTime] Loaded {len(photos)} cached photos from disk for {cache_date} ({rendered_lang})")

    def get(self, index: int) -> CachedPhoto:
        """Get photo by index (0-indexed). Triggers refresh if new day or language change.

        Args:
            index: Photo index (0, 1, 2, ...)

        Returns:
            CachedPhoto with candidate info and rendered binary

        Raises:
            IndexError: If index out of range
            RuntimeError: If no photos could be rendered
        """
        today = date.today()

        # Refresh if: new day (date mode only), language change, or empty
        # Curated mode doesn't need date-based refresh (photos are fixed)
        needs_refresh = (
            (self._date != today and settings.selection_mode == "date")
            or self._rendered_lang != settings.default_language
            or not self._photos
        )
        if needs_refresh:
            self._refresh(today)

        if index < 0 or index >= len(self._photos):
            raise IndexError(f"Photo index {index} out of range (0-{len(self._photos)-1})")

        return self._photos[index]

    def get_all(self) -> list[CachedPhoto]:
        """Get all cached photos. Triggers refresh if needed."""
        today = date.today()
        needs_refresh = (
            (self._date != today and settings.selection_mode == "date")
            or self._rendered_lang != settings.default_language
            or not self._photos
        )
        if needs_refresh:
            self._refresh(today)
        return self._photos

    def get_next(self) -> CachedPhoto:
        """Get next photo in sequence, increment index, persist to disk.

        Returns:
            CachedPhoto at current index (before increment)

        Raises:
            RuntimeError: If no photos available
        """
        today = date.today()

        # Refresh if needed (same logic as get())
        needs_refresh = (
            (self._date != today and settings.selection_mode == "date")
            or self._rendered_lang != settings.default_language
            or not self._photos
        )
        if needs_refresh:
            self._refresh(today)

        if not self._photos:
            raise RuntimeError("No photos available")

        # Get photo at current index
        photo = self._photos[self._current_index]

        # Increment with wrap-around
        self._current_index = (self._current_index + 1) % len(self._photos)

        # Persist index to disk
        self._save_index()

        return photo

    def _save_index(self) -> None:
        """Save current index to metadata.json without re-saving photos."""
        metadata = CacheMetadata.load(self._cache_dir)
        if metadata:
            metadata.current_index = self._current_index
            metadata.save(self._cache_dir)

    @property
    def current_index(self) -> int:
        """Get current photo index."""
        return self._current_index

    def _refresh(self, target_date: date) -> None:
        """Refresh cache with new photo selection."""
        # Clear old cache
        if self._cache_dir.exists():
            clear_cache_dir(self._cache_dir)

        # Get current language
        current_lang = settings.default_language

        # Select photos (dispatches by mode: date or curated)
        candidates = select_photos_for_today()

        # Generate enhanced captions in parallel (if enabled)
        _generate_missing_enhanced_captions(candidates, current_lang)

        # Render all photos with layout (photo + text overlay)
        photos: list[CachedPhoto] = []
        for candidate in candidates:
            try:
                binary = render(
                    candidate.path,
                    candidate,
                    lang=current_lang,
                    font_path_zh=settings.font_path_zh,
                    font_path_en=settings.font_path_en,
                )
                photos.append(CachedPhoto(candidate=candidate, binary=binary))
            except Exception as e:
                # Skip photos that fail to render
                print(f"Warning: Failed to render {candidate.path}: {e}")
                continue

        if not photos:
            raise RuntimeError("No photos could be rendered")

        self._date = target_date
        self._rendered_lang = current_lang
        self._photos = photos
        self._current_index = 0  # Reset index on refresh

        # Persist to disk
        try:
            save_cache_to_disk(self._cache_dir, target_date, current_lang, photos)
            print(f"[InkTime] Saved {len(photos)} photos to cache for {target_date} ({current_lang})")
        except Exception as e:
            print(f"Warning: Failed to save cache to disk: {e}")

    @property
    def current_date(self) -> date | None:
        """Get the date of current cache."""
        return self._date

    @property
    def rendered_language(self) -> str:
        """Get the language used for rendering."""
        return self._rendered_lang

    @property
    def count(self) -> int:
        """Get number of cached photos."""
        return len(self._photos)


# Global cache instance
cache = DailyPhotoCache()
