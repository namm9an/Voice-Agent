# Phase 1 Verification Test

## What Was Fixed

1. **✅ `_publish_audio()` now properly streams audio**
   - Chunks audio into 20ms frames
   - Uses LiveKit AudioSource correctly
   - Streams frames asynchronously

2. **✅ Audio reception logging added**
   - Logs every 50th frame with details
   - Shows buffer size and frame count
   - Verifies continuous streaming

3. **✅ Synthetic audio test added**
   - 440Hz test tone generator
   - Used for verification

4. **✅ Test endpoint created**
   - `/api/v1/livekit/test-stream` - plays test tone

## Manual Test Instructions

### Test 1: Start Backend
```bash
cd backend
poetry run uvicorn app.main:app --reload
```

**Expected Output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Test 2: Call Test Endpoint
```bash
curl -X POST http://localhost:8000/api/v1/livekit/test-stream
```

**Expected Response:**
```json
{
  "room_name": "test-abc123",
  "token": "eyJ...",
  "url": "ws://101.53.140.228:7880",
  "message": "Join this room to hear a 440Hz test tone"
}
```

### Test 3: Start Frontend & Connect
```bash
cd frontend
npm start
```

1. Click "Connect to Voice Agent"
2. Check browser console - should see:
   - "LiveKit token received"
   - "Successfully connected to room"

3. Speak into microphone - watch backend logs:
```
[STREAM-START] Processing audio for session: livekit_user_xxx
[STREAM-RX] Session=livekit_user_xxx, Frame=50, Samples=480, Rate=48000Hz, BufferSize=48000 bytes
[STREAM-RX] Session=livekit_user_xxx, Frame=100, Samples=480, Rate=48000Hz, BufferSize=96000 bytes
[STREAM-PROCESS] Processing 32000 bytes after 167 frames
```

### Test 4: Full Pipeline Test (if ASR/LLM/TTS working)
1. Say "Hello"
2. Backend logs should show:
```
[livekit_user_xxx] Starting transcription...
[livekit_user_xxx] Transcription: 'hello' (1.2s)
[livekit_user_xxx] Generating LLM response...
[livekit_user_xxx] LLM response: 'Hi! How can I help you?' (1.5s)
[livekit_user_xxx] Generating TTS audio...
Publishing audio: 64000 bytes, 16000Hz, 1ch
Published audio track: TR_xxx
Finished streaming audio track
```

3. You should **hear** the AI response

## Expected Backend Logs (Success)

```
INFO - Created LiveKit token for room='voice-room-abc123', participant='user-def456'
INFO - Scheduled agent to join room: voice-room-abc123
INFO - Agent joining room: voice-room-abc123
INFO - Agent connected to room: voice-room-abc123
INFO - Participant connected: user-def456 in room voice-room-abc123
INFO - Track subscribed: KIND_AUDIO from user-def456
INFO - [STREAM-START] Processing audio for session: livekit_user-def456
INFO - [STREAM-RX] Session=livekit_user-def456, Frame=50, Samples=480, Rate=48000Hz
INFO - [STREAM-RX] Session=livekit_user-def456, Frame=100, Samples=480, Rate=48000Hz
INFO - [STREAM-PROCESS] Processing 32000 bytes after 167 frames
```

## Success Criteria

Phase 1 is **COMPLETE** when:

- ✅ User joins room successfully
- ✅ Microphone audio streams to backend (see `[STREAM-RX]` logs)
- ✅ Backend receives continuous audio frames
- ✅ Backend can publish audio back to user
- ✅ User hears backend audio

## Known Limitations

1. **Still using 2-second buffer** - Not fully real-time yet (Phase 2 will fix)
2. **ASR/LLM/TTS still batch mode** - Phases 2-4 will add streaming
3. **No barge-in** - Phase 6 will add interruption
4. **Latency ~4-8s** - Phase 7 will optimize

## Next Step

**Phase 2: Real-Time ASR Streaming**
- Replace 2-second buffer with 500ms chunks
- Add streaming Whisper transcription
- Send partial transcripts to frontend
