"""
Audio test utilities for LiveKit streaming verification
"""
import io
import wave
import numpy as np
import logging

logger = logging.getLogger(__name__)


def generate_test_tone(
    frequency: int = 440,
    duration_seconds: float = 2.0,
    sample_rate: int = 16000,
    amplitude: float = 0.3
) -> bytes:
    """
    Generate a test tone WAV file

    Args:
        frequency: Tone frequency in Hz (default 440Hz = A4 note)
        duration_seconds: Duration in seconds
        sample_rate: Sample rate in Hz
        amplitude: Amplitude (0.0 to 1.0)

    Returns:
        WAV file bytes
    """
    # Generate sine wave
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), False)
    audio_data = np.sin(2 * np.pi * frequency * t) * amplitude

    # Convert to 16-bit PCM
    audio_data = (audio_data * 32767).astype(np.int16)

    # Create WAV file in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())

    wav_bytes = wav_buffer.getvalue()
    logger.info(
        f"Generated test tone: {frequency}Hz, {duration_seconds}s, "
        f"{sample_rate}Hz, {len(wav_bytes)} bytes"
    )

    return wav_bytes


def generate_beep_sequence(
    num_beeps: int = 3,
    beep_duration: float = 0.2,
    gap_duration: float = 0.3,
    sample_rate: int = 16000
) -> bytes:
    """
    Generate a sequence of beeps for testing

    Args:
        num_beeps: Number of beeps
        beep_duration: Duration of each beep in seconds
        gap_duration: Gap between beeps in seconds
        sample_rate: Sample rate in Hz

    Returns:
        WAV file bytes
    """
    segments = []

    for i in range(num_beeps):
        # Add beep
        beep_freq = 440 + (i * 100)  # Increasing frequency
        t_beep = np.linspace(0, beep_duration, int(sample_rate * beep_duration), False)
        beep = np.sin(2 * np.pi * beep_freq * t_beep) * 0.3

        segments.append(beep)

        # Add gap (silence)
        if i < num_beeps - 1:
            gap = np.zeros(int(sample_rate * gap_duration))
            segments.append(gap)

    # Concatenate all segments
    audio_data = np.concatenate(segments)

    # Convert to 16-bit PCM
    audio_data = (audio_data * 32767).astype(np.int16)

    # Create WAV file
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())

    wav_bytes = wav_buffer.getvalue()
    logger.info(f"Generated beep sequence: {num_beeps} beeps, {len(wav_bytes)} bytes")

    return wav_bytes
