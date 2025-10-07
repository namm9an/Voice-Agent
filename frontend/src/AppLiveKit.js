import React from 'react';
import LiveKitVoiceAgent from './components/LiveKitVoiceAgent';
import './App.css';

function AppLiveKit() {
  return (
    <div className="app">
      <div className="background-gradient"></div>
      <div className="main-container">
        <header className="header">
          <h1 className="title">LiveKit Voice AI Assistant</h1>
          <p className="subtitle">Real-time voice interaction with minimal latency</p>
        </header>

        <LiveKitVoiceAgent />
      </div>
    </div>
  );
}

export default AppLiveKit;
