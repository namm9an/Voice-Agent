# Phase 3: Streaming LLM - Verification Guide

## ✅ What Was Implemented

### 1. Streaming LLM Service (`streaming_llm.py`)
- **Token-by-token streaming** from Phi-3.5
- **SSE parsing** for OpenAI-compatible streaming API
- **Conversation history** with session-based memory
- **Retry logic** with exponential backoff
- **Token callbacks** for live frontend updates
- **TTS queue hand-off** when response completes

### 2. LiveKit Worker Updates
- **LLM trigger** on `asr_final` event
- **Streaming callbacks** for `llm_partial` tokens
- **TTS queue stub** for Phase 4 integration
- **Automatic cleanup** on stream end

### 3. Frontend Updates
- **Growing AI response** display with purple dashed border
- **Partial → Final** conversion logic
- **Visual distinction** between user/agent partials
- **Real-time token rendering**

## 📋 Manual Test Instructions

### Step 1: Start Backend
```bash
cd backend
poetry run uvicorn app.main:app --reload
```

**Expected startup:**
```
INFO:     Started server process
INFO:     Application startup complete.
```

### Step 2: Start Frontend
```bash
cd frontend
npm start
```

Browser opens at `http://localhost:3000`

### Step 3: Connect & Speak Test Phrase

1. **Click "Connect to Voice Agent"**
2. **Grant microphone permission**
3. **Speak clearly:**
   ```
   "Tell me a fun fact about space"
   ```

### Expected Backend Logs (Success)

```
[ASR-INIT] session=livekit_user-abc123, window=500ms, slide=250ms
[ASR-START] session=livekit_user-abc123
[LLM-INIT] session=livekit_user-abc123
[LLM-START] session=livekit_user-abc123
[STREAM-RX] Session=livekit_user-abc123, Frame=50, Samples=480
[ASR] chunk 1 → "Tell me" (0.8s)
[ASR] chunk 2 → "Tell me a fun fact" (0.9s)
[ASR] chunk 3 → "Tell me a fun fact about space" (0.8s)
[ASR-FINAL] Triggering LLM for: "Tell me a fun fact about space"
[LLM-START] session=livekit_user-abc123, prompt='Tell me a fun fact about space'
[LLM-TOKEN] chunk 5 → "Sure, here's a fun fact about space: Neut..." (0.3s)
[LLM-TOKEN] chunk 10 → "Sure, here's a fun fact about space: Neutron stars ca..." (0.6s)
[LLM-TOKEN] chunk 15 → "Sure, here's a fun fact about space: Neutron stars can spin u..." (0.9s)
[LLM-FINAL] session=livekit_user-abc123, tokens=23, time=1.2s, response="Sure, here's a fun fact about space: Neutron stars can spin up to 600 times per second!"
[TTS-QUEUE] Added response: "Sure, here's a fun fact about space: Neutro..."
```

### Expected Frontend Behavior

1. **ASR Phase:**
   - Green dashed box appears with: "Tell me"
   - Text grows: "Tell me a fun fact"
   - Final: "Tell me a fun fact about space" (solid)

2. **LLM Phase:**
   - Purple dashed box appears with: "Sure,"
   - Text grows: "Sure, here's"
   - Continues: "Sure, here's a fun fact about space:"
   - Completes: "Sure, here's a fun fact about space: Neutron stars can spin up to 600 times per second!" (solid purple)

3. **Timing:**
   - ASR partial updates: every 500ms
   - LLM partial updates: every 100-300ms
   - Total latency: < 2s from speech end to AI response start

## ✅ Success Criteria

Phase 3 is **COMPLETE** when:

- ✅ `asr_final` triggers LLM automatically
- ✅ LLM tokens stream incrementally (< 300ms between updates)
- ✅ Frontend shows **growing purple AI response**
- ✅ Logs show progressive token accumulation
- ✅ Text appears **during generation** (not after)
- ✅ TTS queue receives final response
- ✅ Retry logic handles transient errors

## ❌ Failure Indicators

If you see this → **Phase 3 not working:**

- ❌ AI text appears only after full generation (batch)
- ❌ No `[LLM-TOKEN]` logs during response
- ❌ Frontend shows nothing until LLM completes
- ❌ `[LLM-RETRY]` errors (API connection issue)
- ❌ No purple dashed partial response

## 🔧 Troubleshooting

**Issue: No LLM streaming**
```bash
# Test Phi-3.5 API directly
curl -X POST https://infer.e2enetworks.net/project/p-6530/endpoint/is-6703/v1/chat/completions \
  -H "Authorization: Bearer <LLM_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "microsoft/Phi-3.5-mini-instruct",
    "messages": [{"role":"user","content":"Hi"}],
    "stream": true
  }'
```

**Issue: Tokens not appearing**
- Check browser console for `llm_partial` messages
- Verify DataTrack emission in backend logs
- Ensure `stream=True` in API payload

**Issue: High latency (>1s per token)**
- Check `[LLM-TOKEN]` timing in logs
- Phi-3.5 may be slow - check GPU status
- Network latency to inference server

## 📊 Performance Metrics

From logs, verify:
- **Token generation**: 50-100ms per token
- **Network latency**: < 200ms per chunk
- **Total response time**: 1-3s for typical response
- **Tokens per update**: 1-5 tokens

## 🎯 Key Differences from Phase 2

| Phase 2 (ASR) | Phase 3 (LLM) |
|---------------|---------------|
| 500ms windows | Token-by-token |
| Green dashed | Purple dashed |
| Speech → Text | Text → AI response |
| Whisper Turbo | Phi-3.5 streaming |

## 📁 Files Changed

**Backend:**
- `app/services/streaming_llm.py` - ✨ NEW streaming LLM service
- `app/services/livekit_worker.py` - Added LLM trigger + TTS queue

**Frontend:**
- `src/components/LiveKitVoiceAgent.js` - Added `llm_partial` handling
- `src/App.css` - Added `agent_partial` styling

## 🚀 Next Step: Phase 4

**Streaming TTS (Parler chunked audio)**
- Receive tokens from TTS queue
- Generate audio in 1-2 sentence chunks
- Stream audio frames back to frontend
- < 1s latency from text → audio

---

**Phase 3 Status: ✅ READY FOR TESTING**
- Streaming LLM implemented
- Token-by-token frontend display
- TTS queue ready for Phase 4
- Test with: "Tell me a fun fact about space"
