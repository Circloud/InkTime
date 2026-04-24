"""City resolution from GPS coordinates using local database."""

import csv
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

# Type alias for city record: (lat, lon, name_zh, name_en)
CityRecord = tuple[float, float, str, str]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers."""
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def grid_key(lat: float, lon: float, grid_deg: float) -> tuple[int, int]:
    """Convert coordinates to grid cell index."""
    gx = int(math.floor(lat / grid_deg))
    gy = int(math.floor(lon / grid_deg))
    return gx, gy


class CityResolver:
    """Resolve GPS coordinates to city names using local database."""

    def __init__(self, csv_path: Path, grid_deg: float = 1.0, max_km: float = 80.0):
        """Initialize city resolver with database path and parameters."""
        self.grid_deg = grid_deg
        self.max_km = max_km
        self.cities: list[CityRecord] = []
        self.grid_index: dict[tuple[int, int], list[int]] = {}

        self._load_cities(csv_path)

    def _load_cities(self, csv_path: Path) -> None:
        """Load city database from CSV file."""
        if not csv_path.exists():
            raise FileNotFoundError(f"City database not found: {csv_path}")

        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    lat = float((row.get("lat") or "").strip())
                    lon = float((row.get("lon") or "").strip())
                except Exception:
                    continue
                name_en = (row.get("name_en") or "").strip()
                name_zh = (row.get("name_zh") or "").strip()
                self.cities.append((lat, lon, name_zh, name_en))

        # Build grid index
        for idx, (lat, lon, _, _) in enumerate(self.cities):
            key = grid_key(lat, lon, self.grid_deg)
            self.grid_index.setdefault(key, []).append(idx)

        logger.info(f"Loaded {len(self.cities)} cities from {csv_path}")

    def resolve(self, lat: float | None, lon: float | None) -> str:
        """Find the nearest city for given coordinates."""
        if lat is None or lon is None:
            return ""

        gx, gy = grid_key(lat, lon, self.grid_deg)

        # Collect candidates from nearby grid cells
        candidates: list[int] = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                bucket = self.grid_index.get((gx + dx, gy + dy))
                if bucket:
                    candidates.extend(bucket)

        if not candidates:
            # Try wider search
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    bucket = self.grid_index.get((gx + dx, gy + dy))
                    if bucket:
                        candidates.extend(bucket)

        if not candidates:
            return ""

        # Find nearest city
        best_idx: int | None = None
        best_dist = float("inf")

        for idx in candidates:
            city_lat, city_lon, _, _ = self.cities[idx]
            d = haversine_km(lat, lon, city_lat, city_lon)
            if d < best_dist:
                best_dist = d
                best_idx = idx

        if best_idx is None or best_dist > self.max_km:
            return ""

        _, _, name_zh, name_en = self.cities[best_idx]
        return name_zh or name_en or ""


def create_city_resolver(
    csv_path: Path,
    grid_deg: float = 1.0,
    max_km: float = 80.0,
) -> CityResolver:
    """Factory function to create a CityResolver instance."""
    return CityResolver(csv_path, grid_deg, max_km)
