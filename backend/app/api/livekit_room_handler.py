"""
LiveKit Room Handler - Manages voice agent sessions in LiveKit rooms
Handles real-time audio streaming, transcription, LLM, and TTS
"""
import asyncio
import logging
from livekit import rtc
from typing import Optional
import io
import wave

from app.services.whisper_service import WhisperService
from app.services.qwen_service import QwenService
from app.services.tts_service import TTSService
from app.services.vad_service import get_vad_service

logger = logging.getLogger(__name__)


class LiveKitRoomHandler:
    """Handles LiveKit room connections and orchestrates voice agent pipeline"""

    def __init__(self):
        self.whisper_service = WhisperService()
        self.qwen_service = QwenService()
        self.tts_service = TTSService()
        self.vad_service = get_vad_service()
        self.active_sessions = {}

    async def handle_room(self, room: rtc.Room, participant_identity: str):
        """
        Main room handler - orchestrates the voice agent pipeline

        Args:
            room: LiveKit room instance
            participant_identity: Participant identifier
        """
        session_id = f"livekit_{participant_identity}"
        logger.info(f"Starting LiveKit room handler for session: {session_id}")

        audio_buffer = bytearray()
        sample_rate = 16000
        silence_duration = 0
        is_processing = False

        try:
            # Subscribe to audio track
            async for event in room.on('track_subscribed'):
                track = event.track
                if track.kind == rtc.TrackKind.KIND_AUDIO:
                    logger.info(f"Subscribed to audio track: {track.sid}")

                    async for frame in track:
                        if is_processing:
                            # Skip processing if already handling a request
                            continue

                        # Convert AudioFrame to bytes
                        audio_data = frame.data
                        audio_buffer.extend(audio_data)

                        # Check for speech using VAD on accumulated buffer
                        if len(audio_buffer) > sample_rate * 2:  # 2 seconds of audio
                            wav_data = self._create_wav(bytes(audio_buffer), sample_rate)

                            # Check if speech detected
                            has_speech = self.vad_service.has_speech(
                                wav_data,
                                min_speech_duration_ms=500
                            )

                            if has_speech:
                                # Process the audio
                                is_processing = True
                                asyncio.create_task(
                                    self._process_audio_chunk(
                                        bytes(audio_buffer),
                                        sample_rate,
                                        room,
                                        session_id
                                    )
                                )
                                audio_buffer.clear()
                                is_processing = False
                            else:
                                # Clear buffer if too long without speech
                                if len(audio_buffer) > sample_rate * 5:  # 5 seconds
                                    audio_buffer.clear()

        except Exception as e:
            logger.error(f"Room handler error for session {session_id}: {e}", exc_info=True)
        finally:
            logger.info(f"Room handler ended for session: {session_id}")

    async def _process_audio_chunk(
        self,
        audio_data: bytes,
        sample_rate: int,
        room: rtc.Room,
        session_id: str
    ):
        """
        Process a single audio chunk through the pipeline

        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate
            room: LiveKit room for sending responses
            session_id: Session identifier
        """
        try:
            import time
            start_time = time.time()

            # Convert to WAV format
            wav_data = self._create_wav(audio_data, sample_rate)

            # Step 1: Transcribe with Whisper
            logger.info(f"[{session_id}] Starting transcription...")
            transcription = await self.whisper_service.transcribe_audio(wav_data)

            if not transcription or len(transcription.strip()) < 2:
                logger.warning(f"[{session_id}] Empty or very short transcription")
                return

            transcription_time = time.time() - start_time
            logger.info(f"[{session_id}] Transcription: '{transcription}' ({transcription_time:.2f}s)")

            # Send transcription to client via DataChannel
            await self._send_data_message(room, {
                "type": "transcription",
                "text": transcription
            })

            # Step 2: Generate LLM response
            logger.info(f"[{session_id}] Generating LLM response...")
            llm_start = time.time()
            ai_response = await self.qwen_service.generate_response(
                transcription,
                session_id=session_id
            )
            llm_time = time.time() - llm_start
            logger.info(f"[{session_id}] LLM response: '{ai_response}' ({llm_time:.2f}s)")

            # Send AI response text to client
            await self._send_data_message(room, {
                "type": "response",
                "text": ai_response
            })

            # Step 3: Generate TTS audio
            logger.info(f"[{session_id}] Generating TTS audio...")
            tts_start = time.time()
            audio_response = await self.tts_service.synthesize_speech(
                ai_response,
                session_id=session_id
            )
            tts_time = time.time() - tts_start
            logger.info(f"[{session_id}] TTS generated: {len(audio_response)} bytes ({tts_time:.2f}s)")

            # Step 4: Stream TTS audio back to client
            await self._publish_audio(room, audio_response)

            total_time = time.time() - start_time
            logger.info(
                f"[{session_id}] Pipeline complete: "
                f"Total={total_time:.2f}s "
                f"(ASR={transcription_time:.2f}s, LLM={llm_time:.2f}s, TTS={tts_time:.2f}s)"
            )

        except Exception as e:
            logger.error(f"[{session_id}] Pipeline error: {e}", exc_info=True)
            await self._send_data_message(room, {
                "type": "error",
                "message": str(e)
            })

    def _create_wav(self, audio_data: bytes, sample_rate: int = 16000) -> bytes:
        """Create WAV file from raw audio bytes"""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data)
        return wav_buffer.getvalue()

    async def _send_data_message(self, room: rtc.Room, message: dict):
        """Send data message to all participants"""
        try:
            import json
            data = json.dumps(message).encode('utf-8')
            await room.local_participant.publish_data(data, reliable=True)
            logger.debug(f"Sent data message: {message.get('type')}")
        except Exception as e:
            logger.error(f"Failed to send data message: {e}")

    async def _publish_audio(self, room: rtc.Room, audio_wav: bytes):
        """
        Publish audio response to the room

        Args:
            room: LiveKit room
            audio_wav: WAV audio data
        """
        try:
            # Parse WAV to get raw PCM data
            with wave.open(io.BytesIO(audio_wav), 'rb') as wav:
                sample_rate = wav.getframerate()
                num_channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                audio_data = wav.readframes(wav.getnframes())

            logger.info(f"Publishing audio: {len(audio_data)} bytes, {sample_rate}Hz, {num_channels}ch")

            # Create audio source
            audio_source = rtc.AudioSource(sample_rate, num_channels)

            # Create track
            track = rtc.LocalAudioTrack.create_audio_track("agent-voice", audio_source)

            # Publish track
            options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            publication = await room.local_participant.publish_track(track, options)

            logger.info(f"Published audio track: {publication.sid}")

            # Stream audio in chunks (20ms chunks for smooth playback)
            chunk_duration_ms = 20
            chunk_samples = int(sample_rate * chunk_duration_ms / 1000)
            bytes_per_sample = sample_width * num_channels
            chunk_size = chunk_samples * bytes_per_sample

            import numpy as np

            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]

                # Pad last chunk if needed
                if len(chunk) < chunk_size:
                    chunk = chunk + b'\x00' * (chunk_size - len(chunk))

                # Convert to numpy array
                audio_array = np.frombuffer(chunk, dtype=np.int16)

                # Create audio frame
                frame = rtc.AudioFrame(
                    data=audio_array,
                    sample_rate=sample_rate,
                    num_channels=num_channels,
                    samples_per_channel=chunk_samples
                )

                # Capture frame
                await audio_source.capture_frame(frame)

                # Small delay to maintain real-time playback
                await asyncio.sleep(chunk_duration_ms / 1000.0)

            logger.info(f"Finished streaming audio track")

            # Keep track published briefly then unpublish
            await asyncio.sleep(0.1)
            await room.local_participant.unpublish_track(publication.sid)

        except Exception as e:
            logger.error(f"Failed to publish audio: {e}", exc_info=True)


# Global room handler instance
_room_handler: Optional[LiveKitRoomHandler] = None


def get_room_handler() -> LiveKitRoomHandler:
    """Get or create global room handler instance"""
    global _room_handler
    if _room_handler is None:
        _room_handler = LiveKitRoomHandler()
    return _room_handler
