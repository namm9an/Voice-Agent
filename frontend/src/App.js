import React, { useState, useEffect } from 'react';
import './App.css';
import VoiceRecorder from './components/VoiceRecorder';
import AudioPlayer from './components/AudioPlayer';
import ErrorDisplay from './components/ErrorDisplay';
import AudioWaveform from './components/AudioWaveform';
import ProcessingOrb from './components/ProcessingOrb';
import IdleOrb from './components/IdleOrb';
import { apiService } from './services/api';
import { logger } from './utils/logger';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [status, setStatus] = useState('Ready');
  const [error, setError] = useState(null);
  const [autoPlay, setAutoPlay] = useState(true);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [canCancel, setCanCancel] = useState(false);

  useEffect(() => {
    let interval;
    if (isRecording || isProcessing) {
      interval = setInterval(() => setElapsedTime((t) => t + 1), 1000);
    } else {
      setElapsedTime(0);
    }
    return () => interval && clearInterval(interval);
  }, [isRecording, isProcessing]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.code === 'Space' && !event.repeat && !isProcessing) {
        event.preventDefault();
        if (isRecording) {
          handleRecordingStop();
        } else {
          handleRecordingStart();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isRecording, isProcessing]);

  const handleRecordingStart = () => {
    setIsRecording(true);
    setStatus('Listening...');
    setAudioUrl(null);
    setError(null);
    logger.info('Recording started');
  };

  const handleRecordingStop = () => {
    setIsRecording(false);
    setStatus('Processing...');
    setIsProcessing(true);
    logger.info('Recording stopped, starting processing');
  };

  const handleRecordingComplete = async (audioBlob) => {
    try {
      setStatus('Processing...');
      setError(null);
      setCanCancel(true);

      const result = await apiService.processAudio(audioBlob);

      if (result.success) {
        setAudioUrl(result.audioUrl);
        setStatus('Response ready');
        logger.info('Audio processing succeeded');
      } else {
        setStatus('Error occurred');
        setError({
          message: result.error,
          type: result.type || 'error',
          canRetry: result.canRetry !== false,
          critical: false,
        });
        logger.error('Audio processing failed', result.error);
      }
    } catch (error) {
      setStatus('Error occurred');
      setError({
        message: error.message || 'An unexpected error occurred',
        type: 'error',
        canRetry: true,
        critical: false,
      });
      logger.error('Unexpected error during processing', error);
    } finally {
      setIsProcessing(false);
      setCanCancel(false);
    }
  };

  const handleError = (errorObj) => {
    setError(errorObj);
    if (errorObj.critical) {
      setStatus('Error - action required');
    }
    logger.warn('Recorder error', errorObj);
  };

  const handleRetry = () => {
    setError(null);
    setStatus('Ready');
    logger.info('User retried after error');
  };

  const handleCancel = () => {
    // Cancel the current request
    apiService.cancelPendingRequests();
    setIsProcessing(false);
    setCanCancel(false);
    setStatus('Cancelled');
    setError({
      message: 'Processing cancelled by user',
      type: 'info',
      canRetry: true,
      critical: false,
    });
    logger.info('User cancelled processing');
  };

  const handleVoiceToggle = () => {
    if (isRecording) {
      handleRecordingStop();
    } else {
      handleRecordingStart();
    }
  };

  return (
    <div className="app-container">
      {/* Glassmorphic background */}
      <div className="background-gradient"></div>

      {/* Main Content */}
      <div className="main-content">
        <div className="brand-header">
          <h1 className="brand-title">Voice AI Assistant</h1>
          <p className="brand-subtitle">Enterprise Intelligence</p>
        </div>

        <div className="voice-interface-card">
          <div className="voice-visualizer">
            {isRecording && <AudioWaveform audioLevel={audioLevel} />}
            {isProcessing && <ProcessingOrb />}
            {!isRecording && !isProcessing && <IdleOrb />}
          </div>

          <button
            className={`voice-button ${isRecording ? 'recording' : ''} ${isProcessing ? 'processing' : ''}`}
            onClick={handleVoiceToggle}
            disabled={isProcessing}
          >
            <div className="button-inner">
              {isRecording ? (
                <>
                  <span className="pulse-ring"></span>
                  <svg className="mic-icon active" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
                  </svg>
                </>
              ) : isProcessing ? (
                <div className="processing-spinner"></div>
              ) : (
                <svg className="mic-icon" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
                </svg>
              )}
            </div>
          </button>

          <div className="status-text">
            {status}
          </div>

          {/* Cancel button when processing */}
          {canCancel && (
            <button 
              className="cancel-button"
              onClick={handleCancel}
            >
              <span className="cancel-icon">⏹</span>
              Stop Processing
            </button>
          )}

          <div className="keyboard-hint">
            Press <kbd>Space</kbd> to speak
          </div>
        </div>

        {/* Error Display */}
        <ErrorDisplay
          error={error}
          onRetry={handleRetry}
          autoDismiss={true}
          dismissTime={5000}
        />

        {/* Hidden Voice Recorder Component */}
        <div style={{ display: 'none' }}>
          <VoiceRecorder
            onRecordingComplete={handleRecordingComplete}
            isRecording={isRecording}
            onRecordingStart={handleRecordingStart}
            onRecordingStop={handleRecordingStop}
            onError={handleError}
          />
        </div>

        {/* Auto-play audio response */}
        {audioUrl && (
          <div className="response-player">
            <AudioPlayer audioUrl={audioUrl} autoPlay={autoPlay} />
          </div>
        )}
      </div>

      {/* Floating indicators */}
      <div className="floating-indicators">
        <div className="connection-status online"></div>
      </div>

      {/* Settings */}
      <div className="settings-panel">
        <details>
          <summary>Settings</summary>
          <div className="settings-content">
            <label>
              <input
                type="checkbox"
                checked={autoPlay}
                onChange={(e) => setAutoPlay(e.target.checked)}
              />
              Auto-play AI responses
            </label>
          </div>
        </details>
      </div>
    </div>
  );
}

export default App;