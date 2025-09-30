"""
Application settings and environment variables
"""
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Phase 1: Provide fields with sensible defaults; integrations come in Phase 2.
    """

    # External services
    openai_api_key: Optional[str] = None
    # Whisper-compatible overrides (optional)
    whisper_api_key: Optional[str] = None
    whisper_base_url: Optional[str] = None
    whisper_model: str = "openai/whisper-large-v3-turbo"
    # Qwen (OpenAI-compatible chat endpoint)
    qwen_base_url: Optional[str] = None
    qwen_api_key: Optional[str] = None
    qwen_model: str = "Qwen/Qwen2.5-14B-Instruct"

    # TTS
    # Parler primary, XTTS fallback
    parler_tts_base_url: Optional[str] = None
    xtts_tts_base_url: Optional[str] = None
    tts_voice: str = "female"  # Default to female voice
    tts_language: str = "en"
    tts_model: str = "parler-tts/parler-tts-mini-v1"
    
    # Available voices for Parler TTS (using actual voice model names)
    available_voices: dict = {
        "male": "Jon",           # High consistency male voice
        "female": "Lea",         # High consistency female voice  
        "male_casual": "Gary",   # Casual male voice
        "female_casual": "Jenny" # Casual female voice
    }

    # Server
    cors_origins: List[str] = ["http://localhost:3000"]
    log_level: str = "INFO"

    # Audio constraints
    max_audio_size_mb: int = 10
    audio_sample_rate: int = 16000
    audio_max_duration_seconds: int = 120
    audio_min_duration_seconds: float = 0.5
    audio_normalize: bool = True
    whisper_language: str = "auto"
    tts_voice_model: str = "tts_models/en/ljspeech/tacotron2-DDC"
    enable_cache: bool = False
    log_file_path: str = "logs/app.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # Support comma-separated origins from .env
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()