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

from pydantic import Field, AliasChoices
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

    def resolve_paths(self) -> None:
        """Resolve relative paths to absolute paths based on project root."""
        root = Path(__file__).parent.parent

        if not self.db_path.is_absolute():
            self.db_path = (root / self.db_path).resolve()
        if self.font_path_zh and not self.font_path_zh.is_absolute():
            self.font_path_zh = (root / self.font_path_zh).resolve()
        if self.font_path_en and not self.font_path_en.is_absolute():
            self.font_path_en = (root / self.font_path_en).resolve()
        if not self.cache_dir.is_absolute():
            self.cache_dir = (root / self.cache_dir).resolve()


# Global settings instance
settings = ServerSettings()
settings.resolve_paths()
