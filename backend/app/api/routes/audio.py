"""
Audio processing routes - /process-audio endpoint with granular error handling
"""
import logging
import hashlib
import time
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response

from app.services.whisper_service import WhisperService
from app.services.qwen_service import QwenService
from app.services.tts_service import TTSService
from app.utils.audio_utils import (
    validate_audio_format,
    convert_to_wav,
    enhance_audio_quality,
    validate_audio_constraints,
    get_audio_info
)
from app.utils.error_handlers import (
    WhisperServiceError,
    QwenServiceError,
    TTSServiceError,
    InvalidAudioFormatError
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize services
whisper_service = WhisperService()
qwen_service = QwenService()
tts_service = TTSService()

# Audio file size limit (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/process-audio")
async def process_audio(audio_file: UploadFile = File(...)):
    request_id = id(audio_file)
    logger.info(f"[{request_id}] Processing audio request - file: {audio_file.filename}")

    t0 = time.time()
    
    # Add overall timeout for the entire request
    try:
        # Wrap the entire processing in a timeout
        result = await asyncio.wait_for(process_audio_internal(audio_file, request_id, t0), timeout=45.0)
        return result
    except asyncio.TimeoutError:
        logger.error(f"[{request_id}] Overall request timed out after 45 seconds")
        raise HTTPException(status_code=504, detail="Request timed out. Please try again with a shorter audio.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def process_audio_internal(audio_file: UploadFile, request_id: int, t0: float):
    try:
        # Read audio file
        audio_data = await audio_file.read()
        file_size = len(audio_data)
        logger.info(f"[{request_id}] Audio file size: {file_size} bytes")

        if file_size > MAX_FILE_SIZE:
            logger.warning(f"[{request_id}] File too large: {file_size} bytes")
            raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")

        # Stage 1: Validation + enhancement
        s1 = time.time()
        try:
            is_valid, error_msg = validate_audio_constraints(audio_data)
            if not is_valid:
                logger.warning(f"[{request_id}] Audio constraint validation failed: {error_msg}")
                raise HTTPException(status_code=400, detail=error_msg)

            audio_info = get_audio_info(audio_data)
            logger.info(f"[{request_id}] Audio info: {audio_info}")

            audio_data = enhance_audio_quality(audio_data)
            logger.info(f"[{request_id}] Audio enhancement completed")
        except HTTPException:
            raise
        except InvalidAudioFormatError as e:
            logger.error(f"[{request_id}] Audio format error: {e}")
            raise HTTPException(status_code=400, detail="Invalid audio format. Please upload WAV, MP3, FLAC, or WebM files")
        except Exception as e:
            logger.error(f"[{request_id}] Audio processing failed: {e}")
            raise HTTPException(status_code=500, detail="Audio processing failed. Please try again with a different file")
        finally:
            logger.info(f"[{request_id}] Stage 1 time: {(time.time()-s1)*1000:.1f} ms")

        # Stage 2: Whisper
        s2 = time.time()
        try:
            transcription = await whisper_service.transcribe_audio(audio_data)
            if not transcription or not transcription.strip():
                logger.warning(f"[{request_id}] Empty transcription received")
                raise HTTPException(status_code=400, detail="No speech detected in audio. Please ensure the audio contains clear speech.")
            logger.info(f"[{request_id}] Transcription completed: '{transcription[:50]}...' ({len(transcription)} chars)")
        except HTTPException:
            raise
        except WhisperServiceError as e:
            emsg = str(e).lower()
            logger.error(f"[{request_id}] Whisper service error: {e}")
            if "timeout" in emsg:
                raise HTTPException(status_code=504, detail="Speech recognition request timed out. Please try again.")
            if "connection" in emsg:
                raise HTTPException(status_code=503, detail="Speech recognition service temporarily unavailable. Please try again.")
            if "authentication" in emsg or "api key" in emsg:
                raise HTTPException(status_code=503, detail="Speech recognition service configuration error. Please contact support.")
            raise HTTPException(status_code=503, detail="Speech recognition failed. Please try with different audio.")
        except Exception as e:
            logger.error(f"[{request_id}] Unexpected Whisper error: {e}")
            raise HTTPException(status_code=500, detail="Speech recognition encountered an unexpected error. Please try again.")
        finally:
            logger.info(f"[{request_id}] Stage 2 time: {(time.time()-s2)*1000:.1f} ms")

        # Stage 3: Qwen
        s3 = time.time()
        try:
            ai_response = await qwen_service.generate_response(transcription)
            if not ai_response or not ai_response.strip():
                logger.warning(f"[{request_id}] Empty AI response received")
                raise HTTPException(status_code=500, detail="AI service returned an empty response. Please try again.")
            logger.info(f"[{request_id}] AI response generated: '{ai_response[:50]}...' ({len(ai_response)} chars)")
        except HTTPException:
            raise
        except QwenServiceError as e:
            emsg = str(e).lower()
            logger.error(f"[{request_id}] Qwen service error: {e}")
            if "timeout" in emsg:
                raise HTTPException(status_code=504, detail="AI service request timed out. Please try again.")
            if "connection" in emsg:
                raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please try again in a moment.")
            if "rate limit" in emsg or "quota" in emsg:
                raise HTTPException(status_code=429, detail="AI service rate limit exceeded. Please wait and try again.")
            if "authentication" in emsg or "api key" in emsg:
                raise HTTPException(status_code=503, detail="AI service configuration error. Please contact support.")
            raise HTTPException(status_code=503, detail="AI service error. Please try again.")
        except Exception as e:
            logger.error(f"[{request_id}] Unexpected Qwen error: {e}")
            raise HTTPException(status_code=500, detail="AI service encountered an unexpected error. Please try again.")
        finally:
            logger.info(f"[{request_id}] Stage 3 time: {(time.time()-s3)*1000:.1f} ms")

        # Stage 4: TTS
        s4 = time.time()
        try:
            response_audio = await tts_service.synthesize_speech(ai_response)
            if not response_audio or len(response_audio) < 1000:
                logger.warning(f"[{request_id}] TTS returned insufficient audio data: {len(response_audio) if response_audio else 0} bytes")
                raise HTTPException(status_code=500, detail="Audio generation failed to produce valid output. Please try again.")
            logger.info(f"[{request_id}] TTS synthesis completed successfully: {len(response_audio)} bytes")
        except HTTPException:
            raise
        except TTSServiceError as e:
            emsg = str(e).lower()
            logger.error(f"[{request_id}] TTS service error: {e}")
            if "timeout" in emsg:
                raise HTTPException(status_code=504, detail="Speech synthesis request timed out. Please try again.")
            if "connection" in emsg:
                raise HTTPException(status_code=503, detail="Speech synthesis service temporarily unavailable. Please try again.")
            if "text too long" in emsg or "length" in emsg:
                raise HTTPException(status_code=400, detail="AI response too long for speech synthesis. Please try a shorter request.")
            if "authentication" in emsg or "api key" in emsg:
                raise HTTPException(status_code=503, detail="Speech synthesis service configuration error. Please contact support.")
            raise HTTPException(status_code=503, detail="Speech synthesis failed. Please try again.")
        except Exception as e:
            logger.error(f"[{request_id}] Unexpected TTS error: {e}")
            raise HTTPException(status_code=500, detail="Speech synthesis encountered an unexpected error. Please try again.")
        finally:
            logger.info(f"[{request_id}] Stage 4 time: {(time.time()-s4)*1000:.1f} ms")

        # Stage 5: Response
        s5 = time.time()
        try:
            final_audio_info = get_audio_info(response_audio)
            etag = hashlib.sha256(response_audio).hexdigest()
            headers = {
                "Content-Disposition": "attachment; filename=response.wav",
                "X-Audio-Duration": str(final_audio_info.get("duration_seconds", 0)),
                "X-Audio-Size": str(len(response_audio)),
                "X-Request-ID": str(request_id),
                "ETag": etag,
                "Cache-Control": "no-cache, no-store, must-revalidate",
            }
            return Response(content=response_audio, media_type="audio/wav", headers=headers)
        except Exception as e:
            logger.error(f"[{request_id}] Failed to prepare response: {e}")
            raise HTTPException(status_code=500, detail="Failed to prepare audio response. Please try again.")
        finally:
            logger.info(f"[{request_id}] Stage 5 time: {(time.time()-s5)*1000:.1f} ms")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        logger.info(f"[{request_id}] Total request time: {(time.time()-t0)*1000:.1f} ms")