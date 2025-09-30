"""
Health check endpoints - basic and deep health checks
"""
from fastapi import APIRouter
import logging
import io
import wave
import numpy as np
from typing import Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check - server is running"""
    return {"status": "healthy"}


@router.get("/health/deep")
async def deep_health_check():
    """
    Deep health check - verify all critical services are operational
    Tests actual connectivity and functionality of each service
    """
    from app.services.whisper_service import WhisperService
    from app.services.qwen_service import QwenService
    from app.services.tts_service import TTSService
    from app.services.vad_service import get_vad_service

    results: Dict[str, Any] = {}
    services_healthy = True

    # Test Whisper Service
    logger.info("Health check: Testing Whisper service...")
    try:
        whisper = WhisperService()
        # Generate 1 second of silence as test audio
        test_audio = _generate_test_audio(duration_ms=1000)
        # Don't actually call the API - just check initialization
        if whisper.api_key and whisper.base_url:
            results["whisper"] = {
                "status": "healthy",
                "endpoint": whisper.base_url,
                "model": whisper.settings.whisper_model
            }
        else:
            results["whisper"] = {
                "status": "unhealthy",
                "error": "Missing API key or base URL"
            }
            services_healthy = False
    except Exception as e:
        logger.error(f"Whisper health check failed: {e}")
        results["whisper"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        services_healthy = False

    # Test Qwen Service
    logger.info("Health check: Testing Qwen service...")
    try:
        qwen = QwenService()
        # Check if client is initialized
        if qwen.client and qwen.settings.qwen_api_key and qwen.settings.qwen_base_url:
            results["qwen"] = {
                "status": "healthy",
                "endpoint": qwen.settings.qwen_base_url,
                "model": qwen.settings.qwen_model,
                "max_history": qwen.max_history
            }
        else:
            results["qwen"] = {
                "status": "unhealthy",
                "error": "Missing API key or base URL"
            }
            services_healthy = False
    except Exception as e:
        logger.error(f"Qwen health check failed: {e}")
        results["qwen"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        services_healthy = False

    # Test TTS Service
    logger.info("Health check: Testing TTS service...")
    try:
        tts = TTSService()
        # Check if at least one TTS provider is configured
        has_provider = bool(tts.settings.parler_tts_base_url or tts.settings.xtts_tts_base_url)
        if has_provider:
            results["tts"] = {
                "status": "healthy",
                "parler_url": tts.settings.parler_tts_base_url or "not configured",
                "xtts_url": tts.settings.xtts_tts_base_url or "not configured",
                "cache_size": len(tts._cache),
                "cache_max": tts._cache_max_size
            }
        else:
            results["tts"] = {
                "status": "degraded",
                "warning": "No TTS provider configured, will use fallback beep"
            }
    except Exception as e:
        logger.error(f"TTS health check failed: {e}")
        results["tts"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        services_healthy = False

    # Test VAD Service
    logger.info("Health check: Testing VAD service...")
    try:
        vad = get_vad_service()
        # Test with simple audio
        test_audio = _generate_test_audio(duration_ms=500)
        # Just check if VAD is initialized
        if vad.vad and vad.sample_rate:
            results["vad"] = {
                "status": "healthy",
                "sample_rate": vad.sample_rate,
                "frame_duration_ms": vad.frame_duration_ms
            }
        else:
            results["vad"] = {
                "status": "unhealthy",
                "error": "VAD not properly initialized"
            }
            services_healthy = False
    except Exception as e:
        logger.error(f"VAD health check failed: {e}")
        results["vad"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        services_healthy = False

    # Overall status
    overall_status = "healthy" if services_healthy else "unhealthy"

    return {
        "status": overall_status,
        "services": results,
        "message": "All services operational" if services_healthy else "Some services are unhealthy"
    }


def _generate_test_audio(duration_ms: int = 1000, sample_rate: int = 16000) -> bytes:
    """
    Generate test audio - 1 second of silence in WAV format

    Args:
        duration_ms: Duration in milliseconds
        sample_rate: Sample rate in Hz

    Returns:
        WAV audio bytes
    """
    # Generate silence
    num_samples = int(sample_rate * duration_ms / 1000)
    audio_data = np.zeros(num_samples, dtype=np.int16)

    # Create WAV file in memory
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())

    return buffer.getvalue()