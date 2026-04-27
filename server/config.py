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

from pydantic import Field
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

    # Font for text overlay (caption, date, location)
    font_path: Path | None = None  # Path to TTF font file, e.g., "./fonts/LXGWHeartSerifMN.ttf"

    # Cache directory for persisted daily photos
    cache_dir: Path = Field(default=Path("./server/cache"))

    def resolve_paths(self) -> None:
        """Resolve relative paths to absolute paths based on project root."""
        root = Path(__file__).parent.parent

        if not self.db_path.is_absolute():
            self.db_path = (root / self.db_path).resolve()
        if self.font_path and not self.font_path.is_absolute():
            self.font_path = (root / self.font_path).resolve()
        if not self.cache_dir.is_absolute():
            self.cache_dir = (root / self.cache_dir).resolve()


# Global settings instance
settings = ServerSettings()
settings.resolve_paths()
