"""Application configuration using pydantic-settings.

Loads from .env file and environment variables.
Environment variables take precedence over .env file.
"""

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    image_dir: Path = Field(default=Path("./test"))
    db_path: Path = Field(default=Path("./photos.db"))
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

    # Home location
    home_lat: float = 22.543096
    home_lon: float = 114.057865
    home_radius_km: float = 60.0

    @field_validator("batch_limit", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty strings to None for optional integer fields."""
        if v == "" or v is None:
            return None
        return v

    def resolve_paths(self) -> None:
        """Resolve relative paths to absolute paths based on project root."""
        root = Path(__file__).parent.parent

        if not self.image_dir.is_absolute():
            self.image_dir = (root / self.image_dir).resolve()
        if not self.db_path.is_absolute():
            self.db_path = (root / self.db_path).resolve()
        if not self.world_cities_csv.is_absolute():
            self.world_cities_csv = (root / self.world_cities_csv).resolve()


# Global settings instance
settings = Settings()
settings.resolve_paths()
