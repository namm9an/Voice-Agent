"""
FastAPI application entry point with CORS, basic routes, and WebSocket endpoint
"""
from fastapi import FastAPI, Request, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from app.api.routes.audio import router as audio_router
from app.api.routes.health import router as health_router
from app.api.websockets.voice_stream import get_voice_stream_handler
from app.utils.logger import setup_logging
from typing import Optional
import time

setup_logging()
app = FastAPI(title="Voice Agent Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Simple timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    response.headers["X-Process-Time-ms"] = str(duration_ms)
    return response

@app.get("/")
async def root():
    return {"message": "Voice Agent Backend API"}

# Plain health endpoint at /health (in addition to versioned route)
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Include API routers (Phase 1 wiring only)
app.include_router(health_router, prefix="/api/v1")
app.include_router(audio_router, prefix="/api/v1")

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time voice streaming

    Query params:
        session_id: Optional session identifier for conversation context

    Usage:
        ws://localhost:8000/ws?session_id=my-session
    """
    # Generate session ID if not provided
    if not session_id:
        import uuid
        session_id = f"ws_{uuid.uuid4().hex[:12]}"

    # Get handler and process connection
    handler = get_voice_stream_handler()
    await handler.handle_connection(websocket, session_id=session_id)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)