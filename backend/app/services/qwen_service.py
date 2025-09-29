"""
Qwen model endpoint integration service (OpenAI-compatible client)
"""

import logging
import os
import asyncio
from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.utils.error_handlers import QwenServiceError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

logger = logging.getLogger(__name__)


class QwenService:
    def __init__(self):
        self.settings = get_settings()
        api_key = self.settings.qwen_api_key or os.getenv("QWEN_API_KEY")
        base_url = self.settings.qwen_base_url or os.getenv("QWEN_BASE_URL") or None
        if not api_key or not base_url:
            logger.warning("Qwen service not fully configured (missing base URL or API key)")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        
        # Conversation memory
        self.conversation_history = []
        self.max_history = 10  # Keep last 10 exchanges

    async def generate_response(self, text: str) -> str:
        if not text or not text.strip():
            raise QwenServiceError("Empty prompt provided to Qwen")

        @retry(
            reraise=True,
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        async def attempt_chat() -> str:
            try:
                # Build messages with conversation history
                messages = []
                
                # Add system message for context
                messages.append({
                    "role": "system", 
                    "content": "You are a helpful AI assistant. You can remember our previous conversation and provide contextual responses. Keep responses concise and natural for voice interaction."
                })
                
                # Add conversation history
                messages.extend(self.conversation_history)
                
                # Add current user message
                messages.append({"role": "user", "content": text})
                
                response = await asyncio.wait_for(self.client.chat.completions.create(
                    model=self.settings.qwen_model,
                    messages=messages,
                    temperature=0.7,
                ), timeout=10)

                if not response.choices:
                    raise QwenServiceError("Empty choices from Qwen")

                content = response.choices[0].message.content
                if not content:
                    raise QwenServiceError("Empty content from Qwen response")
                
                # Add to conversation history
                self.conversation_history.append({"role": "user", "content": text})
                self.conversation_history.append({"role": "assistant", "content": content.strip()})
                
                # Keep only recent history
                if len(self.conversation_history) > self.max_history * 2:  # *2 because we store user+assistant pairs
                    self.conversation_history = self.conversation_history[-self.max_history * 2:]
                
                return content.strip()
            except Exception as e:
                # Bubble up for retry classification
                msg = str(e).lower()
                if "rate limit" in msg or "429" in msg:
                    raise QwenServiceError("rate limit")
                raise

        try:
            return await attempt_chat()
        except Exception as e:
            logger.error(f"Qwen request failed: {e}")
            if isinstance(e, QwenServiceError):
                raise
            raise QwenServiceError(str(e))