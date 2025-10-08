import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  LiveKitRoom,
  useLocalParticipant,
  useRoomContext,
  useTracks,
  RoomAudioRenderer
} from '@livekit/components-react';
import { Track, ConnectionState } from 'livekit-client';
import '@livekit/components-styles';

const BACKEND_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function VoiceAgent() {
  const [token, setToken] = useState('');
  const [serverUrl, setServerUrl] = useState('');
  const [roomName, setRoomName] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [isSpeaking, setIsSpeaking] = useState(false);

  // Audio playback context
  const audioContextRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  // Get LiveKit token from backend
  const getToken = async () => {
    try {
      setError(null);
      const response = await fetch(`${BACKEND_URL}/api/v1/livekit/create-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          participant_name: `user_${Date.now()}`
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to get token: ${response.status}`);
      }

      const data = await response.json();
      console.log('LiveKit token received:', {
        url: data.url,
        room: data.room_name
      });

      setToken(data.token);
      setServerUrl(data.url);
      setRoomName(data.room_name);
      setIsConnected(true);
    } catch (err) {
      console.error('Token error:', err);
      setError(`Failed to connect: ${err.message}`);
    }
  };

  const disconnect = () => {
    setToken('');
    setServerUrl('');
    setRoomName('');
    setIsConnected(false);
    setTranscript([]);
  };

  if (!token || !serverUrl) {
    return (
      <div className="livekit-container">
        <div className="livekit-connect">
          <h2>LiveKit Voice Agent</h2>
          {error && <div className="error-message">{error}</div>}
          <button onClick={getToken} className="connect-button">
            Connect to Voice Agent
          </button>
        </div>
      </div>
    );
  }

  return (
    <LiveKitRoom
      token={token}
      serverUrl={serverUrl}
      connect={true}
      audio={true}
      video={false}
      onDisconnected={disconnect}
      onError={(error) => {
        console.error('LiveKit error:', error);
        setError(error.message);
      }}
    >
      <VoiceAgentUI
        roomName={roomName}
        transcript={transcript}
        setTranscript={setTranscript}
        onDisconnect={disconnect}
      />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

function VoiceAgentUI({ roomName, transcript, setTranscript, onDisconnect }) {
  const room = useRoomContext();
  const { localParticipant } = useLocalParticipant();
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const animationFrameRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const lastBargeInTimeRef = useRef(0);

  // Monitor connection state
  useEffect(() => {
    const handleStateChange = (state) => {
      console.log('Room state changed:', state);
      if (state === ConnectionState.Connected) {
        console.log('Successfully connected to room:', roomName);
      }
    };

    room.on('connectionStateChanged', handleStateChange);
    return () => room.off('connectionStateChanged', handleStateChange);
  }, [room, roomName]);

  // Monitor audio tracks and visualize
  const audioTracks = useTracks([Track.Source.Microphone]);

  useEffect(() => {
    if (audioTracks.length > 0) {
      const track = audioTracks[0];
      if (track.publication?.track) {
        const mediaStream = new MediaStream([track.publication.track.mediaStreamTrack]);

        // Setup audio context for visualization
        if (!audioContextRef.current) {
          audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
        }

        const source = audioContextRef.current.createMediaStreamSource(mediaStream);
        analyserRef.current = audioContextRef.current.createAnalyser();
        analyserRef.current.fftSize = 256;
        source.connect(analyserRef.current);

        visualizeAudio();
      }
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [audioTracks]);

  const visualizeAudio = () => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
    const level = average / 255;
    setAudioLevel(level);

    // Detect speech activity
    const SPEECH_THRESHOLD = 0.1;
    const BARGE_IN_THRESHOLD = 0.02; // Lower threshold for barge-in detection
    const BARGE_IN_MIN_INTERVAL_MS = 300; // Minimum time between barge-in signals

    if (level > SPEECH_THRESHOLD) {
      setIsSpeaking(true);

      // Barge-in detection: user speaking while agent is speaking
      if (isPlayingRef.current && level > BARGE_IN_THRESHOLD) {
        const now = Date.now();
        if (now - lastBargeInTimeRef.current > BARGE_IN_MIN_INTERVAL_MS) {
          console.log('[BARGE-IN] User speaking during TTS playback, level:', level);
          lastBargeInTimeRef.current = now;

          // Send barge-in signal to backend
          try {
            const message = JSON.stringify({ type: "barge_in" });
            localParticipant.publishData(new TextEncoder().encode(message), { reliable: true });
            console.log('[BARGE-IN] Signal sent to backend');
          } catch (err) {
            console.error('[BARGE-IN] Failed to send signal:', err);
          }
        }
      }
    } else {
      setIsSpeaking(false);
    }

    animationFrameRef.current = requestAnimationFrame(visualizeAudio);
  };

  // Handle data messages from server (transcripts, AI responses)
  useEffect(() => {
    let partialTranscriptText = '';
    let partialLLMText = '';

    const handleDataReceived = (payload, participant) => {
      try {
        const decoder = new TextDecoder();
        const message = JSON.parse(decoder.decode(payload));
        console.log('Data received:', message);

        if (message.type === 'asr_partial') {
          // Update partial transcript (growing text)
          partialTranscriptText = message.text;

          // Update or create partial transcript entry
          setTranscript(prev => {
            const filtered = prev.filter(t => t.type !== 'user_partial');
            return [...filtered, {
              type: 'user_partial',
              text: partialTranscriptText,
              timestamp: new Date().toISOString()
            }];
          });
        } else if (message.type === 'asr_final') {
          // Finalize transcript - convert partial to permanent
          if (partialTranscriptText) {
            setTranscript(prev => {
              const filtered = prev.filter(t => t.type !== 'user_partial');
              return [...filtered, {
                type: 'user',
                text: partialTranscriptText,
                timestamp: new Date().toISOString()
              }];
            });
            partialTranscriptText = '';
          }
        } else if (message.type === 'llm_partial') {
          // Update partial LLM response (growing AI text)
          partialLLMText = message.text;

          // Update or create partial LLM entry
          setTranscript(prev => {
            const filtered = prev.filter(t => t.type !== 'agent_partial');
            return [...filtered, {
              type: 'agent_partial',
              text: partialLLMText,
              timestamp: new Date().toISOString()
            }];
          });
        } else if (message.type === 'llm_final') {
          // Finalize LLM response - convert partial to permanent
          if (partialLLMText) {
            setTranscript(prev => {
              const filtered = prev.filter(t => t.type !== 'agent_partial');
              return [...filtered, {
                type: 'agent',
                text: partialLLMText,
                timestamp: new Date().toISOString()
              }];
            });
            partialLLMText = '';
          }
        } else if (message.type === 'transcription') {
          setTranscript(prev => [...prev, {
            type: 'user',
            text: message.text,
            timestamp: new Date().toISOString()
          }]);
        } else if (message.type === 'response') {
          setTranscript(prev => [...prev, {
            type: 'agent',
            text: message.text,
            timestamp: new Date().toISOString()
          }]);
        } else if (message.type === 'tts_chunk') {
          // Handle TTS audio chunk
          handleTTSChunk(message.audio, message.segment, message.frame);
        } else if (message.type === 'agent_interrupted') {
          // Agent was interrupted by user
          console.log('[AGENT-INTERRUPTED] Backend confirmed interruption');

          // Clear audio queue
          audioQueueRef.current = [];

          // Stop current playback
          isPlayingRef.current = false;
          setIsAgentSpeaking(false);

          // Clear partial agent response from transcript
          setTranscript(prev => prev.filter(t => t.type !== 'agent_partial'));
        }
      } catch (err) {
        console.error('Failed to parse data message:', err);
      }
    };

    // Initialize audio context
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }

    // TTS audio chunk handler
    const handleTTSChunk = async (audioB64, segment, frame) => {
      try {
        // Decode base64 audio
        const audioData = Uint8Array.from(atob(audioB64), c => c.charCodeAt(0));

        // Convert to Float32Array for Web Audio
        const pcmData = new Int16Array(audioData.buffer);
        const floatData = new Float32Array(pcmData.length);
        for (let i = 0; i < pcmData.length; i++) {
          floatData[i] = pcmData[i] / 32768.0;
        }

        // Create audio buffer
        const audioBuffer = audioContextRef.current.createBuffer(
          1, // mono
          floatData.length,
          16000 // 16kHz
        );
        audioBuffer.getChannelData(0).set(floatData);

        // Add to queue
        audioQueueRef.current.push(audioBuffer);

        // Start playback if not already playing
        if (!isPlayingRef.current) {
          playAudioQueue();
        }

        if (frame % 25 === 0) {
          console.log(`[TTS-AUDIO] segment=${segment}, frame=${frame}, queue=${audioQueueRef.current.length}`);
        }
      } catch (err) {
        console.error('Failed to decode TTS audio:', err);
      }
    };

    // Play queued audio buffers with audio ducking support
    const playAudioQueue = async () => {
      if (isPlayingRef.current || audioQueueRef.current.length === 0) {
        return;
      }

      isPlayingRef.current = true;
      setIsAgentSpeaking(true);

      // Create gain node for audio ducking
      const gainNode = audioContextRef.current.createGain();
      gainNode.connect(audioContextRef.current.destination);

      while (audioQueueRef.current.length > 0) {
        const buffer = audioQueueRef.current.shift();

        // Create and play buffer source
        const source = audioContextRef.current.createBufferSource();
        source.buffer = buffer;
        source.connect(gainNode);

        // Apply audio ducking if user is speaking
        if (isSpeaking) {
          gainNode.gain.value = 0.3; // Reduce to 30% volume
          console.log('[AUDIO-DUCKING] Reducing AI volume due to user speech');
        } else {
          gainNode.gain.value = 1.0; // Full volume
        }

        // Wait for this chunk to finish
        await new Promise(resolve => {
          source.onended = resolve;
          source.start();
        });
      }

      isPlayingRef.current = false;
      setIsAgentSpeaking(false);
      console.log('[TTS-PLAYBACK] Queue finished');
    };

    room.on('dataReceived', handleDataReceived);
    return () => room.off('dataReceived', handleDataReceived);
  }, [room, setTranscript]);

  // Toggle microphone
  const toggleMicrophone = async () => {
    if (localParticipant) {
      await localParticipant.setMicrophoneEnabled(
        !localParticipant.isMicrophoneEnabled
      );
    }
  };

  const isMicEnabled = localParticipant?.isMicrophoneEnabled ?? false;

  return (
    <div className="voice-agent-ui">
      <div className="status-bar">
        <div className="status-indicator">
          <div className={`status-dot ${room.state === ConnectionState.Connected ? 'connected' : 'disconnected'}`}></div>
          <span>Room: {roomName}</span>
        </div>
        <button onClick={onDisconnect} className="disconnect-button">
          Disconnect
        </button>
      </div>

      <div className="voice-interface">
        <div className="visualizer">
          {isSpeaking && (
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
        </div>

        <button
          className={`voice-button ${isMicEnabled ? 'active' : ''}`}
          onClick={toggleMicrophone}
        >
          <svg className="icon" viewBox="0 0 24 24" fill="currentColor">
            {isMicEnabled ? (
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
            ) : (
              <>
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
                <line x1="1" y1="1" x2="23" y2="23" stroke="currentColor" strokeWidth="2"/>
              </>
            )}
          </svg>
        </button>

        <p className="help-text">
          {isMicEnabled ? 'Microphone Active - Speak now' : 'Click to enable microphone'}
        </p>
      </div>

      <div className="transcript-panel">
        <h3 className="transcript-title">Conversation</h3>
        <div className="transcript-content">
          {transcript.map((entry, index) => (
            <div key={index} className={`message ${entry.type}`}>
              <div className="message-header">
                <span className="message-sender">
                  {entry.type === 'user' ? 'You' : 'AI'}
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
  );
}

export default VoiceAgent;
