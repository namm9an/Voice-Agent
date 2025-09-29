"""
Text-to-speech service (Parler TTS primary, XTTS fallback, beep fallback).
"""

import logging
import httpx
import io
import wave
import numpy as np

from app.config.settings import get_settings
from app.utils.error_handlers import TTSServiceError

logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self):
        self.settings = get_settings()

    async def synthesize_speech(self, text: str) -> bytes:
        if not text or not text.strip():
            logger.warning("Empty text for TTS, generating fallback beep")
            return self._generate_fallback_beep()

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

        # Final fallback: generate a simple beep
        logger.warning("All TTS providers failed, using fallback beep")
        return self._generate_fallback_beep()

    def _generate_fallback_beep(self) -> bytes:
        """Generate a simple beep sound as fallback"""
        sample_rate = 16000
        duration = 1.0  # 1 second
        frequency = 440  # A4 note
        
        # Generate sine wave
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio_data = np.sin(2 * np.pi * frequency * t) * 0.3  # 30% volume
        
        # Convert to 16-bit PCM
        audio_data = (audio_data * 32767).astype(np.int16)
        
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        return wav_buffer.getvalue()


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