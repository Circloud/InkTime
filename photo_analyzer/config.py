"""Application configuration using pydantic-settings.

Loads from .env file and environment variables.
Environment variables take precedence over .env file.
"""

from pathlib import Path
from pydantic import Field, field_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Home location
    home_lat: float = 22.543096
    home_lon: float = 114.057865
    home_radius_km: float = 60.0

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

    @property
    def image_dirs(self) -> list[Path]:
        """Parse comma-separated directories string into list of Paths."""
        if not self.image_dirs_str:
            return [Path("./photo_analyzer/test")]
        paths = [p.strip() for p in self.image_dirs_str.split(",") if p.strip()]
        return [Path(p) for p in paths] if paths else [Path("./photo_analyzer/test")]

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

        if not self.db_path.is_absolute():
            self.db_path = (root / self.db_path).resolve()
        if not self.world_cities_csv.is_absolute():
            self.world_cities_csv = (root / self.world_cities_csv).resolve()

    @property
    def resolved_image_dirs(self) -> list[Path]:
        """Get resolved (absolute) image directories."""
        return getattr(self, "_resolved_image_dirs", self.image_dirs)

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


# Global settings instance
settings = Settings()
settings.resolve_paths()
