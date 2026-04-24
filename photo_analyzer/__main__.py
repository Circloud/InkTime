"""Command-line interface for photo analysis."""

import logging
import time
from pathlib import Path

from .city import create_city_resolver, haversine_km
from .config import settings
from .database import (
    count_records,
    delete_orphaned_records,
    get_analyzed_paths,
    init_database,
    save_photo,
)
from .models import PhotoRecord
from .vlm import analyze_photo, generate_caption

logger = logging.getLogger(__name__)

# Image extensions to scan
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s",
    )


def format_eta(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    if seconds <= 0:
        return "00:00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def is_screenshot(path: Path) -> bool:
    """Check if path appears to be a screenshot."""
    return "screenshot" in str(path).lower()


def list_images(image_dir: Path, limit: int | None = None) -> list[Path]:
    """Recursively scan directory for image files."""
    files: list[Path] = []
    logger.info(f"Scanning image directory: {image_dir}")

    scanned = 0
    for p in image_dir.rglob("*"):
        scanned += 1
        if scanned % 500 == 0:
            logger.info(f"Scanned {scanned} files...")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            if not is_screenshot(p):
                files.append(p)

    logger.info(f"Found {len(files)} images (scanned {scanned} files)")
    if limit is not None:
        files = files[:limit]
    return files


def in_home_area(lat: float | None, lon: float | None) -> bool:
    """Check if coordinates are within the home/local area."""
    if lat is None or lon is None:
        return False

    try:
        d = haversine_km(lat, lon, settings.home_lat, settings.home_lon)
        return d <= settings.home_radius_km
    except Exception:
        return False


def print_progress(
    idx: int,
    total: int,
    processed: int,
    elapsed: float,
    photo_time: float,
) -> None:
    """Print progress bar and ETA."""
    progress = min(processed / total, 1.0) if total > 0 else 0.0

    bar_width = 30
    filled = int(bar_width * progress)
    bar = "█" * filled + "░" * (bar_width - filled)

    avg_time = elapsed / idx if idx > 0 else 0
    remaining = max(total - processed, 0)
    eta = format_eta(remaining * avg_time) if avg_time > 0 else "00:00:00"

    print(
        f"[Progress] {bar} {progress*100:5.1f}%  {processed}/{total}  "
        f"This photo: {photo_time:4.1f}s  ETA: {eta}"
    )


def main() -> None:
    """Main entry point for photo analysis."""
    setup_logging()

    # Scan for images
    logger.info("Scanning image directory...")
    images = list_images(settings.image_dir)

    # Save file list
    filelist_path = Path(__file__).parent.parent / "filelist.txt"
    filelist_path.write_text("\n".join(str(p) for p in images), encoding="utf-8")
    logger.info(f"Updated filelist.txt with {len(images)} files")

    if not images:
        raise SystemExit(f"No image files found in: {settings.image_dir}")

    # Initialize database
    conn = init_database(settings.db_path)
    city_resolver = create_city_resolver(
        settings.world_cities_csv,
        grid_deg=settings.city_grid_deg,
        max_km=settings.city_max_distance_km,
    )

    # Sync delete: remove records for files no longer on disk
    image_dir_prefix = str(settings.image_dir)
    deleted = delete_orphaned_records(conn, [str(p) for p in images], image_dir_prefix)
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} orphaned database records")

    # Count existing records
    existing_count = count_records(conn, image_dir_prefix)
    logger.info(f"Database has {existing_count} analyzed photos")

    # Filter out already-analyzed photos
    analyzed = get_analyzed_paths(conn, [str(p) for p in images])
    target_paths = [p for p in images if str(p) not in analyzed]

    if not target_paths:
        logger.info("All images already analyzed")
        conn.close()
        return

    if settings.batch_limit is not None:
        target_paths = target_paths[: settings.batch_limit]

    total = existing_count + len(target_paths)
    logger.info(f"Ready to process {len(target_paths)} images (total: {total})")

    start_time = time.time()

    for idx, path in enumerate(target_paths, start=1):
        photo_start = time.perf_counter()

        print("\n" + "=" * 60)
        print(f"[{idx}/{len(target_paths)}] Processing: {path}")

        try:
            vlm_response, exif_info = analyze_photo(path)
        except Exception as e:
            logger.warning(f"Failed to analyze photo: {e}")
            continue

        # Generate caption
        caption = generate_caption(path)

        # Resolve city from GPS
        if exif_info.gps_lat is not None and exif_info.gps_lon is not None:
            location_city = city_resolver.resolve(exif_info.gps_lat, exif_info.gps_lon)
        else:
            location_city = ""

        # Check if travel photo (outside home area)
        travel_bonus = not in_home_area(exif_info.gps_lat, exif_info.gps_lon)

        # Create record
        record = PhotoRecord.from_analysis(
            path=str(path),
            vlm_response=vlm_response,
            exif_info=exif_info,
            caption=caption,
            location_city=location_city,
            travel_bonus_applied=travel_bonus,
        )

        # Print results
        print(f"  Type: {record.photo_type}")
        print(f"  Memory Score: {record.memory_score:.1f}")
        print(f"  Beauty Score: {record.beauty_score:.1f}")
        print(f"  Caption: {record.caption or '(none)'}")
        print(f"  Description: {record.description}")
        print(f"  Reason: {record.reason}")

        # Save to database
        save_photo(conn, record)

        # Progress
        photo_time = time.perf_counter() - photo_start
        processed = existing_count + idx
        elapsed = time.time() - start_time
        print_progress(idx, total, processed, elapsed, photo_time)

    conn.close()
    logger.info("Batch processing complete")


if __name__ == "__main__":
    main()
