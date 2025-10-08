"""
LiveKit token generation and room management endpoints
"""
import logging
import uuid
import asyncio
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from livekit import api

from app.config.settings import get_settings
from app.services.livekit_worker import get_livekit_worker

logger = logging.getLogger(__name__)
router = APIRouter(tags=["livekit"])


class TokenRequest(BaseModel):
    room_name: Optional[str] = None
    participant_name: Optional[str] = None


class TokenResponse(BaseModel):
    token: str
    url: str
    room_name: str


@router.post("/create-token", response_model=TokenResponse)
async def create_livekit_token(
    request: TokenRequest,
    background_tasks: BackgroundTasks
):
    """
    Create LiveKit access token for client connection
    Also starts the agent in the room

    Args:
        request: Token request with optional room name and participant name
        background_tasks: FastAPI background tasks

    Returns:
        Token, LiveKit URL, and room name
    """
    try:
        settings = get_settings()

        # Generate room name and participant name if not provided
        room_name = request.room_name or f"voice-room-{uuid.uuid4().hex[:8]}"
        participant_name = request.participant_name or f"user-{uuid.uuid4().hex[:6]}"

        # Create access token
        token = api.AccessToken(
            settings.livekit_api_key,
            settings.livekit_api_secret
        )

        # Set token identity and permissions
        token.with_identity(participant_name).with_name(participant_name).with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )

        # Generate JWT token
        jwt_token = token.to_jwt()

        logger.info(
            f"Created LiveKit token for room='{room_name}', participant='{participant_name}'"
        )

        # Start agent in the room (background task)
        worker = get_livekit_worker()
        background_tasks.add_task(worker.join_room, room_name)
        logger.info(f"Scheduled agent to join room: {room_name}")

        return TokenResponse(
            token=jwt_token,
            url=settings.livekit_url,
            room_name=room_name
        )

    except Exception as e:
        logger.error(f"Failed to create LiveKit token: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create token: {str(e)}"
        )


@router.get("/config")
async def get_livekit_config():
    """
    Get LiveKit server configuration (URL only, no secrets)
    """
    try:
        settings = get_settings()
        return {
            "url": settings.livekit_url,
            "configured": True
        }
    except Exception as e:
        logger.error(f"Failed to get config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get config: {str(e)}"
        )


@router.post("/test-stream")
async def test_livekit_stream(background_tasks: BackgroundTasks):
    """
    Test endpoint - creates a room and plays a test tone
    Use this to verify bidirectional audio streaming works

    Returns room name and token for frontend to join
    """
    try:
        from app.utils.audio_test import generate_test_tone

        settings = get_settings()
        room_name = f"test-{uuid.uuid4().hex[:6]}"

        # Create user token
        token = api.AccessToken(
            settings.livekit_api_key,
            settings.livekit_api_secret
        )
        token.with_identity("test-user").with_name("Test User").with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        user_token = token.to_jwt()

        # Schedule agent to join and play test tone
        async def play_test_tone():
            await asyncio.sleep(2)  # Wait for user to join
            worker = get_livekit_worker()
            await worker.join_room(room_name)

            # Get room and play test tone
            if room_name in worker.active_rooms:
                room = worker.active_rooms[room_name]
                test_audio = generate_test_tone(frequency=440, duration_seconds=2.0)

                from app.api.livekit_room_handler import get_room_handler
                handler = get_room_handler()
                await handler._publish_audio(room, test_audio)

                logger.info(f"[TEST] Played test tone in room: {room_name}")

        background_tasks.add_task(play_test_tone)

        return {
            "room_name": room_name,
            "token": user_token,
            "url": settings.livekit_url,
            "message": "Join this room to hear a 440Hz test tone"
        }

    except Exception as e:
        logger.error(f"Test stream failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Test failed: {str(e)}"
        )
