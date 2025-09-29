import React, { useRef, useEffect } from 'react';

const AudioPlayer = ({ audioUrl, autoPlay = false }) => {
  const audioRef = useRef(null);

  useEffect(() => {
    // Play audio response received from backend
    if (audioUrl && audioRef.current) {
      if (autoPlay) {
        audioRef.current.play().catch(error => {
          console.error('Error playing audio:', error);
        });
      }
    }
  }, [audioUrl, autoPlay]);

  if (!audioUrl) {
    return null;
  }

  return (
    <div className="audio-player" style={{ display: 'none' }}>
      <audio
        ref={audioRef}
        src={audioUrl}
        preload="auto"
      >
        Your browser does not support the audio element.
      </audio>
    </div>
  );
};

export default AudioPlayer;