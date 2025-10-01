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
    # LLM (OpenAI-compatible chat endpoint) - Phi-3.5-mini-instruct
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: str = "microsoft/Phi-3.5-mini-instruct"
    # Legacy qwen settings (deprecated, use llm_* instead)
    qwen_base_url: Optional[str] = None
    qwen_api_key: Optional[str] = None
    qwen_model: Optional[str] = None

    # TTS
    # Parler primary, XTTS fallback
    parler_tts_base_url: Optional[str] = None
    xtts_tts_base_url: Optional[str] = None
    tts_voice: str = "female"  # Default to female voice
    tts_language: str = "en"
    tts_model: str = "parler-tts/parler-tts-mini-v1"
    
    # Available voices for Parler TTS (using speaker names in descriptions)
    available_voices: dict = {
        "male": "Jon's voice is monotone yet slightly fast in delivery, with a very close recording that almost has no background noise.",
        "female": "Lea's voice is warm and clear, delivering her words in a friendly manner with good audio quality.",
        "male_casual": "Gary's voice is casual and relaxed, speaking naturally with a conversational tone.",
        "female_casual": "Jenny's voice is casual and friendly, speaking naturally with a warm conversational tone."
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