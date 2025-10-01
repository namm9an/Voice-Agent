# Voice Agent

AI-powered voice interaction application with audio-in, audio-out conversational AI system.

## Architecture

- **Backend**: FastAPI with Whisper (transcription) + Phi-3.5 (LLM) + TTS
- **Frontend**: React with Web Audio API for voice recording and playback
- **Communication**: HTTP API and WebSocket for real-time streaming

## Quick Start

### Backend
```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm start
```

Visit http://localhost:3000

## Features

- 🎤 Voice recording with Web Audio API
- 🔤 Speech transcription via OpenAI Whisper
- 🤖 AI conversation with microsoft/Phi-3.5-mini-instruct language model
- 🔊 Text-to-speech response generation
- ⚡ Real-time WebSocket communication
- 📱 Responsive web interface

## Development

### Project Structure
```
voice-agent/
├── backend/           # FastAPI backend
│   ├── app/          # Application code
│   ├── tests/        # Test files
│   └── pyproject.toml
├── frontend/         # React frontend
│   ├── src/         # Source code
│   ├── public/      # Static files
│   └── package.json
└── README.md
```

### Environment Variables

Backend (.env):
- LLM_API_KEY (for Phi-3.5)
- LLM_BASE_URL (for Phi-3.5)
- WHISPER_API_KEY
- WHISPER_BASE_URL

Frontend (.env):
- REACT_APP_API_URL
- REACT_APP_WS_URL

## Makefile Commands

- `make run-backend` - Start backend server
- `make run-frontend` - Start frontend dev server
- `make install` - Install all dependencies
- `make test` - Run all tests

## Phase Status

**Phase 1** ✅ - Project setup and structure
**Phase 2** ⏳ - Actual integrations and full implementation