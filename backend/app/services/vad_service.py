"""
Voice Activity Detection (VAD) service using WebRTC VAD
Detects speech segments in audio to filter out silence
"""
import logging
import webrtcvad
import struct
from typing import List, Tuple, Optional
from pydub import AudioSegment
import io

logger = logging.getLogger(__name__)


class VADService:
    def __init__(self, aggressiveness: int = 2):
        """
        Initialize VAD service

        Args:
            aggressiveness: VAD aggressiveness level (0-3)
                0 = Least aggressive (allows more non-speech)
                3 = Most aggressive (filters more aggressively)
                2 = Balanced (recommended for voice agents)
        """
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = 16000  # WebRTC VAD requires 8kHz, 16kHz, 32kHz, or 48kHz
        self.frame_duration_ms = 30  # Frame duration in milliseconds (10, 20, or 30)
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        logger.info(f"VAD initialized with aggressiveness={aggressiveness}, sample_rate={self.sample_rate}Hz")

    def is_speech(self, audio_frame: bytes) -> bool:
        """
        Check if a single audio frame contains speech

        Args:
            audio_frame: Audio frame bytes (must be exactly frame_size samples)

        Returns:
            True if frame contains speech, False otherwise
        """
        try:
            # WebRTC VAD requires exact frame size
            if len(audio_frame) != self.frame_size * 2:  # 2 bytes per sample (16-bit)
                return False
            return self.vad.is_speech(audio_frame, self.sample_rate)
        except Exception as e:
            logger.warning(f"VAD is_speech error: {e}")
            return False

    def detect_speech_segments(self, audio_data: bytes, return_timestamps: bool = False) -> List[Tuple[int, int]]:
        """
        Detect speech segments in audio data

        Args:
            audio_data: Raw audio bytes (any format that pydub can read)
            return_timestamps: If True, return timestamps in ms, otherwise byte positions

        Returns:
            List of (start, end) tuples representing speech segments
        """
        try:
            # Convert audio to 16kHz mono 16-bit PCM
            audio = AudioSegment.from_file(io.BytesIO(audio_data))
            audio = audio.set_frame_rate(self.sample_rate)
            audio = audio.set_channels(1)
            audio = audio.set_sample_width(2)  # 16-bit

            # Get raw audio data
            raw_data = audio.raw_data

            # Process in frames
            segments = []
            is_speaking = False
            speech_start = 0

            frame_size_bytes = self.frame_size * 2  # 2 bytes per sample

            for i in range(0, len(raw_data), frame_size_bytes):
                frame = raw_data[i:i + frame_size_bytes]

                # Only process complete frames
                if len(frame) == frame_size_bytes:
                    if self.is_speech(frame):
                        if not is_speaking:
                            # Start of speech segment
                            speech_start = i
                            is_speaking = True
                    else:
                        if is_speaking:
                            # End of speech segment
                            if return_timestamps:
                                # Convert byte positions to milliseconds
                                start_ms = int((speech_start / len(raw_data)) * len(audio))
                                end_ms = int((i / len(raw_data)) * len(audio))
                                segments.append((start_ms, end_ms))
                            else:
                                segments.append((speech_start, i))
                            is_speaking = False

            # Handle case where speech continues to end
            if is_speaking:
                if return_timestamps:
                    start_ms = int((speech_start / len(raw_data)) * len(audio))
                    end_ms = len(audio)
                    segments.append((start_ms, end_ms))
                else:
                    segments.append((speech_start, len(raw_data)))

            logger.info(f"VAD detected {len(segments)} speech segment(s)")
            return segments

        except Exception as e:
            logger.error(f"VAD detect_speech_segments error: {e}", exc_info=True)
            # Return full audio as single segment if VAD fails
            return [(0, len(audio_data))]

    def extract_speech_audio(self, audio_data: bytes, padding_ms: int = 300) -> Optional[bytes]:
        """
        Extract only speech segments from audio, removing silence

        Args:
            audio_data: Raw audio bytes
            padding_ms: Milliseconds of padding to add before/after speech segments

        Returns:
            Audio bytes containing only speech, or None if no speech detected
        """
        try:
            # Convert to AudioSegment
            audio = AudioSegment.from_file(io.BytesIO(audio_data))

            # Get speech segments in milliseconds
            segments = self.detect_speech_segments(audio_data, return_timestamps=True)

            if not segments:
                logger.warning("No speech detected in audio")
                return None

            # Combine all speech segments with padding
            speech_audio = AudioSegment.empty()

            for start_ms, end_ms in segments:
                # Add padding
                start_with_padding = max(0, start_ms - padding_ms)
                end_with_padding = min(len(audio), end_ms + padding_ms)

                # Extract segment
                segment = audio[start_with_padding:end_with_padding]
                speech_audio += segment

            # Export to WAV bytes
            buffer = io.BytesIO()
            speech_audio.export(buffer, format="wav")
            result = buffer.getvalue()

            logger.info(f"Extracted speech: {len(audio)}ms -> {len(speech_audio)}ms ({len(segments)} segments)")
            return result

        except Exception as e:
            logger.error(f"VAD extract_speech_audio error: {e}", exc_info=True)
            # Return original audio if extraction fails
            return audio_data

    def has_speech(self, audio_data: bytes, min_speech_duration_ms: int = 300) -> bool:
        """
        Check if audio contains meaningful speech

        Args:
            audio_data: Raw audio bytes
            min_speech_duration_ms: Minimum duration of speech to consider valid

        Returns:
            True if audio contains speech longer than min_speech_duration_ms
        """
        segments = self.detect_speech_segments(audio_data, return_timestamps=True)

        if not segments:
            return False

        # Calculate total speech duration
        total_speech_ms = sum(end - start for start, end in segments)

        has_valid_speech = total_speech_ms >= min_speech_duration_ms
        logger.info(f"Total speech duration: {total_speech_ms}ms (min: {min_speech_duration_ms}ms) - valid: {has_valid_speech}")

        return has_valid_speech


# Global VAD service instance
_vad_service: Optional[VADService] = None


def get_vad_service() -> VADService:
    """Get or create global VAD service instance"""
    global _vad_service
    if _vad_service is None:
        _vad_service = VADService(aggressiveness=2)
    return _vad_service