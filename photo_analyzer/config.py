"""Application configuration using pydantic-settings.

Loads from .env file and environment variables.
Environment variables take precedence over .env file.
"""

import logging
from pathlib import Path

from typing import Literal

from pydantic import Field, field_validator, model_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
        populate_by_name=True,
    )

    # Paths
    image_dirs_str: str = Field(
        default="./photo_analyzer/test",
        validation_alias=AliasChoices("IMAGE_DIRS", "image_dirs_str"),
    )

    # Selection mode
    selection_mode: Literal["date", "curated"] | None = None

    # Curated mode settings
    curated_dirs_str: str = Field(
        default="",
        validation_alias=AliasChoices("CURATED_DIRS", "curated_dirs_str"),
    )
    curated_db_path: Path = Field(default=Path("./photo_analyzer/curated.db"))

    db_path: Path = Field(default=Path("./photo_analyzer/photos.db"))
    world_cities_csv: Path = Field(default=Path("./photo_analyzer/world_cities_zh.csv"))

    # VLM API
    api_url: str = "http://127.0.0.1:1234/v1/chat/completions"
    model_name: str = "qwen3.5-4b"
    api_key: str = ""

    # Processing
    batch_limit: int | None = None
    timeout: int = 600
    vlm_max_long_edge: int = 2560

    # City resolution
    city_grid_deg: float = 1.0
    city_max_distance_km: float = 80.0

    # Local areas for travel detection (up to 5 areas)
    # Each area has LAT, LON, RADIUS
    local_0_lat: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_0_LAT", "local_0_lat"))
    local_0_lon: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_0_LON", "local_0_lon"))
    local_0_radius: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_0_RADIUS", "local_0_radius"))

    local_1_lat: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_1_LAT", "local_1_lat"))
    local_1_lon: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_1_LON", "local_1_lon"))
    local_1_radius: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_1_RADIUS", "local_1_radius"))

    local_2_lat: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_2_LAT", "local_2_lat"))
    local_2_lon: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_2_LON", "local_2_lon"))
    local_2_radius: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_2_RADIUS", "local_2_radius"))

    local_3_lat: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_3_LAT", "local_3_lat"))
    local_3_lon: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_3_LON", "local_3_lon"))
    local_3_radius: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_3_RADIUS", "local_3_radius"))

    local_4_lat: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_4_LAT", "local_4_lat"))
    local_4_lon: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_4_LON", "local_4_lon"))
    local_4_radius: float | None = Field(default=None, validation_alias=AliasChoices("LOCAL_4_RADIUS", "local_4_radius"))

    # Language settings
    display_languages_str: str = Field(
        default="zh",
        validation_alias=AliasChoices("DISPLAY_LANGUAGES", "display_languages_str"),
    )

    @field_validator("batch_limit", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty strings to None for optional integer fields."""
        if v == "" or v is None:
            return None
        return v

    @model_validator(mode="after")
    def validate_selection_mode(self) -> "Settings":
        """Validate selection_mode and required settings."""
        if self.selection_mode is None:
            raise ValueError(
                "SELECTION_MODE is required. Set to 'date' or 'curated' in .env"
            )

        if self.selection_mode == "date" and not self.image_dirs_str:
            raise ValueError(
                "IMAGE_DIRS is required when SELECTION_MODE=date"
            )

        if self.selection_mode == "curated" and not self.curated_dirs_str:
            raise ValueError(
                "CURATED_DIRS is required when SELECTION_MODE=curated"
            )

        return self

    @property
    def image_dirs(self) -> list[Path]:
        """Parse comma-separated directories string into list of Paths."""
        if not self.image_dirs_str:
            return [Path("./photo_analyzer/test")]
        paths = [p.strip() for p in self.image_dirs_str.split(",") if p.strip()]
        return [Path(p) for p in paths] if paths else [Path("./photo_analyzer/test")]

    @property
    def curated_dirs(self) -> list[Path]:
        """Parse comma-separated curated directories string into list of Paths."""
        if not self.curated_dirs_str:
            return []
        paths = [p.strip() for p in self.curated_dirs_str.split(",") if p.strip()]
        return [Path(p) for p in paths]

    def resolve_paths(self) -> None:
        """Resolve relative paths to absolute paths based on project root."""
        root = Path(__file__).parent.parent

        # Resolve image_dirs via the property
        resolved_dirs = []
        for p in self.image_dirs:
            if not p.is_absolute():
                resolved_dirs.append((root / p).resolve())
            else:
                resolved_dirs.append(p)
        self._resolved_image_dirs = resolved_dirs

        # Resolve curated dirs
        resolved_curated = []
        for p in self.curated_dirs:
            if not p.is_absolute():
                resolved_curated.append((root / p).resolve())
            else:
                resolved_curated.append(p)
        self._resolved_curated_dirs = resolved_curated

        if not self.db_path.is_absolute():
            self.db_path = (root / self.db_path).resolve()
        if not self.curated_db_path.is_absolute():
            self.curated_db_path = (root / self.curated_db_path).resolve()
        if not self.world_cities_csv.is_absolute():
            self.world_cities_csv = (root / self.world_cities_csv).resolve()

    @property
    def resolved_image_dirs(self) -> list[Path]:
        """Get resolved (absolute) image directories."""
        return getattr(self, "_resolved_image_dirs", self.image_dirs)

    @property
    def resolved_curated_dirs(self) -> list[Path]:
        """Get resolved (absolute) curated directories."""
        return getattr(self, "_resolved_curated_dirs", self.curated_dirs)

    @property
    def display_languages(self) -> list[str]:
        """Parse comma-separated languages string into list."""
        if not self.display_languages_str:
            return ["zh"]
        langs = [lang.strip() for lang in self.display_languages_str.split(",") if lang.strip()]
        return langs if langs else ["zh"]

    @property
    def default_language(self) -> str:
        """First language in list is the default display language."""
        return self.display_languages[0] if self.display_languages else "zh"

    @property
    def local_areas(self) -> list[tuple[float, float, float]]:
        """Build list of (lat, lon, radius) tuples from configured LOCAL_N_* fields.

        Returns empty list if no LOCAL_* configured (no travel bonus will be applied).
        """
        areas: list[tuple[float, float, float]] = []

        # Check each configured area
        area_fields = [
            (self.local_0_lat, self.local_0_lon, self.local_0_radius),
            (self.local_1_lat, self.local_1_lon, self.local_1_radius),
            (self.local_2_lat, self.local_2_lon, self.local_2_radius),
            (self.local_3_lat, self.local_3_lon, self.local_3_radius),
            (self.local_4_lat, self.local_4_lon, self.local_4_radius),
        ]

        for lat, lon, radius in area_fields:
            if lat is not None and lon is not None and radius is not None:
                areas.append((lat, lon, radius))

        return areas


# Global settings instance
settings = Settings()
settings.resolve_paths()
