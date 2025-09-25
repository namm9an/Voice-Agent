"""
Whisper (E2E OpenAI-compatible) integration service
"""
import io
import logging
import asyncio
import tempfile
import os
from openai import AsyncOpenAI
from app.config.settings import get_settings
from app.utils.error_handlers import WhisperServiceError

logger = logging.getLogger(__name__)


class WhisperService:
    def __init__(self):
        self.settings = get_settings()
        # Use E2E OpenAI-compatible endpoint and key
        self.client = AsyncOpenAI(
            api_key=self.settings.whisper_api_key or self.settings.openai_api_key,
            base_url=self.settings.whisper_base_url or None,
        )

    async def transcribe_audio(self, audio_data: bytes) -> str:
        """
        Single attempt transcription with timeout to prevent infinite loops
        """
        try:
            logger.info(f"Starting Whisper transcription, audio size: {len(audio_data)} bytes")

            if len(audio_data) < 1000:
                raise WhisperServiceError("Audio data too small for transcription")

            # Add timeout and single attempt first
            client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            
            # Save audio to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp.write(audio_data)
                tmp.flush()
                
                # Single transcription attempt with timeout
                with open(tmp.name, 'rb') as audio_file:
                    response = await asyncio.wait_for(
                        client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file
                        ),
                        timeout=10  # 10 second max timeout for faster failure
                    )
                
                os.unlink(tmp.name)
                return response.text
                
        except asyncio.TimeoutError:
            logger.error("Whisper transcription timed out")
            raise WhisperServiceError("Transcription timed out after 10 seconds")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise WhisperServiceError(f"Transcription failed: {str(e)}")