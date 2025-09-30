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
        # 20s timeout for Whisper Turbo (faster than v3-large but still remote)
        self.timeout = aiohttp.ClientTimeout(total=20)
        self._session: Optional[aiohttp.ClientSession] = None

        if not self.api_key:
            raise WhisperServiceError("Whisper/OpenAI API key not configured")
        if not self.base_url:
            raise WhisperServiceError("Whisper base URL not configured")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create reusable HTTP session with optimized connector"""
        if self._session is None or self._session.closed:
            # Use TCP connector with connection pooling for better performance
            connector = aiohttp.TCPConnector(
                limit=10,  # Max 10 concurrent connections
                limit_per_host=5,  # Max 5 per host
                ttl_dns_cache=300,  # Cache DNS for 5 minutes
                keepalive_timeout=30  # Keep connections alive for reuse
            )
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector
            )
        return self._session

    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def transcribe_audio(self, audio_data: bytes) -> str:
        """Transcribe audio using E2E Whisper API"""
        import time
        start_time = time.time()

        # Log audio info
        logger.info(f"Sending {len(audio_data)} bytes to Whisper at {self.base_url}")
        
        # Create form data
        form = aiohttp.FormData()
        form.add_field('file',
                      audio_data,
                      filename='audio.wav',
                      content_type='audio/wav')
        # Add model parameter for Whisper Turbo
        form.add_field('model', self.settings.whisper_model)

        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }

        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}audio/transcriptions",
                data=form,
                headers=headers
            ) as response:
                elapsed = time.time() - start_time
                if response.status == 200:
                    result = await response.json()
                    text = result.get('text', '').strip()
                    logger.info(f"Transcription received in {elapsed:.2f}s: {text}")
                    return text
                else:
                    error_text = await response.text()
                    logger.error(f"Whisper API error {response.status} after {elapsed:.2f}s: {error_text}")
                    raise WhisperServiceError(f"Whisper API error: {response.status}")

        except asyncio.TimeoutError:
            logger.error("Whisper Turbo API timeout after 20 seconds")
            raise WhisperServiceError("Transcription timeout - service may be slow or overloaded")
        except Exception as e:
            logger.error(f"Whisper API error: {str(e)}")
            raise WhisperServiceError(f"Transcription failed: {str(e)}")