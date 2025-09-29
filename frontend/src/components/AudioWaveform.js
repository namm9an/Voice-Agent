import React from 'react';

const AudioWaveform = ({ audioLevel = 0 }) => {
  const level = Math.min(1, Math.max(0, audioLevel));
  const height = 10 + level * 90;
  return (
    <div className="waveform-container">
      <div className="waveform-bar" style={{ height: `${height}px` }} />
    </div>
  );
};

export default AudioWaveform;

