"""
Streaming LLM service - generates Phi-3.5 responses token-by-token
"""
import asyncio
import logging
import time
from typing import AsyncIterator, Callable, Optional
import aiohttp
import json

from app.config.settings import get_settings
from app.utils.error_handlers import QwenServiceError

logger = logging.getLogger(__name__)


class StreamingLLM:
    """Streams Phi-3.5 tokens in real-time"""

    def __init__(self, session_id: str, on_token: Callable, on_complete: Callable):
        self.session_id = session_id
        self.on_token = on_token  # Callback for each token
        self.on_complete = on_complete  # Callback when stream completes
        self.settings = get_settings()

        # Conversation history (session-based)
        self.conversation_history = []
        self.max_history = 10

        # HTTP session
        self.http_session: Optional[aiohttp.ClientSession] = None

        # Stats
        self.token_count = 0
        self.start_time = 0

        logger.info(f"[LLM-INIT] session={session_id}")

    async def start(self):
        """Initialize HTTP session"""
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        connector = aiohttp.TCPConnector(
            limit=5,
            limit_per_host=3,
            keepalive_timeout=30
        )
        self.http_session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        logger.info(f"[LLM-START] session={self.session_id}")

    async def stop(self):
        """Close HTTP session"""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        logger.info(f"[LLM-STOP] session={self.session_id}, tokens={self.token_count}")

    async def generate_streaming_response(self, user_text: str) -> str:
        """
        Generate streaming LLM response

        Args:
            user_text: User's transcribed speech

        Returns:
            Complete response text
        """
        if not user_text or not user_text.strip():
            logger.warning(f"[LLM] Empty user text for session {self.session_id}")
            return ""

        self.start_time = time.time()
        self.token_count = 0
        accumulated_text = ""

        try:
            # Build messages with history
            messages = self._build_messages(user_text)

            logger.info(f"[LLM-START] session={self.session_id}, prompt='{user_text}'")

            # Stream tokens from Phi-3.5
            async for token in self._stream_phi(messages):
                self.token_count += 1
                accumulated_text += token

                # Emit token to frontend
                await self.on_token(accumulated_text, is_final=False)

                # Log every 5th token
                if self.token_count % 5 == 0:
                    elapsed = time.time() - self.start_time
                    logger.info(
                        f"[LLM-TOKEN] chunk {self.token_count} → \"{accumulated_text[:50]}...\" "
                        f"({elapsed:.2f}s)"
                    )

            # Update conversation history
            self.conversation_history.append({"role": "user", "content": user_text})
            self.conversation_history.append({"role": "assistant", "content": accumulated_text})

            # Keep only recent history
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history * 2:]

            elapsed = time.time() - self.start_time
            logger.info(
                f"[LLM-FINAL] session={self.session_id}, "
                f"tokens={self.token_count}, "
                f"time={elapsed:.2f}s, "
                f"response=\"{accumulated_text}\""
            )

            # Notify completion
            await self.on_complete(accumulated_text)

            return accumulated_text

        except Exception as e:
            logger.error(f"[LLM-ERROR] session={self.session_id}: {e}", exc_info=True)
            # Return partial response if we got something
            if accumulated_text:
                await self.on_complete(accumulated_text)
                return accumulated_text
            raise

    def _build_messages(self, user_text: str) -> list:
        """Build message array with conversation history"""
        messages = [
            {
                "role": "system",
                "content": "You are a helpful AI assistant in a voice conversation. "
                           "Keep responses concise and conversational (2-3 sentences max). "
                           "Remember previous context."
            }
        ]

        # Add conversation history
        messages.extend(self.conversation_history)

        # Add current user message
        messages.append({"role": "user", "content": user_text})

        return messages

    async def _stream_phi(self, messages: list) -> AsyncIterator[str]:
        """
        Stream tokens from Phi-3.5 via OpenAI-compatible API

        Args:
            messages: Conversation messages

        Yields:
            Token strings
        """
        if not self.http_session:
            raise QwenServiceError("HTTP session not initialized")

        url = f"{self.settings.llm_base_url}chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.7,
            "stream": True  # Enable streaming
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with self.http_session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise QwenServiceError(f"LLM API error {response.status}: {error_text}")

                    # Read streaming response line by line
                    async for line in response.content:
                        line = line.decode('utf-8').strip()

                        # Skip empty lines
                        if not line:
                            continue

                        # Parse SSE format: "data: {...}"
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix

                            # Check for stream end
                            if data == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data)

                                # Extract token from delta
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})
                                    token = delta.get("content", "")

                                    if token:
                                        yield token

                            except json.JSONDecodeError:
                                logger.warning(f"[LLM] Failed to parse chunk: {data[:100]}")
                                continue

                    # Successfully completed
                    break

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_retries:
                    logger.warning(f"[LLM-RETRY] attempt {attempt + 1}: {e}")
                    await asyncio.sleep(0.2)
                else:
                    logger.error(f"[LLM-FAILED] after {max_retries + 1} attempts: {e}")
                    raise QwenServiceError(f"LLM streaming failed: {e}")
