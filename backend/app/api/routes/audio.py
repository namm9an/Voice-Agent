"""
Audio processing routes - /process-audio endpoint
"""
from fastapi import APIRouter

router = APIRouter()

@router.post("/process-audio")
async def process_audio():
    # TODO: Implement in Phase 2
    raise NotImplementedError("Phase 2")