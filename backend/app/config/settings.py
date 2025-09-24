"""
Application settings and environment variables
"""
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Phase 1: Provide fields with sensible defaults; integrations come in Phase 2.
    """

    # External services
    openai_api_key: Optional[str] = None
    qwen_endpoint: Optional[str] = None
    qwen_api_key: Optional[str] = None

    # TTS
    tts_model: str = "coqui"

    # Server
    cors_origins: List[str] = ["http://localhost:3000"]
    log_level: str = "INFO"

    # Audio constraints
    max_audio_size_mb: int = 10
    audio_sample_rate: int = 16000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()