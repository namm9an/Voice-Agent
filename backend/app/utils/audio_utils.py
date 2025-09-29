"""
Audio processing utilities: validation, conversion, and basic analysis helpers.
"""

import io
import wave
from typing import Tuple, Dict
from pydub import AudioSegment, effects
from pydub.silence import detect_nonsilent
import math

from app.utils.error_handlers import InvalidAudioFormatError


def validate_audio_format(audio_data: bytes) -> bool:
    # Accept WAV (RIFF) and WebM (EBML header 0x1A45DFA3)
    if not audio_data or len(audio_data) < 1000:
        return False
    header = audio_data[:12]
    if header.startswith(b'RIFF'):
        return True
    if header.startswith(b'\x1A\x45\xDF\xA3'):
        return True
    # Be permissive in Phase 2 to allow browser MediaRecorder formats
    return True


def convert_to_wav(audio_data: bytes) -> bytes:
    # Phase 2: pass-through. Whisper can accept WebM; conversion not required here.
    if not validate_audio_format(audio_data):
        raise InvalidAudioFormatError("Unsupported or corrupt audio format")
    return audio_data


def get_audio_info(audio_data: bytes) -> Dict[str, float]:
    try:
        with io.BytesIO(audio_data) as bio:
            with wave.open(bio, 'rb') as wf:
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                channels = wf.getnchannels()
                duration = nframes / float(framerate) if framerate else 0.0
                return {
                    "sample_rate": float(framerate),
                    "channels": float(channels),
                    "duration_seconds": float(duration),
                }
    except Exception:
        return {"sample_rate": 0.0, "channels": 0.0, "duration_seconds": 0.0}


def validate_audio_constraints(audio_data: bytes) -> Tuple[bool, str]:
    if not audio_data or len(audio_data) < 1000:
        return False, "Audio too short or empty"
    if not validate_audio_format(audio_data):
        return False, "Invalid or unsupported audio format"
    return True, ""


def enhance_audio_quality(audio_data: bytes) -> bytes:
    # Pipeline: normalize -> trim silence -> resample -> return WAV
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_data))
        # Normalize
        seg = effects.normalize(seg)
        # Trim silence
        nonsilent = detect_nonsilent(seg, min_silence_len=300, silence_thresh=seg.dBFS - 16)
        if nonsilent:
            start = max(0, nonsilent[0][0] - 100)
            end = min(len(seg), nonsilent[-1][1] + 100)
            seg = seg[start:end]
        # Resample to 16k mono
        seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        out = io.BytesIO()
        seg.export(out, format='wav')
        return out.getvalue()
    except Exception:
        return audio_data


def normalize_audio(audio_data: bytes) -> bytes:
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_data))
        seg = effects.normalize(seg)
        out = io.BytesIO()
        seg.export(out, format='wav')
        return out.getvalue()
    except Exception:
        return audio_data


def remove_silence(audio_data: bytes) -> bytes:
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_data))
        nonsilent = detect_nonsilent(seg, min_silence_len=300, silence_thresh=seg.dBFS - 16)
        if not nonsilent:
            return audio_data
        start = max(0, nonsilent[0][0] - 100)
        end = min(len(seg), nonsilent[-1][1] + 100)
        seg = seg[start:end]
        out = io.BytesIO()
        seg.export(out, format='wav')
        return out.getvalue()
    except Exception:
        return audio_data


def resample_audio(audio_data: bytes, target_rate: int = 16000) -> bytes:
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_data))
        seg = seg.set_frame_rate(target_rate).set_channels(1).set_sample_width(2)
        out = io.BytesIO()
        seg.export(out, format='wav')
        return out.getvalue()
    except Exception:
        return audio_data


def compress_audio(audio_data: bytes) -> bytes:
    # Simple downsample-based compression for size control
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_data))
        seg = seg.set_frame_rate(12000).set_channels(1).set_sample_width(2)
        out = io.BytesIO()
        seg.export(out, format='wav')
        return out.getvalue()
    except Exception:
        return audio_data