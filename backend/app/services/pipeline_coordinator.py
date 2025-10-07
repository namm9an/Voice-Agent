"""
Voice Pipeline Coordinator - Orchestrates ASR → LLM → TTS flow
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Callable

from app.services.metrics_manager import get_metrics_manager, SessionMetricsV2

logger = logging.getLogger(__name__)


@dataclass
class SessionMetrics:
    """Metrics for a single session"""
    session_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    # ASR metrics
    asr_chunks: int = 0
    asr_total_latency: float = 0.0
    asr_final_count: int = 0

    # LLM metrics
    llm_requests: int = 0
    llm_total_tokens: int = 0
    llm_total_latency: float = 0.0

    # TTS metrics
    tts_segments: int = 0
    tts_frames: int = 0
    tts_total_latency: float = 0.0

    # End-to-end metrics
    e2e_latencies: list = field(default_factory=list)  # Speech → AI voice

    def add_e2e_latency(self, latency: float):
        """Add end-to-end latency measurement"""
        self.e2e_latencies.append(latency)

    def get_average_e2e(self) -> float:
        """Get average end-to-end latency"""
        if not self.e2e_latencies:
            return 0.0
        return sum(self.e2e_latencies) / len(self.e2e_latencies)

    def get_summary(self) -> dict:
        """Get metrics summary"""
        duration = (self.end_time or time.time()) - self.start_time
        return {
            "session_id": self.session_id,
            "duration": f"{duration:.2f}s",
            "asr": {
                "chunks": self.asr_chunks,
                "final_count": self.asr_final_count,
                "avg_latency": f"{self.asr_total_latency / max(1, self.asr_chunks):.3f}s"
            },
            "llm": {
                "requests": self.llm_requests,
                "total_tokens": self.llm_total_tokens,
                "avg_latency": f"{self.llm_total_latency / max(1, self.llm_requests):.3f}s"
            },
            "tts": {
                "segments": self.tts_segments,
                "frames": self.tts_frames,
                "avg_latency": f"{self.tts_total_latency / max(1, self.tts_segments):.3f}s"
            },
            "e2e": {
                "measurements": len(self.e2e_latencies),
                "avg_latency": f"{self.get_average_e2e():.3f}s",
                "min_latency": f"{min(self.e2e_latencies):.3f}s" if self.e2e_latencies else "N/A",
                "max_latency": f"{max(self.e2e_latencies):.3f}s" if self.e2e_latencies else "N/A"
            }
        }


@dataclass
class SessionContext:
    """Context for a single voice pipeline session"""
    session_id: str
    tts_queue: asyncio.Queue
    metrics: SessionMetrics

    # State tracking
    last_asr_final_time: Optional[float] = None
    last_llm_start_time: Optional[float] = None
    last_tts_start_time: Optional[float] = None

    # Task management
    tasks: list = field(default_factory=list)
    is_active: bool = True

    # Barge-in tracking
    current_llm_task: Optional[asyncio.Task] = None
    current_tts_consumer_task: Optional[asyncio.Task] = None
    is_agent_speaking: bool = False
    barge_in_count: int = 0


class VoicePipelineCoordinator:
    """
    Coordinates ASR → LLM → TTS pipeline for real-time voice interaction
    """

    def __init__(self):
        self.sessions: dict[str, SessionContext] = {}
        logger.info("[COORDINATOR-INIT] Voice pipeline coordinator initialized")

    def create_session(self, session_id: str) -> SessionContext:
        """Create new session context"""
        # Create context with legacy metrics
        context = SessionContext(
            session_id=session_id,
            tts_queue=asyncio.Queue(),
            metrics=SessionMetrics(session_id=session_id)
        )
        self.sessions[session_id] = context

        # Also create V2 metrics for fine-grained tracking
        metrics_manager = get_metrics_manager()
        metrics_manager.create_session(session_id)

        logger.info(f"[PIPELINE-START] session={session_id}")
        return context

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get existing session context"""
        return self.sessions.get(session_id)

    async def handle_barge_in(self, session_id: str, room_publish_callback: Callable):
        """
        Handle user interruption during AI response

        Args:
            session_id: Session identifier
            room_publish_callback: Callback to publish data to room
        """
        context = self.get_session(session_id)
        if not context or not context.is_active:
            logger.warning(f"[BARGE-IN] No active session for {session_id}")
            return

        logger.warning(f"[BARGE-IN] Detected new user speech for {session_id}")
        context.barge_in_count += 1

        # Stop current TTS consumer
        if context.current_tts_consumer_task and not context.current_tts_consumer_task.done():
            context.current_tts_consumer_task.cancel()
            logger.info(f"[BARGE-IN] Stopped TTS consumer for {session_id}")
            try:
                await context.current_tts_consumer_task
            except asyncio.CancelledError:
                pass

        # Cancel ongoing LLM generation
        if context.current_llm_task and not context.current_llm_task.done():
            context.current_llm_task.cancel()
            logger.info(f"[BARGE-IN] Cancelled LLM response for {session_id}")
            try:
                await context.current_llm_task
            except asyncio.CancelledError:
                pass

        # Flush TTS queue (discard pending audio)
        while not context.tts_queue.empty():
            try:
                context.tts_queue.get_nowait()
                context.tts_queue.task_done()
            except asyncio.QueueEmpty:
                break
        logger.info(f"[BARGE-IN] Flushed TTS queue for {session_id}")

        # Reset speaking state
        context.is_agent_speaking = False

        # Notify frontend that agent was interrupted
        try:
            import json
            message = {
                "type": "agent_interrupted",
                "session_id": session_id
            }
            data = json.dumps(message).encode('utf-8')
            await room_publish_callback(data, reliable=True)
            logger.info(f"[BARGE-IN] Notified frontend of interruption")
        except Exception as e:
            logger.error(f"[BARGE-IN-NOTIFY-ERROR] {e}")

        logger.info(f"[BARGE-IN] Ready for new input from {session_id}")

    async def cleanup_session(self, session_id: str):
        """Clean up session and print metrics"""
        context = self.sessions.get(session_id)
        if not context:
            return

        # Mark as inactive
        context.is_active = False
        context.metrics.end_time = time.time()

        # Cancel all pending tasks
        for task in context.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Print metrics summary (including barge-in count)
        summary = context.metrics.get_summary()
        summary["barge_ins"] = context.barge_in_count
        logger.info(f"[PIPELINE-END] session={session_id}")
        logger.info(f"[PIPELINE-METRICS] {summary}")

        # Finalize V2 metrics
        metrics_manager = get_metrics_manager()
        v2_metrics = metrics_manager.get_session(session_id)
        if v2_metrics:
            v2_metrics.barge_in_count = context.barge_in_count
            metrics_manager.finalize_session(session_id)

        # Remove from active sessions
        del self.sessions[session_id]

    def create_asr_callback(
        self,
        session_id: str,
        room_publish_callback: Callable,
        llm_trigger_callback: Callable
    ):
        """
        Create ASR callback that tracks metrics and triggers LLM

        Args:
            session_id: Session identifier
            room_publish_callback: Callback to publish data to room
            llm_trigger_callback: Callback to trigger LLM generation
        """
        async def on_partial_transcript(text: str, is_final: bool):
            """Handle partial transcript from ASR"""
            context = self.get_session(session_id)
            if not context or not context.is_active:
                return

            try:
                # Update metrics
                context.metrics.asr_chunks += 1

                # Publish to frontend
                import json
                message = {
                    "type": "asr_partial" if not is_final else "asr_final",
                    "text": text,
                    "session_id": session_id
                }
                data = json.dumps(message).encode('utf-8')
                await room_publish_callback(data, reliable=True)
                logger.debug(f"[ASR-EMIT] {message['type']}: \"{text}\"")

                # Trigger LLM on final transcript
                if is_final and text.strip():
                    context.metrics.asr_final_count += 1
                    context.last_asr_final_time = time.time()

                    logger.info(f"[ASR-FINAL] Triggering LLM for: \"{text}\"")

                    # Create LLM task and track it for barge-in
                    llm_task = asyncio.create_task(llm_trigger_callback(text))
                    context.current_llm_task = llm_task
                    context.tasks.append(llm_task)

            except Exception as e:
                logger.error(f"[ASR-CALLBACK-ERROR] {e}")

        return on_partial_transcript

    def create_llm_callbacks(
        self,
        session_id: str,
        room_publish_callback: Callable
    ):
        """
        Create LLM callbacks that track metrics and emit tokens

        Args:
            session_id: Session identifier
            room_publish_callback: Callback to publish data to room
        """
        async def on_llm_token(text: str, is_final: bool):
            """Handle LLM token emission"""
            context = self.get_session(session_id)
            if not context or not context.is_active:
                return

            try:
                # Track start time
                if context.last_llm_start_time is None:
                    context.last_llm_start_time = time.time()

                # Update metrics
                context.metrics.llm_total_tokens += 1

                # Publish to frontend
                import json
                message = {
                    "type": "llm_partial" if not is_final else "llm_final",
                    "text": text,
                    "session_id": session_id
                }
                data = json.dumps(message).encode('utf-8')
                await room_publish_callback(data, reliable=True)
                logger.debug(f"[LLM-EMIT] {message['type']}: \"{text[:50]}...\"")

            except Exception as e:
                logger.error(f"[LLM-CALLBACK-ERROR] {e}")

        async def on_llm_complete(full_text: str):
            """Handle LLM completion and hand off to TTS"""
            context = self.get_session(session_id)
            if not context or not context.is_active:
                return

            try:
                # Calculate LLM latency
                if context.last_llm_start_time:
                    llm_latency = time.time() - context.last_llm_start_time
                    context.metrics.llm_requests += 1
                    context.metrics.llm_total_latency += llm_latency
                    context.last_llm_start_time = None

                # Clear current LLM task reference
                context.current_llm_task = None

                # Mark that agent will start speaking
                context.is_agent_speaking = True

                # Add to TTS queue
                await context.tts_queue.put(full_text)
                logger.info(f"[TTS-QUEUE] Added response: \"{full_text[:50]}...\"")

                # Calculate end-to-end latency (ASR final → TTS queue)
                if context.last_asr_final_time:
                    e2e_latency = time.time() - context.last_asr_final_time
                    context.metrics.add_e2e_latency(e2e_latency)
                    logger.info(f"[E2E-LATENCY] ASR→TTS: {e2e_latency:.3f}s")

            except Exception as e:
                logger.error(f"[LLM-COMPLETE-ERROR] {e}")

        return on_llm_token, on_llm_complete

    def create_tts_callback(
        self,
        session_id: str,
        room_publish_callback: Callable
    ):
        """
        Create TTS callback that tracks metrics and emits audio

        Args:
            session_id: Session identifier
            room_publish_callback: Callback to publish audio to room
        """
        async def on_tts_audio_chunk(frame_data: bytes, segment_num: int, frame_num: int):
            """Handle TTS audio chunk emission"""
            context = self.get_session(session_id)
            if not context or not context.is_active:
                return

            try:
                # Track start time for this segment
                if frame_num == 0:
                    context.last_tts_start_time = time.time()
                    context.metrics.tts_segments += 1

                # Update metrics
                context.metrics.tts_frames += 1

                # Encode and publish audio frame
                import json
                import base64
                audio_b64 = base64.b64encode(frame_data).decode('utf-8')

                message = {
                    "type": "tts_chunk",
                    "audio": audio_b64,
                    "segment": segment_num,
                    "frame": frame_num,
                    "session_id": session_id
                }
                data = json.dumps(message).encode('utf-8')
                await room_publish_callback(data, reliable=False)  # Unreliable for audio

                if frame_num % 25 == 0:
                    logger.debug(f"[TTS-EMIT] segment={segment_num}, frame={frame_num}")

            except Exception as e:
                logger.error(f"[TTS-CALLBACK-ERROR] {e}")

        return on_tts_audio_chunk

    async def run_tts_consumer(
        self,
        session_id: str,
        tts_service
    ):
        """
        Run TTS consumer that processes queue

        Args:
            session_id: Session identifier
            tts_service: StreamingTTS instance
        """
        context = self.get_session(session_id)
        if not context:
            logger.error(f"[TTS-CONSUMER] No context for session {session_id}")
            return

        logger.info(f"[TTS-CONSUMER-START] session={session_id}")

        try:
            while context.is_active:
                # Get text from queue with timeout
                try:
                    text = await asyncio.wait_for(
                        context.tts_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                logger.info(f"[TTS-QUEUE-POP] queue_length={context.tts_queue.qsize()}, text=\"{text[:50]}...\"")

                # Process text into audio chunks
                start_time = time.time()
                await tts_service.process_text(text)

                # Update latency metrics
                tts_latency = time.time() - start_time
                context.metrics.tts_total_latency += tts_latency

                context.tts_queue.task_done()

        except asyncio.CancelledError:
            logger.info(f"[TTS-CONSUMER-STOP] session={session_id}")
        except Exception as e:
            logger.error(f"[TTS-CONSUMER-ERROR] {e}", exc_info=True)


# Global coordinator instance
_coordinator: Optional[VoicePipelineCoordinator] = None


def get_pipeline_coordinator() -> VoicePipelineCoordinator:
    """Get or create global pipeline coordinator"""
    global _coordinator
    if _coordinator is None:
        _coordinator = VoicePipelineCoordinator()
    return _coordinator
