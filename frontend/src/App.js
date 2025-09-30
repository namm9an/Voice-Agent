import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';

// Generate unique session ID for this browser session
const SESSION_ID = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

function App() {
  const [connectionState, setConnectionState] = useState('disconnected');
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const [audioLevel, setAudioLevel] = useState(0);
  const [error, setError] = useState(null);
  const [selectedVoice, setSelectedVoice] = useState('female');
  const [availableVoices, setAvailableVoices] = useState({});
  const [continuousMode, setContinuousMode] = useState(false);
  const [isListening, setIsListening] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const audioStreamRef = useRef(null);
  const vadRef = useRef(null);
  const silenceTimeoutRef = useRef(null);
  const speechTimeoutRef = useRef(null);
  const currentAudioRef = useRef(null);

  // Initialize audio context for visualization
  useEffect(() => {
    audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    return () => {
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  // Load available voices on component mount
  useEffect(() => {
    const loadVoices = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/voices');
        const data = await response.json();
        setAvailableVoices(data.available_voices);
        setSelectedVoice(data.current_voice || 'female');
      } catch (error) {
        console.error('Failed to load voices:', error);
      }
    };
    loadVoices();
  }, []);

  const startRecording = async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          sampleSize: 16,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });
      
      audioStreamRef.current = stream;
      
      // Setup audio visualization
      const source = audioContextRef.current.createMediaStreamSource(stream);
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      source.connect(analyserRef.current);
      
      // Start visualization
      visualizeAudio();
      
      // Setup MediaRecorder with correct MIME type
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
        ? 'audio/webm;codecs=opus' 
        : 'audio/ogg;codecs=opus';
      
      mediaRecorderRef.current = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];
      
      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      
      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        await processAudio(audioBlob);
      };
      
      mediaRecorderRef.current.start();
      setIsRecording(true);
      setConnectionState('connected');
      
      // Add to transcript
      setTranscript(prev => [...prev, { 
        type: 'system', 
        text: 'Listening...', 
        timestamp: new Date().toISOString() 
      }]);
      
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('Failed to access microphone. Please check permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(track => track.stop());
      }
    }
  };

  const visualizeAudio = () => {
    if (!analyserRef.current || !isRecording) return;
    
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);
    
    const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
    const level = average / 255;
    setAudioLevel(level);
    
    // Voice Activity Detection for continuous mode
    if (continuousMode && isListening) {
      const threshold = 0.1; // Adjust this value based on testing
      
      if (level > threshold) {
        // Speech detected
        if (silenceTimeoutRef.current) {
          clearTimeout(silenceTimeoutRef.current);
          silenceTimeoutRef.current = null;
        }
        
        if (!isRecording) {
          // Start recording when speech is detected
          startRecording();
        }
        
        // Reset speech timeout
        if (speechTimeoutRef.current) {
          clearTimeout(speechTimeoutRef.current);
        }
        speechTimeoutRef.current = setTimeout(() => {
          if (isRecording) {
            stopRecording();
          }
        }, 3000); // Stop after 3 seconds of speech
      } else {
        // Silence detected
        if (isRecording && !silenceTimeoutRef.current) {
          silenceTimeoutRef.current = setTimeout(() => {
            if (isRecording) {
              stopRecording();
            }
          }, 1500); // Stop after 1.5 seconds of silence
        }
      }
    }
    
    requestAnimationFrame(visualizeAudio);
  };

  const processAudio = async (audioBlob) => {
    setConnectionState('processing');

    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.webm');

      const response = await fetch('http://localhost:8000/api/v1/process-audio', {
        method: 'POST',
        body: formData,
        headers: {
          'X-Session-ID': SESSION_ID
        }
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      // Extract transcription and AI response from headers
      const transcription = response.headers.get('X-Transcription') || 'Audio message';
      const aiResponse = response.headers.get('X-AI-Response') || 'Response received';

      // Add user message to transcript
      setTranscript(prev => [...prev, {
        type: 'user',
        text: transcription,
        timestamp: new Date().toISOString()
      }]);

      const audioResponse = await response.blob();

      // Clean up previous audio URL if exists
      if (currentAudioRef.current) {
        URL.revokeObjectURL(currentAudioRef.current);
      }

      // Play the response
      const audioUrl = URL.createObjectURL(audioResponse);
      currentAudioRef.current = audioUrl;
      const audio = new Audio(audioUrl);

      // Add AI response to transcript
      setTranscript(prev => [...prev, {
        type: 'agent',
        text: aiResponse,
        timestamp: new Date().toISOString()
      }]);

      // Clean up audio URL after playback completes
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        currentAudioRef.current = null;
      };

      // Handle playback errors
      audio.onerror = (e) => {
        console.error('Audio playback error:', e);
        URL.revokeObjectURL(audioUrl);
        currentAudioRef.current = null;
        setError('Failed to play audio response');
      };

      await audio.play();
      setConnectionState('connected');

    } catch (err) {
      console.error('Processing failed:', err);
      setError(`Failed to process audio: ${err.message}`);
      setConnectionState('error');
    }
  };

  // Voice selection handler
  const handleVoiceChange = async (voiceName) => {
    try {
      const response = await fetch(`http://localhost:8000/api/v1/voices/${voiceName}`, {
        method: 'POST'
      });
      if (response.ok) {
        setSelectedVoice(voiceName);
      }
    } catch (error) {
      console.error('Failed to change voice:', error);
    }
  };

  // Continuous mode toggle
  const toggleContinuousMode = () => {
    setContinuousMode(!continuousMode);
    if (!continuousMode) {
      setIsListening(true);
    } else {
      setIsListening(false);
      if (isRecording) {
        stopRecording();
      }
    }
  };

  // Keyboard shortcut
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.code === 'Space' && !e.repeat && !continuousMode) {
        e.preventDefault();
        if (isRecording) {
          stopRecording();
        } else if (connectionState !== 'processing') {
          startRecording();
        }
      }
    };
    
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [isRecording, connectionState, continuousMode]);

  return (
    <div className="app">
      <div className="background-gradient"></div>

      <div className="main-container">
        <header className="header">
          <h1 className="title">Voice AI Assistant</h1>
        </header>
        
        <div className="content-wrapper">
          <div className="voice-interface">
            <div className="status-indicator">
              <div className={`status-dot ${connectionState}`}></div>
              <span className="status-text">
                {connectionState === 'connected' && isRecording && 'Listening...'}
                {connectionState === 'processing' && 'Processing...'}
                {connectionState === 'disconnected' && 'Ready'}
                {connectionState === 'error' && 'Error'}
              </span>
        </div>

            <div className="visualizer">
              {isRecording && (
                <div className="audio-bars">
                  {[...Array(5)].map((_, i) => (
                    <div 
                      key={i} 
                      className="bar" 
                      style={{
                        height: `${20 + (audioLevel * 100 * Math.random())}%`,
                        animationDelay: `${i * 0.1}s`
                      }}
                    />
                  ))}
                </div>
              )}
              {connectionState === 'processing' && (
                <div className="processing-animation">
                  <div className="spinner"></div>
                </div>
              )}
          </div>

          <button
              className={`voice-button ${isRecording ? 'recording' : ''} ${connectionState === 'processing' ? 'processing' : ''}`}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={connectionState === 'processing'}
            >
              <div className="button-content">
              {isRecording ? (
                <>
                  <span className="pulse-ring"></span>
                    <svg className="icon" viewBox="0 0 24 24" fill="currentColor">
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    </svg>
                  </>
                ) : connectionState === 'processing' ? (
                  <svg className="icon rotating" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <circle cx="12" cy="12" r="10" strokeWidth="2" strokeDasharray="32" strokeDashoffset="32" />
                  </svg>
              ) : (
                  <svg className="icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
                </svg>
              )}
            </div>
          </button>

            <p className="help-text">
              {continuousMode ? 'Continuous listening mode - just speak!' : 'Press Space to speak'}
            </p>
            
            {/* Voice Selection */}
            <div className="voice-selection">
              <label>Voice:</label>
              <select 
                value={selectedVoice} 
                onChange={(e) => handleVoiceChange(e.target.value)}
                className="voice-select"
              >
                {Object.keys(availableVoices).map(voice => (
                  <option key={voice} value={voice}>
                    {voice.charAt(0).toUpperCase() + voice.slice(1).replace('_', ' ')} ({availableVoices[voice]})
                  </option>
                ))}
              </select>
            </div>
            
            {/* Continuous Mode Toggle */}
            <div className="continuous-mode">
              <label>
                <input
                  type="checkbox"
                  checked={continuousMode}
                  onChange={toggleContinuousMode}
                />
                Continuous Listening
              </label>
            </div>
            
            {error && (
              <div className="error-message">
                {error}
              </div>
            )}
      </div>

          <div className="transcript-panel">
            <h3 className="transcript-title">Conversation</h3>
            <div className="transcript-content">
              {transcript.map((entry, index) => (
                <div key={index} className={`message ${entry.type}`}>
                  <div className="message-header">
                    <span className="message-sender">
                      {entry.type === 'user' ? 'You' : entry.type === 'agent' ? 'AI' : 'System'}
                    </span>
                    <span className="message-time">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="message-text">{entry.text}</div>
                </div>
              ))}
      </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;