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
        self._session_voices: Dict[str, str] = {}  # session_id -> voice_name mapping

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client"""
        if self._client is None or self._client.is_closed:
            # Increased timeout for longer text responses (like ChatGPT voice mode)
            timeout = httpx.Timeout(60.0, connect=10.0, read=50.0)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.close()

    def set_voice(self, session_id: str, voice_name: str):
        """Set voice for a specific session"""
        self._session_voices[session_id] = voice_name
        logger.info(f"Voice set to '{voice_name}' for session {session_id}")

    def get_voice(self, session_id: str = "default") -> str:
        """Get voice for a specific session"""
        return self._session_voices.get(session_id, self.settings.tts_voice or "female")

    def _get_cache_key(self, text: str, voice: str) -> str:
        """Generate cache key from text and voice"""
        cache_input = f"{text}:{voice}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    async def synthesize_speech(self, text: str, session_id: str = "default") -> bytes:
        if not text or not text.strip():
            logger.warning("Empty text for TTS, generating fallback beep")
            return self._generate_fallback_beep()

        # Get voice for this session
        voice = self.get_voice(session_id)

        # Check cache first for exact match
        cache_key = self._get_cache_key(text, voice)
        if cache_key in self._cache:
            logger.info(f"TTS cache hit for text: {text[:50]}...")
            return self._cache[cache_key]

        # For long texts (>100 chars), split into sentences and synthesize in chunks
        if len(text) > 100:
            logger.info(f"Long text detected ({len(text)} chars), using chunked synthesis")
            return await self._synthesize_chunked(text, cache_key, voice, session_id)

        # Try Parler first with retry logic
        if self.settings.parler_tts_base_url:
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Attempting Parler TTS (attempt {attempt + 1}/{max_retries + 1})")
                    logger.info(f"Text length: {len(text)} chars, URL: {self.settings.parler_tts_base_url}")
                    import time
                    start_time = time.time()

                    audio = await _call_parler(
                        self.settings.parler_tts_base_url,
                        text,
                        voice,
                        self.settings,
                        await self._get_client()
                    )

                    elapsed = time.time() - start_time
                    if audio:
                        logger.info(f"✓ Parler TTS successful in {elapsed:.2f}s, generated {len(audio)} bytes")
                        self._add_to_cache(cache_key, audio)
                        return audio
                    else:
                        logger.warning(f"✗ Parler TTS returned empty audio after {elapsed:.2f}s")
                        break  # Don't retry if we got empty audio
                except httpx.TimeoutException as e:
                    elapsed = time.time() - start_time
                    logger.warning(f"✗ Parler TTS timeout after {elapsed:.2f}s on attempt {attempt + 1}: {e}")
                    if attempt < max_retries:
                        logger.info(f"Retrying Parler TTS in 2 seconds...")
                        await asyncio.sleep(2)
                        continue
                    else:
                        logger.error(f"✗ Parler TTS failed after {max_retries + 1} attempts due to timeout")
                except Exception as e:
                    logger.error(f"✗ Parler TTS failed with error: {e}", exc_info=True)
                    break  # Don't retry on non-timeout errors

        # Fallback XTTS
        if self.settings.xtts_tts_base_url:
            try:
                audio = await _call_xtts(
                    self.settings.xtts_tts_base_url,
                    text,
                    voice,
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

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences for chunked synthesis"""
        import re
        # Split on sentence boundaries (., !, ?, but not Mr., Dr., etc.)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

        # Group small sentences together (target ~30-60 chars per chunk for better quality)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) < 60:
                current_chunk += " " + sentence if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    async def _synthesize_chunked(self, text: str, full_cache_key: str, voice: str, session_id: str) -> bytes:
        """Synthesize long text in chunks and concatenate"""
        chunks = self._split_into_sentences(text)
        logger.info(f"Split text into {len(chunks)} chunks for synthesis")

        # Synthesize each chunk
        audio_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Synthesizing chunk {i+1}/{len(chunks)}: {chunk[:50]}...")

            # Check cache for this chunk
            chunk_cache_key = self._get_cache_key(chunk, voice)
            if chunk_cache_key in self._cache:
                logger.info(f"Cache hit for chunk {i+1}")
                audio_chunks.append(self._cache[chunk_cache_key])
                continue

            # Synthesize this chunk (short text, use direct synthesis)
            chunk_audio = await self._synthesize_direct(chunk, voice)
            if chunk_audio:
                audio_chunks.append(chunk_audio)
                self._add_to_cache(chunk_cache_key, chunk_audio)
            else:
                logger.warning(f"Failed to synthesize chunk {i+1}, skipping")

        if not audio_chunks:
            logger.error("All chunks failed to synthesize")
            return self._generate_fallback_beep()

        # Concatenate audio chunks
        combined_audio = self._concatenate_wav_files(audio_chunks)
        logger.info(f"Concatenated {len(audio_chunks)} chunks into {len(combined_audio)} bytes")

        # Verify the concatenated WAV is valid
        try:
            test_wav = io.BytesIO(combined_audio)
            with wave.open(test_wav, 'rb') as wav:
                logger.info(f"Final WAV: {wav.getnchannels()}ch, {wav.getframerate()}Hz, {wav.getnframes()} frames")
        except Exception as e:
            logger.error(f"Invalid concatenated WAV: {e}")
            return self._generate_fallback_beep()

        # Cache the full result
        self._add_to_cache(full_cache_key, combined_audio)

        return combined_audio

    async def _synthesize_direct(self, text: str, voice: str) -> bytes:
        """Direct synthesis for a single chunk (no caching, no chunking)"""
        # Try Parler first with retry logic
        if self.settings.parler_tts_base_url:
            max_retries = 1  # Fewer retries for chunks
            for attempt in range(max_retries + 1):
                try:
                    import time
                    start_time = time.time()

                    audio = await _call_parler(
                        self.settings.parler_tts_base_url,
                        text,
                        voice,
                        self.settings,
                        await self._get_client()
                    )

                    elapsed = time.time() - start_time
                    if audio:
                        logger.info(f"✓ Parler chunk TTS in {elapsed:.2f}s, {len(audio)} bytes")
                        return audio
                    else:
                        logger.warning(f"✗ Parler returned empty audio after {elapsed:.2f}s")
                        break
                except httpx.TimeoutException as e:
                    logger.warning(f"✗ Parler chunk TTS timeout: {e}")
                    if attempt < max_retries:
                        await asyncio.sleep(1)
                        continue
                    else:
                        break
                except Exception as e:
                    logger.error(f"✗ Parler chunk TTS error: {e}")
                    break

        # Fallback XTTS
        if self.settings.xtts_tts_base_url:
            try:
                audio = await _call_xtts(
                    self.settings.xtts_tts_base_url,
                    text,
                    voice,
                    self.settings,
                    await self._get_client()
                )
                if audio:
                    return audio
            except Exception as e:
                logger.error(f"XTTS chunk fallback failed: {e}")

        # Return None if all fail - caller will handle fallback
        return None

    def _concatenate_wav_files(self, audio_chunks: list[bytes]) -> bytes:
        """Concatenate multiple WAV files into a single WAV file using pydub for better compatibility"""
        if not audio_chunks:
            return self._generate_fallback_beep()

        if len(audio_chunks) == 1:
            return audio_chunks[0]

        try:
            from pydub import AudioSegment

            # Load all audio chunks as AudioSegments
            segments = []
            for i, chunk in enumerate(audio_chunks):
                try:
                    segment = AudioSegment.from_wav(io.BytesIO(chunk))
                    segments.append(segment)
                    logger.info(f"Loaded chunk {i+1}: duration={len(segment)}ms")
                except Exception as e:
                    logger.error(f"Failed to load chunk {i+1}: {e}")
                    continue

            if not segments:
                logger.error("No valid audio segments to concatenate")
                return self._generate_fallback_beep()

            # Concatenate all segments
            combined = segments[0]
            for segment in segments[1:]:
                combined += segment

            logger.info(f"Combined audio: duration={len(combined)}ms")

            # Export as WAV
            output = io.BytesIO()
            combined.export(output, format="wav")
            result = output.getvalue()

            logger.info(f"Concatenated WAV: {len(result)} bytes")
            return result

        except Exception as e:
            logger.error(f"pydub concatenation failed: {e}, falling back to wave module")
            # Fallback to wave module concatenation
            return self._concatenate_wav_files_basic(audio_chunks)

    def _concatenate_wav_files_basic(self, audio_chunks: list[bytes]) -> bytes:
        """Basic WAV concatenation using wave module (fallback)"""
        if len(audio_chunks) == 1:
            return audio_chunks[0]

        # Parse the first WAV to get format info
        first_wav = io.BytesIO(audio_chunks[0])
        with wave.open(first_wav, 'rb') as wav:
            channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            framerate = wav.getframerate()

        # Extract audio data from all chunks
        all_frames = []
        for chunk in audio_chunks:
            chunk_io = io.BytesIO(chunk)
            with wave.open(chunk_io, 'rb') as wav:
                all_frames.append(wav.readframes(wav.getnframes()))

        # Combine all frames
        combined_frames = b''.join(all_frames)

        # Create new WAV file with combined audio
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav_out:
            wav_out.setnchannels(channels)
            wav_out.setsampwidth(sampwidth)
            wav_out.setframerate(framerate)
            wav_out.writeframes(combined_frames)

        return output.getvalue()

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


async def _call_parler(base_url: str, text: str, voice_key: str, settings, client: httpx.AsyncClient) -> bytes:
    url = base_url.rstrip('/') + '/tts'
    logger.info(f"Parler TTS URL: {url}")

    # Get voice description from settings
    voice_description = settings.available_voices.get(voice_key, settings.available_voices["female"])
    logger.info(f"Using voice: {voice_key} - {voice_description[:50]}...")

    # Use proper Parler TTS API format with description
    payload = {
        "text": text,
        "description": voice_description
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


async def _call_xtts(base_url: str, text: str, voice_key: str, settings, client: httpx.AsyncClient) -> bytes:
    url = base_url.rstrip('/') + '/synthesize'
    payload = {
        "text": text,
        "voice": voice_key,
        "language": settings.tts_language or "en",
        "format": "wav",
    }
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return resp.content