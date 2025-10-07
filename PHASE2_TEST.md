# Phase 2: Real-Time ASR - Verification Guide

## ✅ What Was Implemented

### 1. Streaming ASR Service (`streaming_asr.py`)
- **500ms audio windows** with 250ms slide
- **Producer-consumer pattern** using asyncio.Queue
- **Rolling buffer** (max 1s of audio)
- **Retry logic** with exponential backoff for Whisper API
- **Partial transcript emission** via callback

### 2. Updated LiveKit Worker
- Removed 2-second batch buffer
- Integrated StreamingASR for real-time processing
- Emits `asr_partial` and `asr_final` via DataTrack
- Flushes buffer on stream end

### 3. Frontend Updates
- Handles `asr_partial` messages for growing text
- Displays partial transcripts with pulsing animation (green dashed border)
- Converts partial to permanent on `asr_final`
- Visual distinction: partial vs final transcripts

## 📋 Manual Test Instructions

### Step 1: Start Backend
```bash
cd backend
poetry run uvicorn app.main:app --reload
```

**Expected startup logs:**
```
INFO:     Started server process
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Step 2: Start Frontend
```bash
cd frontend
npm start
```

Browser opens at `http://localhost:3000`

### Step 3: Connect & Speak

1. **Click "Connect to Voice Agent"**
2. **Grant microphone permission**
3. **Speak test phrase slowly:**
   ```
   "Hello world testing whisper streaming"
   ```

### Expected Backend Logs

```
[ASR-INIT] session=livekit_user-abc123, window=500ms, slide=250ms
[ASR-START] session=livekit_user-abc123
[STREAM-RX] Session=livekit_user-abc123, Frame=50, Samples=480, Rate=48000Hz
[STREAM-RX] Session=livekit_user-abc123, Frame=100, Samples=480, Rate=48000Hz
[ASR] chunk 1 → "Hello" (0.8s)
[ASR-EMIT] asr_partial: "Hello"
[ASR] chunk 2 → "Hello world" (0.9s)
[ASR-EMIT] asr_partial: "Hello world"
[ASR] chunk 3 → "Hello world testing" (0.8s)
[ASR-EMIT] asr_partial: "Hello world testing"
[ASR] chunk 4 → "Hello world testing whisper" (0.9s)
[ASR-EMIT] asr_partial: "Hello world testing whisper"
[ASR] chunk 5 → "Hello world testing whisper streaming" (0.8s)
[ASR-EMIT] asr_partial: "Hello world testing whisper streaming"
[ASR-FLUSH] Processing final 12000 samples
[ASR-EMIT] asr_final: ""
[ASR-STOP] session=livekit_user-abc123, chunks=5
```

### Expected Frontend Behavior

1. **Partial transcript appears** (green dashed border, italic, pulsing)
2. **Text grows** as you speak:
   - "Hello" → "Hello world" → "Hello world testing" ...
3. **Becomes solid** when you stop (final transcript)
4. **New line** for next utterance

## ✅ Success Criteria

Phase 2 is **COMPLETE** when you observe:

- ✅ Each 500ms → new ASR chunk in logs
- ✅ Backend logs show `[ASR] chunk N → "text"` every ~0.5s
- ✅ Frontend displays **growing text while speaking**
- ✅ Partial transcript has green dashed border + pulse animation
- ✅ Text appears **< 1s after speaking** (not after silence)
- ✅ No errors in retry logic

## ❌ Failure Indicators

If you see this → **Phase 2 not working:**

- ❌ Text appears only after you stop speaking (batch mode)
- ❌ No `[ASR]` logs during speech
- ❌ Frontend shows nothing until silence
- ❌ Logs show `[ASR-RETRY]` repeatedly (Whisper connection issue)

## 🔧 Troubleshooting

**Issue: No ASR logs**
```bash
# Check Whisper API is accessible
curl -X POST https://infer.e2enetworks.net/project/p-6530/endpoint/is-6690/v1/audio/transcriptions \
  -H "Authorization: Bearer <WHISPER_API_KEY>" \
  -F "file=@test.wav" \
  -F "model=openai/whisper-large-v3-turbo"
```

**Issue: Partial transcript not showing**
- Check browser console for `Data received:` messages
- Verify `asr_partial` type in console

**Issue: High latency (>2s)**
- Check `[ASR] chunk N → "text" (X.Xs)` timing
- If X > 1.5s → Whisper API slow

## 📊 Performance Metrics

From logs, verify:
- **Window size**: 500ms (24k samples @ 48kHz)
- **Slide interval**: 250ms (~12 frames)
- **Whisper latency**: 0.5-1.5s per chunk
- **Total latency**: < 1.5s speech → display

## 🎯 Key Differences from Phase 1

| Phase 1 | Phase 2 |
|---------|---------|
| 2-second buffer | 500ms windows |
| Batch processing | Streaming ASR |
| No partial updates | Growing text |
| Post-speech display | Real-time display |

## 📁 Files Changed

**Backend:**
- `app/services/streaming_asr.py` - ✨ NEW streaming ASR service
- `app/services/livekit_worker.py` - Replaced batch with streaming

**Frontend:**
- `src/components/LiveKitVoiceAgent.js` - Added partial transcript handling
- `src/App.css` - Added `user_partial` styling

## 🚀 Next Step: Phase 3

**Streaming LLM (Phi-3.5 token-by-token)**
- Receive final transcript from Phase 2
- Stream LLM response tokens as they're generated
- Send tokens to TTS queue (Phase 4)
- Display growing AI response in frontend
