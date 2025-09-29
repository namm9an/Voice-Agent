import React from 'react';

const TranscriptDisplay = ({ userText, aiText }) => {
  if (!userText && !aiText) return null;
  return (
    <div className="transcript-display">
      {userText && (
        <div className="bubble user">
          <div className="label">You</div>
          <div className="text">{userText}</div>
        </div>
      )}
      {aiText && (
        <div className="bubble ai">
          <div className="label">Assistant</div>
          <div className="text">{aiText}</div>
        </div>
      )}
    </div>
  );
};

export default TranscriptDisplay;

