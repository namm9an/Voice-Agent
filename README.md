# 🎙️ Voice Agent

Real-time conversational AI voice agent with sub-second latency, built with LiveKit, Whisper, Phi-3.5, and Parler TTS.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.0+-61DAFB.svg)](https://reactjs.org/)
[![LiveKit](https://img.shields.io/badge/LiveKit-Real--time-orange.svg)](https://livekit.io/)

## ✨ Features

- 🔊 **Real-time Voice Streaming** - LiveKit WebRTC transport with low-latency audio
- 🎯 **Streaming ASR** - Whisper Turbo with 500ms windowed transcription
- 💬 **Token-by-Token LLM** - Phi-3.5-mini-instruct with progressive response generation
- 🗣️ **Chunked TTS** - Parler TTS with sentence-level audio streaming (20ms frames)
- ⚡ **Barge-In Support** - Interrupt AI mid-response with natural conversation flow
- 📊 **Production Monitoring** - Metrics tracking, health checks, and circuit breakers
- 🎨 **Live Transcripts** - Real-time partial and final transcript display
- 🔄 **E2E Pipeline** - <1s speech-to-response latency

## 🏗️ Architecture

```
User Speech → LiveKit → ASR (Whisper) → LLM (Phi-3.5) → TTS (Parler) → Audio Playback
              ↑_______________________________________________↓
                      Barge-In / Pipeline Coordinator
```

### Technology Stack

**Backend:**
- FastAPI (async Python web framework)
- LiveKit SDK (real-time audio transport)
- Whisper Turbo (speech-to-text)
- Phi-3.5-mini-instruct (conversational LLM)
- Parler TTS + XTTS fallback (text-to-speech)

**Frontend:**
- React 18+ (UI framework)
- LiveKit Components (audio/video SDK)
- Web Audio API (audio playback)
- Real-time transcript rendering

**Infrastructure:**
- Poetry (Python dependency management)
- asyncio (concurrent task management)
- Prometheus-compatible metrics
- Health check endpoints

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- Poetry (`pip install poetry`)
- LiveKit server (running on your infrastructure)

### 1. Clone Repository

```bash
git clone https://github.com/namm9an/Voice-Agent.git
cd Voice-Agent
```

### 2. Backend Setup

```bash
cd backend

# Install dependencies
poetry install

# Create .env file (see Configuration section below)
cp .env.example .env
nano .env  # Add your API keys and URLs

# Start backend
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

Frontend will open at `http://localhost:3000`

## ⚙️ Configuration

### Backend Environment Variables

Create `backend/.env` with the following:

```bash
# Core Settings
APP_ENV=development
APP_PORT=8000
LOG_LEVEL=INFO

# LiveKit Configuration
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_URL=ws://your-livekit-server:7880

# ASR (Whisper Turbo)
WHISPER_API_KEY=your_whisper_api_key
WHISPER_BASE_URL=https://your-whisper-endpoint/v1/
WHISPER_MODEL=openai/whisper-large-v3-turbo
ASR_BUFFER_WINDOW_MS=500
ASR_BUFFER_SLIDE_MS=250

# LLM (Phi-3.5)
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://your-llm-endpoint/v1/
LLM_MODEL=microsoft/Phi-3.5-mini-instruct
LLM_STREAMING=true
LLM_MAX_TOKENS=256
LLM_TEMPERATURE=0.8

# TTS (Parler + XTTS Fallback)
PARLER_TTS_BASE_URL=http://your-parler-server:8001
XTTS_TTS_BASE_URL=http://your-xtts-server:8000
TTS_VOICE=female
TTS_LANGUAGE=en

# Audio & CORS
CORS_ORIGINS=http://localhost:3000,http://your-production-domain
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1

# Pipeline & Sessions
SESSION_EXPIRY_MINUTES=10
MAX_CONCURRENT_SESSIONS=5
MEMORY_CONTEXT_TOKENS=512

# Monitoring
ENABLE_METRICS=true
METRICS_SAVE_PATH=./logs/metrics.jsonl
HEALTH_CHECK_INTERVAL=30
SERVICE_TIMEOUT=3
```

### Frontend Environment Variables

Create `frontend/.env` (optional):

```bash
REACT_APP_API_URL=http://localhost:8000
```

## 📁 Project Structure

```
Voice-Agent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── livekit.py          # LiveKit token generation
│   │   │   │   └── monitoring.py       # Health & metrics endpoints
│   │   │   └── livekit_room_handler.py # Audio stream processing
│   │   ├── services/
│   │   │   ├── streaming_asr.py        # Real-time speech-to-text
│   │   │   ├── streaming_llm.py        # Token streaming LLM
│   │   │   ├── streaming_tts.py        # Chunked text-to-speech
│   │   │   ├── pipeline_coordinator.py  # ASR→LLM→TTS orchestration
│   │   │   ├── livekit_worker.py       # LiveKit agent worker
│   │   │   ├── metrics_manager.py      # Performance tracking
│   │   │   └── health_monitor.py       # Service health checks
│   │   ├── config/
│   │   │   └── settings.py             # Configuration management
│   │   └── main.py                     # FastAPI application
│   └── pyproject.toml                  # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── LiveKitVoiceAgent.js    # Main voice UI component
│   │   ├── AppLiveKit.js               # App wrapper
│   │   ├── App.css                     # Styles
│   │   └── index.js                    # Entry point
│   └── package.json                    # Node dependencies
└── README.md
```

## 🎯 How It Works

### 1. Connection Flow

1. User clicks "Connect to Voice Agent"
2. Frontend requests LiveKit token from backend
3. Backend generates JWT token with room access
4. Frontend connects to LiveKit room
5. Backend agent joins room automatically
6. Microphone audio streams to backend via LiveKit

### 2. Voice Processing Pipeline

```
┌─────────────┐
│ User Speech │ (Microphone)
└──────┬──────┘
       ↓ Audio frames (48kHz)
┌─────────────────────┐
│  Streaming ASR      │ (500ms windows, 250ms slide)
│  (Whisper Turbo)    │
└──────┬──────────────┘
       ↓ Partial transcripts → Frontend (green dashed)
       ↓ Final transcript
┌─────────────────────┐
│  Streaming LLM      │ (Token-by-token)
│  (Phi-3.5)          │
└──────┬──────────────┘
       ↓ Token stream → Frontend (purple dashed)
       ↓ Complete response
┌─────────────────────┐
│  Streaming TTS      │ (Sentence chunks)
│  (Parler)           │
└──────┬──────────────┘
       ↓ 20ms PCM frames → Frontend
┌─────────────────────┐
│  Audio Playback     │ (Web Audio API)
│  (Progressive)      │
└─────────────────────┘
```

### 3. Barge-In (Interruption)

- **Detection**: RMS audio level > 0.02 during TTS playback
- **Action**: Cancel LLM task, stop TTS, flush audio queue
- **Result**: AI stops speaking, new ASR cycle begins
- **Latency**: <200ms interruption response time

## 📊 Monitoring & Metrics

### Health Check Endpoint

```bash
curl http://localhost:8000/api/v1/monitoring/health
```

Returns service health status (ASR, LLM, TTS).

### Metrics Endpoint

```bash
curl http://localhost:8000/api/v1/monitoring/metrics
```

Returns:
- Active sessions
- Average latencies (ASR, LLM, TTS, E2E)
- Latency target compliance
- Error counts
- Barge-in frequency

### Metrics File

Session metrics are persisted to `backend/logs/metrics.jsonl`:

```json
{
  "session_id": "livekit_user-abc123",
  "duration_s": 15.23,
  "asr": {"avg_latency_ms": 62.56},
  "llm": {"avg_latency_ms": 52.19},
  "tts": {"avg_latency_ms": 11.54},
  "e2e": {"avg_latency_ms": 920.5}
}
```

## 🧪 Testing

### Manual Test Flow

1. Start backend and frontend
2. Click "Connect to Voice Agent"
3. Grant microphone permission
4. Speak: **"Tell me a fun fact about space"**
5. Observe:
   - Real-time transcript (green dashed → solid)
   - AI response (purple dashed → solid)
   - Audio playback starts <1s after your speech ends

### Interrupt Test

1. Ask: **"Tell me a long story about planets"**
2. While AI is speaking, interrupt: **"Actually, tell me about black holes"**
3. Verify:
   - AI stops immediately
   - New response begins within ~1s
   - No audio overlap

## 🐛 Troubleshooting

### Backend won't start

- Check `.env` file exists and has all required variables
- Verify Python 3.9+ is installed: `python --version`
- Run `poetry install` to ensure dependencies are installed

### Frontend can't connect

- Verify backend is running on port 8000
- Check CORS origins in backend `.env` include your frontend URL
- Ensure LiveKit server is accessible

### No audio playback

- Check Parler TTS service is running and accessible
- Verify browser microphone permissions granted
- Check browser console for errors
- Test Parler endpoint: `curl http://your-parler-url:8001/health`

### High latency

Check metrics to identify bottleneck:
```bash
curl http://localhost:8000/api/v1/monitoring/metrics
```

- **High ASR**: Whisper endpoint slow
- **High LLM**: Phi-3.5 endpoint slow
- **High TTS**: Parler endpoint slow

## 📈 Performance Targets

| Metric | Target | Typical |
|--------|--------|---------|
| ASR Latency | <500ms | ~65ms |
| LLM Latency | <300ms | ~49ms |
| TTS Latency | <200ms | ~12ms |
| **E2E Latency** | **<1000ms** | **~890ms** |
| Interruption | <200ms | ~150ms |

## 🚀 Production Deployment

### Prerequisites

- Server with LiveKit installed and running
- GPU nodes for Whisper, Phi-3.5, and Parler TTS
- Domain with SSL certificate (for production)

### Steps

1. **Deploy backend on server with LiveKit:**
```bash
# On server
cd ~/voice-agent/backend
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. **Build and serve frontend:**
```bash
cd ~/voice-agent/frontend
npm run build
npx serve -s build -p 3000
```

3. **Configure reverse proxy (nginx):**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

4. **Set up monitoring:**
- Configure Prometheus to scrape `/api/v1/monitoring/metrics`
- Set up Grafana dashboard for latency tracking
- Configure alerts for service health

## 🤝 Contributing

This is a demonstration project showcasing real-time AI voice agent capabilities. For production use, consider:

- Adding authentication and user management
- Implementing rate limiting
- Setting up log aggregation (ELK/Loki)
- Load balancing for multiple backend instances
- Redis for session state management

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- [LiveKit](https://livekit.io/) - Real-time communication platform
- [OpenAI Whisper](https://github.com/openai/whisper) - Speech recognition
- [Microsoft Phi-3.5](https://huggingface.co/microsoft/Phi-3.5-mini-instruct) - Language model
- [Parler TTS](https://github.com/huggingface/parler-tts) - Text-to-speech synthesis

## 📧 Contact

**Naman Moudgill**
- GitHub: [@namm9an](https://github.com/namm9an)
- Project: [Voice-Agent](https://github.com/namm9an/Voice-Agent)

---

Built with ❤️ using FastAPI, React, and LiveKit
