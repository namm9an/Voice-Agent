# Phase 4: Streaming TTS - Deployment & Test Guide

## ✅ What Was Implemented

### 1. Streaming TTS Service (`streaming_tts.py`)
- **Sentence segmentation** (15-25 tokens per chunk)
- **Real-time audio streaming** (20ms PCM frames @ 16kHz)
- **Parler TTS primary** with XTTS fallback
- **Retry logic** with exponential backoff
- **Progressive frame emission** via DataTrack

### 2. LiveKit Worker Integration
- **TTS queue consumer** task
- **Audio chunk callbacks** with base64 encoding
- **Unreliable DataTrack** for low-latency audio
- **Automatic cleanup** on stream end

### 3. Frontend Audio Playback
- **Web Audio API** progressive playback
- **Audio queue** for seamless streaming
- **16kHz mono PCM** decoding
- **Speaking indicator** while playing

## 📋 Deployment Instructions

### Step 1: Deploy to Server with LiveKit

**Requirements:**
- Same VM/server where LiveKit is running (`101.53.140.228`)
- Phi-3.5, Whisper Turbo, Parler TTS accessible
- Python 3.9+, Node.js 18+

**Upload project:**
```bash
# On your local machine
cd /Users/namanmoudgill13/Desktop/Voice-Agent
scp -r . user@101.53.140.228:~/voice-agent/
```

### Step 2: Start Backend on Server

```bash
ssh user@101.53.140.228
cd ~/voice-agent/backend

# Re-enable agent auto-join (IMPORTANT!)
nano app/api/routes/livekit.py
```

**Uncomment these lines:**
```python
# Start agent in the room (background task)
worker = get_livekit_worker()
background_tasks.add_task(worker.join_room, room_name)
logger.info(f"Scheduled agent to join room: {room_name}")
```

**Remove this line:**
```python
logger.warning(f"Agent auto-join disabled for room: {room_name} (WebRTC timeout issue)")
```

**Start backend:**
```bash
poetry install
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Step 3: Start Frontend on Server

```bash
# In another terminal on server
cd ~/voice-agent/frontend

# Update API URL if needed
nano .env
# Add: REACT_APP_API_URL=http://101.53.140.228:8000

npm install
npm run build
npx serve -s build -p 3000
```

### Step 4: Test Full Pipeline

**From your local browser:**
```
http://101.53.140.228:3000
```

1. Click "Connect to Voice Agent"
2. Grant microphone permission
3. Speak: **"Tell me a fun fact about space"**

### Expected Server Logs (Success)

```
[STREAM-START] Processing audio for session: livekit_user-abc123
[ASR-INIT] session=livekit_user-abc123, window=500ms
[LLM-INIT] session=livekit_user-abc123
[TTS-INIT] session=livekit_user-abc123, rate=16000Hz
[TTS-CONSUMER-START] session=livekit_user-abc123

[STREAM-RX] Session=livekit_user-abc123, Frame=50, Samples=480
[ASR] chunk 1 → "Tell me" (0.8s)
[ASR] chunk 2 → "Tell me a fun fact about space" (1.1s)
[ASR-FINAL] Triggering LLM for: "Tell me a fun fact about space"

[LLM-START] session=livekit_user-abc123, prompt='Tell me a fun fact about space'
[LLM-TOKEN] chunk 5 → "Sure, here's a fun fact about space..." (0.3s)
[LLM-TOKEN] chunk 10 → "Sure, here's a fun fact about space: Neutron..." (0.6s)
[LLM-FINAL] session=livekit_user-abc123, tokens=25, time=1.3s

[TTS-QUEUE] Added response: "Sure, here's a fun fact about space: Neutron..."
[TTS-QUEUE-POP] queue_length=0, text="Sure, here's a fun fact about space..."
[TTS-SEGMENTS] 2 segments from text: "Sure, here's a fun fact about space..."

[TTS-START] segment=1/2, text="Sure, here's a fun fact about space:"
[TTS-AUDIO] segment=1, size=64000 bytes, rate=16000Hz, channels=1
[TTS-CHUNK] segment=1, frame=20, samples=320
[TTS-CHUNK] segment=1, frame=40, samples=320
[TTS-SEGMENT-END] segment=1, time=0.9s
[TTS-NEXT] segment=2/2

[TTS-START] segment=2/2, text="Neutron stars can spin up to 600 times per second!"
[TTS-AUDIO] segment=2, size=80000 bytes, rate=16000Hz
[TTS-CHUNK] segment=2, frame=25, samples=320
[TTS-SEGMENT-END] segment=2, time=1.1s
[TTS-DONE] session=livekit_user-abc123, segments=2

[TTS-STOP] session=livekit_user-abc123, segments=2, frames=156
[STREAM-END] session=livekit_user-abc123
```

### Expected Browser Behavior

1. **ASR Phase:**
   - Green dashed: "Tell me a fun fact about space"

2. **LLM Phase:**
   - Purple dashed growing: "Sure, here's..." → "Sure, here's a fun fact..."

3. **TTS Phase:**
   - **Audio starts playing < 1s after LLM final**
   - Hear: "Sure, here's a fun fact about space:"
   - Then: "Neutron stars can spin up to 600 times per second!"
   - Total audio latency: < 2s from LLM completion

## ✅ Success Criteria

Phase 4 is **COMPLETE** when:

- ✅ LLM final text triggers TTS automatically
- ✅ Audio playback starts **< 1s** after TTS begins
- ✅ Audio streams chunk-by-chunk (not batch)
- ✅ Logs show segment-by-segment processing
- ✅ No gaps/stutters in audio playback
- ✅ Frontend plays progressively

## ❌ Failure Indicators

If you see this → **Phase 4 not working:**

- ❌ Audio plays only after full generation (batch)
- ❌ No `[TTS-CHUNK]` logs during playback
- ❌ Long delay (>2s) between LLM and audio
- ❌ `[TTS-RETRY]` errors (Parler API issue)
- ❌ Audio stutters/gaps

## 🔧 Troubleshooting

**Issue: Agent connection timeout**
- Ensure backend runs on same server as LiveKit
- Check LiveKit credentials in `.env`
- Verify auto-join code is uncommented

**Issue: No TTS audio**
```bash
# Test Parler TTS directly
curl -X POST http://164.52.192.118:8001/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world","description":"Female voice"}'
```

**Issue: Audio choppy**
- Check network latency
- Increase frame buffer size (Phase 7)
- Use reliable=True for DataTrack

## 📊 Performance Metrics

From logs, verify:
- **Segment latency**: 0.5-1.5s per segment
- **Frame rate**: 50 frames/sec (20ms chunks)
- **Total TTS latency**: < 2s from text → playback
- **Audio quality**: 16kHz mono PCM

## 🎯 Pipeline Flow

```
User Speech (LiveKit)
    ↓ 48kHz frames
[ASR] Whisper Turbo (500ms windows)
    ↓ Partial transcripts
[LLM] Phi-3.5 (token streaming)
    ↓ Complete response
[TTS Queue] → Consumer task
    ↓ Sentence segments
[TTS] Parler (20ms PCM frames)
    ↓ Base64 encoded audio
Frontend (Web Audio API playback)
```

## 📁 Files Changed

**Backend:**
- `app/services/streaming_tts.py` - ✨ NEW
- `app/services/livekit_worker.py` - TTS consumer added

**Frontend:**
- `src/components/LiveKitVoiceAgent.js` - Audio playback added

## 🚀 Next Steps

**Phase 5: System Integration Testing**
- Full pipeline smoke test
- Latency measurement
- Error handling verification

**Phase 6: Interruptibility (Barge-In)**
- Detect user speech during AI response
- Cancel TTS/LLM tasks
- Start new ASR immediately

**Phase 7: Latency Optimization**
- Target: < 500ms end-to-end
- FP16 inference
- Reduce buffer sizes
- Optimize frame rates

---

**Phase 4 Status: ✅ READY FOR DEPLOYMENT**
- Streaming TTS implemented
- Audio chunks via DataTrack
- Frontend playback ready
- Deploy to server with LiveKit for full test
