# Voice Agent Backend

FastAPI backend for the Voice Agent application with audio processing capabilities.

## Setup

1. Install Poetry:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:
```bash
poetry install
```

3. Environment configuration:
Set variables in your shell or create a `.env` file (optional). Examples:
```
OPENAI_API_KEY=<your_whisper_api_key>
QWEN_ENDPOINT=<your_qwen_model_endpoint>
QWEN_API_KEY=<your_qwen_api_key>
TTS_MODEL=coqui
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=INFO
MAX_AUDIO_SIZE_MB=10
AUDIO_SAMPLE_RATE=16000
```

## Run

```bash
poetry run uvicorn app.main:app --reload
```

Server will start at http://localhost:8000

## API Endpoints

- GET `/` - Root endpoint
- GET `/health` - Health check (root)
- GET `/api/v1/health` - Health check (versioned)
- POST `/api/v1/process-audio` - Process audio file
- WebSocket `/ws` - Real-time audio streaming

## Development

Run tests:
```bash
poetry run pytest
```

Code formatting:
```bash
poetry run black .
poetry run flake8 .
```

## Phase 1 Status

✅ Project structure created
✅ Dependencies configured
✅ Placeholder services implemented
⏳ Phase 2: Actual integrations (Whisper, Qwen, TTS)