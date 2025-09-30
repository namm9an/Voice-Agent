"""
Audio processing routes - /process-audio endpoint with proper audio handling
"""
import logging
import io
import tempfile
import os
from fastapi import APIRouter, UploadFile, File, HTTPException, Header
from fastapi.responses import Response
from pydub import AudioSegment
import numpy as np
from scipy.io import wavfile
from typing import Optional

from app.services.whisper_service import WhisperService
from app.services.qwen_service import QwenService
from app.services.tts_service import TTSService
from app.services.vad_service import get_vad_service
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

_whisper_service = None
_qwen_service = None
_tts_service = None
_vad_service = None


def get_whisper_service() -> WhisperService:
    global _whisper_service
    if _whisper_service is None:
        _whisper_service = WhisperService()
    return _whisper_service


def get_qwen_service() -> QwenService:
    global _qwen_service
    if _qwen_service is None:
        _qwen_service = QwenService()
    return _qwen_service


def get_tts_service() -> TTSService:
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service


def get_vad() -> 'VADService':
    """Get VAD service instance"""
    global _vad_service
    if _vad_service is None:
        _vad_service = get_vad_service()
    return _vad_service


@router.post("/process-audio")
async def process_audio(
    file: UploadFile = File(...),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    try:
        # Use session ID from header or default
        session_id = x_session_id or "default"
        logger.info(f"Processing audio for session: {session_id}")

        # Read the uploaded file
        audio_data = await file.read()
        logger.info(f"Received audio file: {len(audio_data)} bytes")

        # Step 1: Apply VAD to check if audio contains speech
        vad = get_vad()
        has_speech = vad.has_speech(audio_data, min_speech_duration_ms=300)

        if not has_speech:
            logger.warning(f"No speech detected in audio for session {session_id}")
            raise HTTPException(status_code=400, detail="No speech detected in audio")

        # Step 2: Extract only speech segments (removes silence)
        speech_audio = vad.extract_speech_audio(audio_data, padding_ms=300)
        if not speech_audio:
            logger.warning(f"VAD failed to extract speech for session {session_id}")
            speech_audio = audio_data  # Fallback to original audio

        logger.info(f"VAD extracted speech: {len(audio_data)} -> {len(speech_audio)} bytes")

        # Step 3: Convert to proper WAV format for Whisper
        audio = AudioSegment.from_file(io.BytesIO(speech_audio))

        # Whisper requirements: 16kHz, mono, 16-bit PCM WAV
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)  # 16-bit

        # Export to WAV bytes
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        wav_data = buffer.getvalue()

        logger.info(f"Converted to WAV: {len(wav_data)} bytes")

        # Step 4: Transcribe with Whisper
        transcription = await get_whisper_service().transcribe_audio(wav_data)
        logger.info(f"Transcription: {transcription}")

        if not transcription:
            raise HTTPException(status_code=400, detail="No speech detected")

        ai_response = await get_qwen_service().generate_response(transcription, session_id=session_id)
        logger.info(f"AI Response: {ai_response}")

        audio_response = await get_tts_service().synthesize_speech(ai_response)
        logger.info(f"TTS Generated: {len(audio_response)} bytes")

        # Sanitize text for HTTP headers (remove newlines and control characters)
        def sanitize_header(text: str) -> str:
            # Replace newlines with spaces
            text = text.replace('\n', ' ').replace('\r', ' ')
            # Replace smart quotes and other unicode with ASCII equivalents
            text = text.replace('\u2019', "'")  # Right single quotation mark
            text = text.replace('\u2018', "'")  # Left single quotation mark
            text = text.replace('\u201c', '"')  # Left double quotation mark
            text = text.replace('\u201d', '"')  # Right double quotation mark
            text = text.replace('\u2013', '-')  # En dash
            text = text.replace('\u2014', '-')  # Em dash
            text = text.replace('\u2026', '...')  # Ellipsis
            # Remove any remaining non-latin-1 characters
            text = text.encode('ascii', errors='ignore').decode('ascii')
            # Collapse multiple spaces
            return ' '.join(text.split())

        return Response(
            content=audio_response,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=response.wav",
                "Cache-Control": "no-cache",
                "X-Transcription": sanitize_header(transcription),
                "X-AI-Response": sanitize_header(ai_response)
            }
        )

    except Exception as e:
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Audio processing failed")


@router.get("/voices")
async def get_available_voices():
    """Get available voice options"""
    settings = get_settings()
    return {
        "available_voices": settings.available_voices,
        "current_voice": settings.tts_voice
    }


@router.post("/voices/{voice_name}")
async def set_voice(voice_name: str):
    """Set the TTS voice"""
    settings = get_settings()
    if voice_name not in settings.available_voices:
        raise HTTPException(status_code=400, detail=f"Voice '{voice_name}' not available")
    
    # Update the voice setting (this will persist for the session)
    settings.tts_voice = voice_name
    return {"message": f"Voice set to {voice_name}", "voice": voice_name}
