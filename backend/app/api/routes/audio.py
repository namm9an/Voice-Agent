"""
Audio processing routes - /process-audio endpoint with proper audio handling
"""
import logging
import io
import tempfile
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydub import AudioSegment
import numpy as np
from scipy.io import wavfile

from app.services.whisper_service import WhisperService
from app.services.qwen_service import QwenService
from app.services.tts_service import TTSService
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

_whisper_service = None
_qwen_service = None
_tts_service = None


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


@router.post("/process-audio")
async def process_audio(file: UploadFile = File(...)):
    try:
        # Read the uploaded file
        audio_data = await file.read()
        logger.info(f"Received audio file: {len(audio_data)} bytes")
        
        # Convert to proper WAV format for Whisper
        audio = AudioSegment.from_file(io.BytesIO(audio_data))
        
        # Whisper requirements: 16kHz, mono, 16-bit PCM WAV
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)  # 16-bit
        
        # Export to WAV bytes
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        wav_data = buffer.getvalue()
        
        logger.info(f"Converted to WAV: {len(wav_data)} bytes")
        
        # Process through pipeline
        transcription = await get_whisper_service().transcribe_audio(wav_data)
        logger.info(f"Transcription: {transcription}")
        
        if not transcription:
            raise HTTPException(status_code=400, detail="No speech detected")
        
        ai_response = await get_qwen_service().generate_response(transcription)
        logger.info(f"AI Response: {ai_response}")
        
        audio_response = await get_tts_service().synthesize_speech(ai_response)
        logger.info(f"TTS Generated: {len(audio_response)} bytes")
        
        return Response(
            content=audio_response,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=response.wav",
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
