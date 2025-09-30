"""
Text-to-speech service (Parler TTS primary, XTTS fallback, beep fallback).
"""

import logging
import httpx
import io
import wave
import numpy as np
import hashlib
import asyncio
from typing import Optional, Dict

from app.config.settings import get_settings
from app.utils.error_handlers import TTSServiceError

logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, bytes] = {}  # Simple in-memory cache
        self._cache_max_size = 100  # Maximum cached responses

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client"""
        if self._client is None or self._client.is_closed:
            # Optimized timeout for voice model-based TTS
            timeout = httpx.Timeout(20.0, connect=5.0, read=15.0)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.close()

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text and voice settings"""
        voice_key = self.settings.tts_voice or "female"
        cache_input = f"{text}:{voice_key}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    async def synthesize_speech(self, text: str) -> bytes:
        if not text or not text.strip():
            logger.warning("Empty text for TTS, generating fallback beep")
            return self._generate_fallback_beep()

        # Check text length - very long texts are more likely to timeout
        if len(text) > 500:
            logger.warning(f"Long text detected ({len(text)} chars), TTS may take longer or timeout")

        # Check cache first
        cache_key = self._get_cache_key(text)
        if cache_key in self._cache:
            logger.info(f"TTS cache hit for text: {text[:50]}...")
            return self._cache[cache_key]

        # Try Parler first with retry logic
        if self.settings.parler_tts_base_url:
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Attempting Parler TTS (attempt {attempt + 1}/{max_retries + 1}) with URL: {self.settings.parler_tts_base_url}")
                    audio = await _call_parler(
                        self.settings.parler_tts_base_url,
                        text,
                        self.settings,
                        await self._get_client()
                    )
                    if audio:
                        logger.info(f"Parler TTS successful, generated {len(audio)} bytes")
                        self._add_to_cache(cache_key, audio)
                        return audio
                    else:
                        logger.warning("Parler TTS returned empty audio")
                        break  # Don't retry if we got empty audio
                except httpx.TimeoutException as e:
                    logger.warning(f"Parler TTS timeout on attempt {attempt + 1}: {e}")
                    if attempt < max_retries:
                        logger.info(f"Retrying Parler TTS in 2 seconds...")
                        await asyncio.sleep(2)
                        continue
                    else:
                        logger.error(f"Parler TTS failed after {max_retries + 1} attempts due to timeout")
                except Exception as e:
                    logger.error(f"Parler TTS failed with error: {e}", exc_info=True)
                    break  # Don't retry on non-timeout errors

        # Fallback XTTS
        if self.settings.xtts_tts_base_url:
            try:
                audio = await _call_xtts(
                    self.settings.xtts_tts_base_url,
                    text,
                    self.settings,
                    await self._get_client()
                )
                if audio:
                    self._add_to_cache(cache_key, audio)
                    return audio
            except Exception as e:
                logger.error(f"XTTS fallback failed: {e}")

        # Final fallback: generate a simple beep
        logger.warning("All TTS providers failed, using fallback beep")
        return self._generate_fallback_beep()

    def _add_to_cache(self, key: str, audio: bytes):
        """Add audio to cache with size limit"""
        if len(self._cache) >= self._cache_max_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = audio

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

    async def _try_fast_tts_fallback(self, text: str) -> bytes:
        """Try a fast TTS fallback service"""
        try:
            # Try using a simple HTTP TTS service as fallback
            # This is a placeholder - you could integrate with other TTS services
            logger.info("Attempting fast TTS fallback...")
            
            # For now, return None to use beep fallback
            # In the future, you could integrate with:
            # - Google TTS API
            # - Azure Speech Services  
            # - AWS Polly
            # - Local TTS engines
            
            return None
            
        except Exception as e:
            logger.warning(f"Fast TTS fallback failed: {e}")
            return None


async def _call_parler(base_url: str, text: str, settings, client: httpx.AsyncClient) -> bytes:
    url = base_url.rstrip('/') + '/tts'
    logger.info(f"Parler TTS URL: {url}")

    # Get voice model name from settings
    voice_key = settings.tts_voice or "female"
    voice_model = settings.available_voices.get(voice_key, settings.available_voices["female"])
    logger.info(f"Using voice model: {voice_key} -> {voice_model}")

    # Use proper Parler TTS API format with voice model
    payload = {
        "text": text,
        "voice": voice_model,
        "model": settings.tts_model
    }
    
    try:
        logger.info(f"Sending request to Parler TTS with text: {text[:50]}...")
        resp = await client.post(url, json=payload)
        logger.info(f"Parler TTS response status: {resp.status_code}")
        
        if resp.status_code != 200:
            error_text = await resp.aread()
            logger.error(f"Parler TTS error response: {error_text.decode('utf-8', errors='ignore')}")
            raise httpx.HTTPStatusError(f"Parler TTS returned {resp.status_code}", request=resp.request, response=resp)
        
        content = resp.content
        logger.info(f"Parler TTS returned {len(content)} bytes")
        return content
        
    except httpx.ConnectError as e:
        logger.error(f"Parler TTS connection error: {e}")
        raise
    except httpx.TimeoutException as e:
        logger.error(f"Parler TTS timeout: {e}")
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"Parler TTS HTTP error: {e}")
        raise
    except Exception as e:
        logger.error(f"Parler TTS unexpected error: {e}")
        raise


async def _call_xtts(base_url: str, text: str, settings, client: httpx.AsyncClient) -> bytes:
    url = base_url.rstrip('/') + '/synthesize'
    payload = {
        "text": text,
        "voice": settings.tts_voice or "default",
        "language": settings.tts_language or "en",
        "format": "wav",
    }
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return resp.content