"""
Whisper (E2E OpenAI-compatible) integration service
"""
import asyncio
import aiohttp
import logging
import base64
from typing import Optional
from app.config.settings import get_settings
from app.utils.error_handlers import WhisperServiceError

logger = logging.getLogger(__name__)

class WhisperService:
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.whisper_api_key or self.settings.openai_api_key
        self.base_url = self.settings.whisper_base_url
        self.timeout = aiohttp.ClientTimeout(total=30)
        
        if not self.api_key:
            raise WhisperServiceError("Whisper/OpenAI API key not configured")
        if not self.base_url:
            raise WhisperServiceError("Whisper base URL not configured")
    
    async def transcribe_audio(self, audio_data: bytes) -> str:
        """Transcribe audio using E2E Whisper API"""
        
        # Log audio info
        logger.info(f"Sending {len(audio_data)} bytes to Whisper")
        
        # Create form data
        form = aiohttp.FormData()
        form.add_field('file', 
                      audio_data,
                      filename='audio.wav',
                      content_type='audio/wav')
        
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.post(
                    f"{self.base_url}audio/transcriptions",
                    data=form,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('text', '').strip()
                        logger.info(f"Transcription received: {text}")
                        return text
                    else:
                        error_text = await response.text()
                        logger.error(f"Whisper API error {response.status}: {error_text}")
                        raise WhisperServiceError(f"Whisper API error: {response.status}")
                        
            except asyncio.TimeoutError:
                logger.error("Whisper API timeout after 30 seconds")
                raise WhisperServiceError("Transcription timeout - audio may be too long")
            except Exception as e:
                logger.error(f"Whisper API error: {str(e)}")
                raise WhisperServiceError(f"Transcription failed: {str(e)}")