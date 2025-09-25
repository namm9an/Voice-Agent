import React, { useState, useEffect } from 'react';

const StatusIndicator = ({
  status,
  isRecording,
  isProcessing,
  processingStage = null,
  elapsedTime = 0
}) => {
  const [animationClass, setAnimationClass] = useState('');

  useEffect(() => {
    if (isRecording) {
      setAnimationClass('recording-pulse');
    } else if (isProcessing) {
      setAnimationClass('processing-spin');
    } else {
      setAnimationClass('');
    }
  }, [isRecording, isProcessing]);

  const getStatusIcon = () => {
    if (isRecording) {
      return '🎤';
    } else if (isProcessing) {
      if (processingStage === 'transcribing') return '🔄';
      if (processingStage === 'thinking') return '🤔';
      if (processingStage === 'generating') return '🗣️';
      return '⚙️';
    } else {
      return '✅';
    }
  };

  const getProcessingText = () => {
    if (!isProcessing) return status;

    // Instead of "Transcribing speech..." just show:
    return 'Processing...';
  };

  const formatTime = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`status-indicator ${animationClass}`}>
      <div className="status-icon-container">
        <span className="status-icon">
          {getStatusIcon()}
        </span>
        {isRecording && (
          <span className="recording-dot"></span>
        )}
        {isProcessing && (
          <div className="processing-spinner">
            <div className="spinner-ring"></div>
          </div>
        )}
      </div>

      <div className="status-text-container">
        <span className="status-text">
          {getProcessingText()}
        </span>

        {(isRecording || isProcessing) && elapsedTime > 0 && (
          <span className="elapsed-time">
            {formatTime(elapsedTime)}
          </span>
        )}
      </div>

      {isProcessing && (
        <div className="processing-indicator">
          <div className="spinner"></div>
          <p>Processing...</p>
        </div>
      )}
    </div>
  );
};

export default StatusIndicator;