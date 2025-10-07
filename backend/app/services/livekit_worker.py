"""
LiveKit Worker - Background service that joins rooms as an agent participant
"""
import asyncio
import logging
from livekit import rtc, api
from app.config.settings import get_settings
from app.api.livekit_room_handler import get_room_handler

logger = logging.getLogger(__name__)


class LiveKitWorker:
    """Background worker that connects to LiveKit rooms as voice agent"""

    def __init__(self):
        self.settings = get_settings()
        self.room_handler = get_room_handler()
        self.active_rooms = {}
        self.running = False

    async def start(self):
        """Start the LiveKit worker"""
        self.running = True
        logger.info("LiveKit worker started - listening for room connections")

        # This worker will be triggered when new tokens are created
        # For now, it's a stub that will be called from the token endpoint

    async def stop(self):
        """Stop the LiveKit worker"""
        self.running = False
        # Disconnect from all active rooms
        for room_name, room in list(self.active_rooms.items()):
            await self._leave_room(room_name)
        logger.info("LiveKit worker stopped")

    async def join_room(self, room_name: str):
        """
        Join a LiveKit room as the voice agent

        Args:
            room_name: Name of the room to join
        """
        if room_name in self.active_rooms:
            logger.warning(f"Already in room: {room_name}")
            return

        try:
            logger.info(f"Agent joining room: {room_name}")

            # Create agent token
            token_gen = api.AccessToken(
                self.settings.livekit_api_key,
                self.settings.livekit_api_secret
            )
            token_gen.with_identity(f"agent_{room_name}").with_name("Voice Agent").with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            agent_token = token_gen.to_jwt()

            # Connect to room
            room = rtc.Room()

            # Set up event handlers
            @room.on("participant_connected")
            def on_participant_connected(participant: rtc.RemoteParticipant):
                logger.info(
                    f"Participant connected: {participant.identity} in room {room_name}"
                )

            @room.on("track_subscribed")
            def on_track_subscribed(
                track: rtc.Track,
                publication: rtc.RemoteTrackPublication,
                participant: rtc.RemoteParticipant,
            ):
                logger.info(f"Track subscribed: {track.kind} from {participant.identity}")
                if track.kind == rtc.TrackKind.KIND_AUDIO:
                    # Start processing audio from this participant
                    asyncio.create_task(
                        self._process_participant_audio(room, track, participant)
                    )

            @room.on("track_unsubscribed")
            def on_track_unsubscribed(
                track: rtc.Track,
                publication: rtc.RemoteTrackPublication,
                participant: rtc.RemoteParticipant,
            ):
                logger.info(f"Track unsubscribed: {track.kind} from {participant.identity}")

            @room.on("participant_disconnected")
            def on_participant_disconnected(participant: rtc.RemoteParticipant):
                logger.info(f"Participant disconnected: {participant.identity}")

            @room.on("data_received")
            def on_data_received(data: bytes, participant: rtc.RemoteParticipant):
                """Handle data messages from participants (including barge-in)"""
                try:
                    import json
                    message = json.loads(data.decode('utf-8'))

                    if message.get("type") == "barge_in":
                        session_id = f"livekit_{participant.identity}"
                        logger.info(f"[DATA-RX] Barge-in signal from {session_id}")

                        # Handle barge-in asynchronously
                        from app.services.pipeline_coordinator import get_pipeline_coordinator
                        coordinator = get_pipeline_coordinator()

                        # Create room publish callback
                        async def room_publish_callback(data: bytes, reliable: bool = True):
                            await room.local_participant.publish_data(data, reliable=reliable)

                        asyncio.create_task(
                            coordinator.handle_barge_in(session_id, room_publish_callback)
                        )
                except Exception as e:
                    logger.error(f"[DATA-RX-ERROR] Failed to process data: {e}")

            # Connect to the room
            await room.connect(self.settings.livekit_url, agent_token)
            logger.info(f"Agent connected to room: {room_name}")

            self.active_rooms[room_name] = room

        except Exception as e:
            logger.error(f"Failed to join room {room_name}: {e}", exc_info=True)
            raise

    async def _process_participant_audio(
        self,
        room: rtc.Room,
        track: rtc.Track,
        participant: rtc.RemoteParticipant
    ):
        """
        Process audio from a participant using streaming ASR

        Args:
            room: LiveKit room
            track: Audio track
            participant: Remote participant
        """
        from app.services.streaming_asr import StreamingASR
        from app.services.streaming_llm import StreamingLLM
        from app.services.streaming_tts import StreamingTTS
        from app.services.pipeline_coordinator import get_pipeline_coordinator

        session_id = f"livekit_{participant.identity}"
        logger.info(f"[STREAM-START] Processing audio for session: {session_id}")

        # Initialize pipeline coordinator
        coordinator = get_pipeline_coordinator()
        context = coordinator.create_session(session_id)

        # Room publish callback (used by coordinator)
        async def room_publish_callback(data: bytes, reliable: bool = True):
            """Publish data to room"""
            await room.local_participant.publish_data(data, reliable=reliable)

        # Create TTS callback via coordinator
        on_tts_audio_chunk = coordinator.create_tts_callback(
            session_id,
            room_publish_callback
        )

        # Initialize streaming TTS
        streaming_tts = StreamingTTS(session_id, on_tts_audio_chunk)
        await streaming_tts.start()

        # Start TTS consumer task via coordinator
        tts_consumer_task = asyncio.create_task(
            coordinator.run_tts_consumer(session_id, streaming_tts)
        )
        context.tasks.append(tts_consumer_task)
        context.current_tts_consumer_task = tts_consumer_task

        # Create LLM callbacks via coordinator
        on_llm_token, on_llm_complete = coordinator.create_llm_callbacks(
            session_id,
            room_publish_callback
        )

        # Initialize streaming LLM
        streaming_llm = StreamingLLM(session_id, on_llm_token, on_llm_complete)
        await streaming_llm.start()

        # Create ASR callback via coordinator
        on_partial_transcript = coordinator.create_asr_callback(
            session_id,
            room_publish_callback,
            streaming_llm.generate_streaming_response
        )

        # Create streaming ASR instance
        streaming_asr = StreamingASR(session_id, on_partial_transcript)
        await streaming_asr.start()

        frame_count = 0

        try:
            audio_stream = rtc.AudioStream(track)
            async for frame in audio_stream:
                frame_count += 1

                # Log every 50th frame to verify streaming
                if frame_count % 50 == 0:
                    logger.info(
                        f"[STREAM-RX] Session={session_id}, "
                        f"Frame={frame_count}, "
                        f"Samples={frame.samples_per_channel}, "
                        f"Rate={frame.sample_rate}Hz"
                    )

                # Push frame to streaming ASR
                await streaming_asr.push_frame(frame.data.tobytes())

        except asyncio.CancelledError:
            logger.info(f"[STREAM-CANCELLED] session={session_id}")
        except Exception as e:
            logger.error(f"[STREAM-ERROR] Error processing audio: {e}", exc_info=True)
        finally:
            # Stop services
            await streaming_asr.flush_buffer()
            await streaming_asr.stop()
            await streaming_llm.stop()
            await streaming_tts.stop()

            # Cleanup session via coordinator (handles metrics and task cancellation)
            await coordinator.cleanup_session(session_id)

            logger.info(f"[STREAM-END] session={session_id}, frames={frame_count}")

    async def _leave_room(self, room_name: str):
        """Leave a LiveKit room"""
        if room_name in self.active_rooms:
            room = self.active_rooms[room_name]
            await room.disconnect()
            del self.active_rooms[room_name]
            logger.info(f"Agent left room: {room_name}")


# Global worker instance
_worker: LiveKitWorker = None


def get_livekit_worker() -> LiveKitWorker:
    """Get or create global LiveKit worker instance"""
    global _worker
    if _worker is None:
        _worker = LiveKitWorker()
    return _worker
