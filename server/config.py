"""Server-specific configuration using pydantic-settings.

This package is designed to be deployed independently from photo_analyzer.
Both packages read from the same .env file, but each only defines what it needs.

Shared settings (both packages need):
    db_path - path to database

Server-specific settings:
    memory_threshold, daily_photo_quantity - photo selection criteria
    flask_host, flask_port, debug - server binding
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Server settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore settings for other packages
    )

    # Paths (shared with photo_analyzer - both packages access same DB)
    db_path: Path = Field(default=Path("./photo_analyzer/photos.db"))

    # Selection mode
    selection_mode: Literal["date", "curated"] | None = None

    # Curated mode settings
    curated_dirs_str: str = Field(
        default="",
        validation_alias=AliasChoices("CURATED_DIRS", "curated_dirs_str"),
    )
    curated_db_path: Path = Field(default=Path("./photo_analyzer/curated.db"))

    # Photo selection criteria (server-only - selects N photos per day for display)
    memory_threshold: float = Field(default=70.0, ge=0, le=100)
    daily_photo_quantity: int = Field(default=3, ge=1)

    # Server-specific settings
    flask_host: str = "0.0.0.0"
    flask_port: int = 8765
    debug: bool = False

    # Language settings
    display_languages_str: str = Field(
        default="zh",
        validation_alias=AliasChoices("DISPLAY_LANGUAGES", "display_languages_str"),
    )

    # Language-specific fonts (required for each configured language)
    font_path_zh: Path | None = None
    font_path_en: Path | None = None

    # Cache directory for persisted daily photos
    cache_dir: Path = Field(default=Path("./server/cache"))

    # Enhanced caption settings (online API for better quality)
    enhanced_caption_enabled: bool = False
    enhanced_base_url: str | None = None
    enhanced_api_key: str | None = None
    enhanced_model_name: str = "gpt-4o-mini"
    enhanced_timeout: int = 60
    enhanced_retry_times: int = 3
    enhanced_concurrent_limit: int = 3

    # Dithering settings
    photo_dither_mode: str = "burkes"
    photo_tone: float | str = 0.0
    text_dither_mode: str = "atkinson"

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
    def curated_dirs(self) -> list[Path]:
        """Parse comma-separated curated directories string into list of Paths."""
        if not self.curated_dirs_str:
            return []
        paths = [p.strip() for p in self.curated_dirs_str.split(",") if p.strip()]
        return [Path(p) for p in paths]

    def get_font_path(self, lang: str) -> Path:
        """Get font path for a specific language.

        Raises:
            ValueError: If font for the language is not configured
        """
        font_map = {
            "zh": self.font_path_zh,
            "en": self.font_path_en,
        }

        font_path = font_map.get(lang)
        if not font_path:
            raise ValueError(f"Font not configured for language: {lang}")

        return font_path

    @model_validator(mode="after")
    def validate_selection_mode(self) -> "ServerSettings":
        """Validate selection_mode is set."""
        if self.selection_mode is None:
            raise ValueError(
                "SELECTION_MODE is required. Set to 'date' or 'curated' in .env"
            )
        return self

    def resolve_paths(self) -> None:
        """Resolve relative paths to absolute paths based on project root."""
        root = Path(__file__).parent.parent

        if not self.db_path.is_absolute():
            self.db_path = (root / self.db_path).resolve()
        if not self.curated_db_path.is_absolute():
            self.curated_db_path = (root / self.curated_db_path).resolve()
        if self.font_path_zh and not self.font_path_zh.is_absolute():
            self.font_path_zh = (root / self.font_path_zh).resolve()
        if self.font_path_en and not self.font_path_en.is_absolute():
            self.font_path_en = (root / self.font_path_en).resolve()
        if not self.cache_dir.is_absolute():
            self.cache_dir = (root / self.cache_dir).resolve()


# Global settings instance
settings = ServerSettings()
settings.resolve_paths()
