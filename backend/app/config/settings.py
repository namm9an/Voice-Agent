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

    # LiveKit Configuration
    livekit_api_key: str = "APIqKZYLpFzhbP4"
    livekit_api_secret: str = "C6ueGcv1Uff6cRdveALMeo2Zaevn134mfIdMRi2TlefNB"
    livekit_url: str = "ws://101.53.140.228:7880"

    # Server
    cors_origins: List[str] = ["http://localhost:3000"]
    log_level: str = "INFO"
    app_env: str = "development"
    app_port: int = 8000

    # Audio constraints
    max_audio_size_mb: int = 10
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_max_duration_seconds: int = 120
    audio_min_duration_seconds: float = 0.5
    audio_normalize: bool = True
    whisper_language: str = "en"
    tts_voice_model: str = "tts_models/en/ljspeech/tacotron2-DDC"
    enable_cache: bool = False
    log_file_path: str = "logs/app.log"

    # ASR (Phase 2)
    asr_buffer_window_ms: int = 500
    asr_buffer_slide_ms: int = 250
    whisper_model: str = "openai/whisper-large-v3-turbo"

    # LLM (Phase 3)
    llm_streaming: bool = True
    llm_max_tokens: int = 256
    llm_temperature: float = 0.8

    # TTS (Phase 4)
    tts_chunk_size_sentences: int = 2
    tts_sample_rate: int = 16000
    tts_format: str = "wav"

    # Pipeline & Session (Phase 5)
    session_expiry_minutes: int = 10
    max_concurrent_sessions: int = 5
    memory_context_tokens: int = 512

    # Diagnostics
    enable_stream_logging: bool = True
    log_frames_every: int = 50
    test_tone_enabled: bool = False

    # LiveKit defaults
    livekit_default_room: str = "voice-room"
    livekit_agent_name: str = "voice_agent"

    # Phase 7: Monitoring & Optimization
    enable_metrics: bool = True
    metrics_save_path: str = "./logs/metrics.jsonl"
    health_check_interval: int = 30
    service_timeout: int = 3
    monitor_port: int = 8500

    # Backup nodes (optional)
    a100_node_backup: Optional[str] = None
    l40_node_backup: Optional[str] = None

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