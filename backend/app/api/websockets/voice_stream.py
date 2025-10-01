"""
WebSocket handler for real-time voice streaming
Provides bidirectional audio streaming for low-latency voice interaction
"""
import logging
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import base64

from app.services.whisper_service import WhisperService
from app.services.qwen_service import QwenService
from app.services.tts_service import TTSService
from app.services.vad_service import get_vad_service

logger = logging.getLogger(__name__)


class VoiceStreamHandler:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.whisper_service: Optional[WhisperService] = None
        self.qwen_service: Optional[QwenService] = None
        self.tts_service: Optional[TTSService] = None
        self.vad_service = None

    def _get_services(self):
        """Lazy initialization of services"""
        if not self.whisper_service:
            self.whisper_service = WhisperService()
        if not self.qwen_service:
            self.qwen_service = QwenService()
        if not self.tts_service:
            self.tts_service = TTSService()
        if not self.vad_service:
            self.vad_service = get_vad_service()

    async def handle_connection(self, websocket: WebSocket, session_id: str = "default"):
        """
        Handle WebSocket connection for real-time voice streaming

        Protocol:
        - Client sends: {"type": "audio", "data": "<base64_audio>"}
        - Server sends: {"type": "transcription", "text": "..."}
        - Server sends: {"type": "response", "text": "..."}
        - Server sends: {"type": "audio", "data": "<base64_audio>"}
        - Server sends: {"type": "error", "message": "..."}
        """
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: session={session_id}")

        # Initialize services
        self._get_services()

        try:
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "message": "WebSocket connection established"
            })

            # Main message loop
            while True:
                # Receive message from client
                try:
                    message = await websocket.receive_json()
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid JSON format"
                    })
                    continue

                message_type = message.get("type")

                if message_type == "audio":
                    # Process audio data
                    await self._process_audio(websocket, message, session_id)

                elif message_type == "ping":
                    # Respond to ping
                    await websocket.send_json({"type": "pong"})

                elif message_type == "clear_history":
                    # Clear conversation history
                    if session_id in self.qwen_service.sessions:
                        del self.qwen_service.sessions[session_id]
                    await websocket.send_json({
                        "type": "history_cleared",
                        "message": "Conversation history cleared"
                    })

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {message_type}"
                    })

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: session={session_id}")
            if session_id in self.active_connections:
                del self.active_connections[session_id]

        except Exception as e:
            logger.error(f"WebSocket error for session {session_id}: {e}", exc_info=True)
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Server error: {str(e)}"
                })
            except:
                pass
            if session_id in self.active_connections:
                del self.active_connections[session_id]

    async def _process_audio(self, websocket: WebSocket, message: dict, session_id: str):
        """
        Process audio data received from client

        Args:
            websocket: WebSocket connection
            message: Message containing base64-encoded audio data
            session_id: Session identifier
        """
        try:
            # Extract audio data
            audio_b64 = message.get("data")
            if not audio_b64:
                await websocket.send_json({
                    "type": "error",
                    "message": "No audio data provided"
                })
                return

            # Decode base64 audio
            audio_data = base64.b64decode(audio_b64)
            logger.info(f"[WS-{session_id}] Received {len(audio_data)} bytes of audio")

            # Step 1: Check for speech using VAD
            has_speech = self.vad_service.has_speech(audio_data, min_speech_duration_ms=300)
            if not has_speech:
                logger.warning(f"[WS-{session_id}] No speech detected")
                await websocket.send_json({
                    "type": "error",
                    "message": "No speech detected in audio"
                })
                return

            # Step 2: Extract speech segments
            speech_audio = self.vad_service.extract_speech_audio(audio_data, padding_ms=300)
            if not speech_audio:
                speech_audio = audio_data

            # Step 3: Transcribe
            transcription = await self.whisper_service.transcribe_audio(speech_audio)
            if not transcription:
                await websocket.send_json({
                    "type": "error",
                    "message": "Failed to transcribe audio"
                })
                return

            logger.info(f"[WS-{session_id}] Transcription: {transcription}")

            # Send transcription to client
            await websocket.send_json({
                "type": "transcription",
                "text": transcription
            })

            # Step 4: Generate AI response
            ai_response = await self.qwen_service.generate_response(transcription, session_id=session_id)
            logger.info(f"[WS-{session_id}] AI Response: {ai_response}")

            # Send AI response to client
            await websocket.send_json({
                "type": "response",
                "text": ai_response
            })

            # Step 5: Generate speech
            audio_response = await self.tts_service.synthesize_speech(ai_response, session_id=session_id)
            logger.info(f"[WS-{session_id}] TTS Generated: {len(audio_response)} bytes")

            # Send audio response to client (base64 encoded)
            audio_b64 = base64.b64encode(audio_response).decode('utf-8')
            await websocket.send_json({
                "type": "audio",
                "data": audio_b64,
                "format": "wav"
            })

            logger.info(f"[WS-{session_id}] Processing complete")

        except Exception as e:
            logger.error(f"[WS-{session_id}] Error processing audio: {e}", exc_info=True)
            await websocket.send_json({
                "type": "error",
                "message": f"Processing error: {str(e)}"
            })


# Global handler instance
_voice_stream_handler: Optional[VoiceStreamHandler] = None


def get_voice_stream_handler() -> VoiceStreamHandler:
    """Get or create global VoiceStreamHandler instance"""
    global _voice_stream_handler
    if _voice_stream_handler is None:
        _voice_stream_handler = VoiceStreamHandler()
    return _voice_stream_handler