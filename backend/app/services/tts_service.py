"""
Text-to-speech service (Parler TTS primary, XTTS fallback).
"""

import logging
import httpx

from app.config.settings import get_settings
from app.utils.error_handlers import TTSServiceError

logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self):
        self.settings = get_settings()

    async def synthesize_speech(self, text: str) -> bytes:
        if not text or not text.strip():
            raise TTSServiceError("Empty text for TTS")

        # Try Parler first
        if self.settings.parler_tts_base_url:
            try:
                audio = await _call_parler(self.settings.parler_tts_base_url, text, self.settings)
                if audio:
                    return audio
            except Exception as e:
                logger.warning(f"Parler TTS failed, will try fallback: {e}")

        # Fallback XTTS
        if self.settings.xtts_tts_base_url:
            try:
                audio = await _call_xtts(self.settings.xtts_tts_base_url, text, self.settings)
                if audio:
                    return audio
            except Exception as e:
                logger.error(f"XTTS fallback failed: {e}")

        raise TTSServiceError("All TTS providers failed")


async def _call_parler(base_url: str, text: str, settings) -> bytes:
    url = base_url.rstrip('/') + '/tts'
    payload = {
        "text": text,
        "description": "A female speaker with a slightly low-pitched voice delivers her words quite expressively, in a very confined sounding environment with clear audio quality."
    }
    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.content


async def _call_xtts(base_url: str, text: str, settings) -> bytes:
    url = base_url.rstrip('/') + '/synthesize'
    payload = {
        "text": text,
        "voice": settings.tts_voice or "default",
        "language": settings.tts_language or "en",
        "format": "wav",
    }
    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.content