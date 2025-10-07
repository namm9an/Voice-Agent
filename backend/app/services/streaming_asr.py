"""
Streaming ASR service - processes audio in 500ms windows for real-time transcription
"""
import asyncio
import logging
import time
from collections import deque
from typing import Optional, Callable
import aiohttp
import io
import wave

from app.config.settings import get_settings
from app.utils.error_handlers import WhisperServiceError

logger = logging.getLogger(__name__)


class StreamingASR:
    """Processes audio frames in real-time with 500ms rolling window"""

    def __init__(self, session_id: str, on_partial_transcript: Callable):
        self.session_id = session_id
        self.on_partial_transcript = on_partial_transcript  # Callback for partial results
        self.settings = get_settings()

        # Rolling buffer configuration
        self.sample_rate = 48000  # LiveKit default
        self.window_duration_ms = 500  # 500ms windows
        self.slide_duration_ms = 250  # Slide forward every 250ms

        self.window_samples = int(self.sample_rate * self.window_duration_ms / 1000)
        self.slide_samples = int(self.sample_rate * self.slide_duration_ms / 1000)

        # Frame queue (producer-consumer pattern)
        self.frame_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.running = False
        self.consumer_task: Optional[asyncio.Task] = None

        # Rolling buffer for audio frames
        self.audio_buffer = deque(maxlen=self.window_samples * 2)  # 1s max buffer

        # Statistics
        self.chunk_count = 0
        self.total_transcription_time = 0

        # HTTP session for Whisper
        self.http_session: Optional[aiohttp.ClientSession] = None

        logger.info(
            f"[ASR-INIT] session={session_id}, "
            f"window={self.window_duration_ms}ms, "
            f"slide={self.slide_duration_ms}ms"
        )

    async def start(self):
        """Start the ASR consumer task"""
        self.running = True

        # Create HTTP session with optimized settings
        timeout = aiohttp.ClientTimeout(total=5, connect=2)
        connector = aiohttp.TCPConnector(
            limit=5,
            limit_per_host=3,
            ttl_dns_cache=300,
            keepalive_timeout=30
        )
        self.http_session = aiohttp.ClientSession(timeout=timeout, connector=connector)

        self.consumer_task = asyncio.create_task(self._asr_consumer())
        logger.info(f"[ASR-START] session={self.session_id}")

    async def stop(self):
        """Stop the ASR consumer task"""
        self.running = False
        if self.consumer_task:
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                pass

        if self.http_session and not self.http_session.closed:
            await self.http_session.close()

        logger.info(f"[ASR-STOP] session={self.session_id}, chunks={self.chunk_count}")

    async def push_frame(self, frame_data: bytes):
        """
        Push audio frame to processing queue (producer)

        Args:
            frame_data: Raw PCM audio bytes (16-bit)
        """
        try:
            await self.frame_queue.put(frame_data)
        except asyncio.QueueFull:
            logger.warning(f"[ASR-QUEUE-FULL] session={self.session_id}")

    async def _asr_consumer(self):
        """Consumer task - processes frames and calls Whisper"""
        frames_since_last_process = 0

        while self.running:
            try:
                # Get frame from queue (non-blocking with timeout)
                try:
                    frame_data = await asyncio.wait_for(
                        self.frame_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue

                # Add to rolling buffer
                # Convert bytes to list of samples (16-bit PCM)
                import numpy as np
                samples = np.frombuffer(frame_data, dtype=np.int16)
                self.audio_buffer.extend(samples)

                frames_since_last_process += 1

                # Process when we've accumulated enough frames for window slide
                frames_per_slide = self.slide_samples // len(samples)

                if frames_since_last_process >= frames_per_slide and len(self.audio_buffer) >= self.window_samples:
                    frames_since_last_process = 0

                    # Extract current window
                    window = np.array(list(self.audio_buffer)[-self.window_samples:])

                    # Convert to WAV and transcribe
                    await self._transcribe_window(window)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ASR-CONSUMER-ERROR] {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def _transcribe_window(self, audio_samples):
        """
        Transcribe a single audio window

        Args:
            audio_samples: numpy array of int16 samples
        """
        self.chunk_count += 1
        start_time = time.time()

        try:
            # Convert to WAV format
            wav_data = self._samples_to_wav(audio_samples, self.sample_rate)

            # Call Whisper Turbo with retry logic
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    transcript = await self._call_whisper(wav_data)

                    if transcript and transcript.strip():
                        elapsed = time.time() - start_time
                        self.total_transcription_time += elapsed

                        logger.info(
                            f"[ASR] chunk {self.chunk_count} → \"{transcript}\" "
                            f"({elapsed:.2f}s)"
                        )

                        # Send partial transcript to frontend
                        await self.on_partial_transcript(transcript, is_final=False)
                        break
                    else:
                        logger.debug(f"[ASR] chunk {self.chunk_count} → (silence)")
                        break

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt < max_retries:
                        logger.warning(f"[ASR-RETRY] attempt {attempt + 1}: {e}")
                        await asyncio.sleep(0.2)
                    else:
                        logger.error(f"[ASR-FAILED] chunk {self.chunk_count}: {e}")
                        break

        except Exception as e:
            logger.error(f"[ASR-ERROR] chunk {self.chunk_count}: {e}", exc_info=True)

    async def _call_whisper(self, wav_data: bytes) -> str:
        """
        Call Whisper Turbo API

        Args:
            wav_data: WAV file bytes

        Returns:
            Transcription text
        """
        if not self.http_session:
            raise WhisperServiceError("HTTP session not initialized")

        # Create form data
        form = aiohttp.FormData()
        form.add_field('file', wav_data, filename='audio.wav', content_type='audio/wav')
        form.add_field('model', self.settings.whisper_model)

        headers = {
            'Authorization': f'Bearer {self.settings.whisper_api_key}'
        }

        url = f"{self.settings.whisper_base_url}audio/transcriptions"

        async with self.http_session.post(url, data=form, headers=headers) as response:
            if response.status == 200:
                result = await response.json()
                return result.get('text', '').strip()
            else:
                error_text = await response.text()
                raise WhisperServiceError(f"Whisper API error {response.status}: {error_text}")

    def _samples_to_wav(self, samples, sample_rate: int) -> bytes:
        """Convert numpy samples to WAV bytes"""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())
        return wav_buffer.getvalue()

    async def flush_buffer(self):
        """Process remaining buffer at end of speech"""
        if len(self.audio_buffer) > 0:
            logger.info(f"[ASR-FLUSH] Processing final {len(self.audio_buffer)} samples")
            import numpy as np
            final_window = np.array(list(self.audio_buffer))
            await self._transcribe_window(final_window)

            # Mark as final
            await self.on_partial_transcript("", is_final=True)
