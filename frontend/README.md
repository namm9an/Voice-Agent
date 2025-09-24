# Voice Agent Frontend

React frontend for the Voice Agent application providing voice interaction UI.

## Setup

1. Install Node.js (v16+ recommended)

2. Install dependencies:
```bash
npm install
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env if needed
```

## Run

```bash
npm start
```

Application will start at http://localhost:3000

## Available Scripts

- `npm start` - Run development server
- `npm build` - Build for production
- `npm test` - Run tests
- `npm run lint` - Run ESLint

## Components

- **VoiceRecorder** - Audio recording interface
- **AudioPlayer** - Audio playback component
- **StatusIndicator** - Visual status feedback

## Services

- **apiService** - Backend API communication
- **audioService** - Web Audio API utilities
- **websocketService** - WebSocket connection handling

## Phase 1 Status

✅ Project structure created
✅ Components scaffolded
✅ Services structure implemented
⏳ Phase 2: Full audio recording and WebSocket integration