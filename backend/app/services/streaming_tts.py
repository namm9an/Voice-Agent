"""
Streaming TTS service - generates speech in 1-2 sentence chunks
"""
import asyncio
import logging
import time
import re
import io
import wave
from typing import AsyncIterator, Callable, Optional
import aiohttp
import numpy as np

from app.config.settings import get_settings
from app.utils.error_handlers import TTSServiceError

logger = logging.getLogger(__name__)


class StreamingTTS:
    """Generates and streams TTS audio in real-time chunks"""

    def __init__(self, session_id: str, on_audio_chunk: Callable):
        self.session_id = session_id
        self.on_audio_chunk = on_audio_chunk  # Callback for audio frames
        self.settings = get_settings()

        # Audio configuration
        self.sample_rate = 16000
        self.channels = 1
        self.frame_duration_ms = 20  # 20ms frames
        self.samples_per_frame = int(self.sample_rate * self.frame_duration_ms / 1000)

        # HTTP session
        self.http_session: Optional[aiohttp.ClientSession] = None

        # Stats
        self.segment_count = 0
        self.total_frames = 0

        logger.info(f"[TTS-INIT] session={session_id}, rate={self.sample_rate}Hz")

    async def start(self):
        """Initialize HTTP session"""
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        connector = aiohttp.TCPConnector(
            limit=5,
            limit_per_host=3,
            keepalive_timeout=30
        )
        self.http_session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        logger.info(f"[TTS-START] session={self.session_id}")

    async def stop(self):
        """Close HTTP session"""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        logger.info(
            f"[TTS-STOP] session={self.session_id}, "
            f"segments={self.segment_count}, frames={self.total_frames}"
        )

    async def process_text(self, text: str):
        """
        Process text and stream TTS audio in chunks

        Args:
            text: Complete text to synthesize
        """
        if not text or not text.strip():
            logger.warning(f"[TTS] Empty text for session {self.session_id}")
            return

        # Split into sentence segments
        segments = self._split_into_segments(text)
        logger.info(f"[TTS-SEGMENTS] {len(segments)} segments from text: \"{text[:50]}...\"")

        # Process each segment
        for i, segment in enumerate(segments):
            self.segment_count = i + 1
            await self._process_segment(segment, i + 1, len(segments))

        logger.info(f"[TTS-DONE] session={self.session_id}, segments={len(segments)}")

    def _split_into_segments(self, text: str) -> list[str]:
        """
        Split text into natural sentence segments

        Args:
            text: Input text

        Returns:
            List of text segments (1-2 sentences each)
        """
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())

        segments = []
        current_segment = ""

        for sentence in sentences:
            # Estimate tokens (~4 chars per token)
            estimated_tokens = len(current_segment + " " + sentence) // 4

            if estimated_tokens < 25:
                # Add to current segment
                current_segment = (current_segment + " " + sentence).strip()
            else:
                # Save current segment and start new one
                if current_segment:
                    segments.append(current_segment)
                current_segment = sentence

        # Add final segment
        if current_segment:
            segments.append(current_segment)

        return segments

    async def _process_segment(self, segment_text: str, segment_num: int, total_segments: int):
        """
        Process a single text segment

        Args:
            segment_text: Text segment to synthesize
            segment_num: Current segment number
            total_segments: Total number of segments
        """
        start_time = time.time()
        logger.info(
            f"[TTS-START] segment={segment_num}/{total_segments}, "
            f"text=\"{segment_text}\""
        )

        try:
            # Generate audio with retry logic
            max_retries = 2
            audio_wav = None

            for attempt in range(max_retries + 1):
                try:
                    audio_wav = await self._call_parler_tts(segment_text)
                    break
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt < max_retries:
                        logger.warning(f"[TTS-RETRY] segment={segment_num}, attempt={attempt + 1}: {e}")
                        await asyncio.sleep(0.2)
                    else:
                        # Try XTTS fallback
                        logger.error(f"[TTS-PARLER-FAILED] Trying XTTS fallback")
                        if self.settings.xtts_tts_base_url:
                            audio_wav = await self._call_xtts_tts(segment_text)
                        else:
                            raise TTSServiceError(f"TTS failed after {max_retries + 1} attempts")

            if not audio_wav:
                logger.error(f"[TTS-ERROR] No audio generated for segment {segment_num}")
                return

            # Parse WAV and stream frames
            with wave.open(io.BytesIO(audio_wav), 'rb') as wav:
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                audio_data = wav.readframes(wav.getnframes())

            logger.info(
                f"[TTS-AUDIO] segment={segment_num}, "
                f"size={len(audio_wav)} bytes, "
                f"rate={sample_rate}Hz, channels={channels}"
            )

            # Stream audio frames
            await self._stream_audio_frames(audio_data, sample_rate, channels, segment_num)

            elapsed = time.time() - start_time
            logger.info(f"[TTS-SEGMENT-END] segment={segment_num}, time={elapsed:.2f}s")

            # Prepare next segment
            if segment_num < total_segments:
                logger.info(f"[TTS-NEXT] segment={segment_num + 1}/{total_segments}")

        except Exception as e:
            logger.error(f"[TTS-ERROR] segment={segment_num}: {e}", exc_info=True)

    async def _call_parler_tts(self, text: str) -> bytes:
        """
        Call Parler TTS API

        Args:
            text: Text to synthesize

        Returns:
            WAV audio bytes
        """
        if not self.http_session:
            raise TTSServiceError("HTTP session not initialized")

        url = f"{self.settings.parler_tts_base_url}/tts"

        # Get voice description
        voice_key = self.settings.tts_voice or "female"
        voice_description = self.settings.available_voices.get(
            voice_key,
            self.settings.available_voices["female"]
        )

        payload = {
            "text": text,
            "description": voice_description
        }

        headers = {"Content-Type": "application/json"}

        async with self.http_session.post(url, json=payload, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                raise TTSServiceError(f"Parler TTS error {response.status}: {error_text}")

            return await response.read()

    async def _call_xtts_tts(self, text: str) -> bytes:
        """
        Call XTTS fallback API

        Args:
            text: Text to synthesize

        Returns:
            WAV audio bytes
        """
        if not self.http_session:
            raise TTSServiceError("HTTP session not initialized")

        url = f"{self.settings.xtts_tts_base_url}/synthesize"

        payload = {
            "text": text,
            "voice": self.settings.tts_voice or "female",
            "language": self.settings.tts_language or "en",
            "format": "wav"
        }

        async with self.http_session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise TTSServiceError(f"XTTS error {response.status}: {error_text}")

            return await response.read()

    async def _stream_audio_frames(
        self,
        audio_data: bytes,
        sample_rate: int,
        channels: int,
        segment_num: int
    ):
        """
        Stream audio frames to frontend

        Args:
            audio_data: Raw PCM audio bytes
            sample_rate: Audio sample rate
            channels: Number of channels
            segment_num: Current segment number
        """
        # Convert to 16-bit samples
        samples = np.frombuffer(audio_data, dtype=np.int16)

        # Resample to 16kHz if needed
        if sample_rate != self.sample_rate:
            from scipy import signal
            num_samples = int(len(samples) * self.sample_rate / sample_rate)
            samples = signal.resample(samples, num_samples).astype(np.int16)

        # Stream in 20ms chunks
        bytes_per_frame = self.samples_per_frame * 2  # 2 bytes per sample (16-bit)
        frame_count = 0

        for i in range(0, len(samples) * 2, bytes_per_frame):
            frame_data = samples.tobytes()[i:i + bytes_per_frame]

            if len(frame_data) < bytes_per_frame:
                # Pad last frame
                frame_data = frame_data + b'\x00' * (bytes_per_frame - len(frame_data))

            # Emit audio chunk
            await self.on_audio_chunk(frame_data, segment_num, frame_count)

            frame_count += 1
            self.total_frames += 1

            # Log every 25th frame
            if frame_count % 25 == 0:
                logger.debug(
                    f"[TTS-CHUNK] segment={segment_num}, "
                    f"frame={frame_count}, samples={self.samples_per_frame}"
                )

            # Small delay to maintain real-time playback
            await asyncio.sleep(self.frame_duration_ms / 1000.0)

        logger.info(f"[TTS-FRAMES] segment={segment_num}, total_frames={frame_count}")
