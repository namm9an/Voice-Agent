"""
Qwen model endpoint integration service (OpenAI-compatible client)
"""

import logging
import os
import asyncio
from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.utils.error_handlers import QwenServiceError

logger = logging.getLogger(__name__)


class QwenService:
    def __init__(self):
        self.settings = get_settings()
        api_key = self.settings.qwen_api_key or os.getenv("QWEN_API_KEY")
        base_url = self.settings.qwen_base_url or os.getenv("QWEN_BASE_URL") or None
        if not api_key or not base_url:
            logger.warning("Qwen service not fully configured (missing base URL or API key)")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        # Session-based conversation memory - each session has its own history
        self.sessions = {}  # session_id -> conversation_history
        self.max_history = 10  # Keep last 10 exchanges

    async def generate_response(self, text: str, session_id: str = "default") -> str:
        if not text or not text.strip():
            raise QwenServiceError("Empty prompt provided to Qwen")

        try:
            # Get or create session-specific conversation history
            if session_id not in self.sessions:
                self.sessions[session_id] = []

            conversation_history = self.sessions[session_id]

            # Build messages with conversation history
            messages = []

            # Add system message for context
            messages.append({
                "role": "system",
                "content": "You are a helpful AI assistant. You can remember our previous conversation and provide contextual responses. Keep responses concise and natural for voice interaction."
            })

            # Add conversation history
            messages.extend(conversation_history)

            # Add current user message
            messages.append({"role": "user", "content": text})

            response = await asyncio.wait_for(self.client.chat.completions.create(
                model=self.settings.qwen_model,
                messages=messages,
                temperature=0.7,
            ), timeout=15)

            if not response.choices:
                raise QwenServiceError("Empty choices from Qwen")

            content = response.choices[0].message.content
            if not content:
                raise QwenServiceError("Empty content from Qwen response")

            # Add to session-specific conversation history
            conversation_history.append({"role": "user", "content": text})
            conversation_history.append({"role": "assistant", "content": content.strip()})

            # Keep only recent history
            if len(conversation_history) > self.max_history * 2:  # *2 because we store user+assistant pairs
                self.sessions[session_id] = conversation_history[-self.max_history * 2:]

            return content.strip()

        except asyncio.TimeoutError:
            logger.error("Qwen request timed out after 15 seconds")
            raise QwenServiceError("AI response timeout")
        except Exception as e:
            logger.error(f"Qwen request failed: {e}")
            msg = str(e).lower()
            if "rate limit" in msg or "429" in msg:
                raise QwenServiceError("Rate limit exceeded")
            if isinstance(e, QwenServiceError):
                raise
            raise QwenServiceError(str(e))