import { useEffect, useRef } from 'react';

const CONSTRAINTS = {
  audio: {
    sampleRate: 16000,
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
  },
};

const VoiceRecorder = ({
  isRecording,
  onRecordingStart,
  onRecordingStop,
  onRecordingComplete,
  onError,
}) => {
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const volumeIntervalRef = useRef(null);
  const startTimestampRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const startRecording = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
        if (cancelled) return;
        streamRef.current = stream;

        const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        mediaRecorderRef.current = mediaRecorder;
        chunksRef.current = [];

        mediaRecorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            chunksRef.current.push(e.data);
          }
        };

        mediaRecorder.onstop = async () => {
          try {
            const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
            onRecordingComplete && onRecordingComplete(blob);
          } catch (err) {
            onError && onError({ message: err.message || 'Failed to finalize recording', critical: false });
          } finally {
            chunksRef.current = [];
            cleanupStream();
          }
        };

        // Setup volume meter
        try {
          audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
          const source = audioContextRef.current.createMediaStreamSource(stream);
          analyserRef.current = audioContextRef.current.createAnalyser();
          analyserRef.current.fftSize = 256;
          source.connect(analyserRef.current);
          const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
          volumeIntervalRef.current = setInterval(() => {
            analyserRef.current.getByteTimeDomainData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
              const val = (dataArray[i] - 128) / 128;
              sum += val * val;
            }
            const rms = Math.sqrt(sum / dataArray.length);
            const level = Math.max(0, Math.min(1, rms * 4));
            // Consumers can read navigator.mediaSession or we could expose a callback; keeping minimal.
          }, 100);
        } catch (e) {
          // Ignore meter errors
        }

        startTimestampRef.current = Date.now();
        mediaRecorder.start(100); // Start with 100ms timeslice to collect data
        onRecordingStart && onRecordingStart();
      } catch (err) {
        onError && onError({ message: err.message || 'Microphone access denied', critical: true });
      }
    };

    const stopRecording = () => {
      try {
        const mr = mediaRecorderRef.current;
        if (mr && mr.state !== 'inactive') {
          mr.stop();
        }
        onRecordingStop && onRecordingStop();
      } catch (err) {
        onError && onError({ message: err.message || 'Failed to stop recording', critical: false });
      }
    };

    const cleanupStream = () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    };

    if (isRecording) {
      startRecording();
      // Auto-timeout after 2 minutes
      setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          onError && onError({ message: 'Recording timed out after 2 minutes', critical: false });
          try { mediaRecorderRef.current.stop(); } catch (_) {}
        }
      }, 2 * 60 * 1000);
    } else {
      if (mediaRecorderRef.current) {
        stopRecording();
      }
    }

    return () => {
      cancelled = true;
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try { mediaRecorderRef.current.stop(); } catch (_) {}
      }
      if (volumeIntervalRef.current) { clearInterval(volumeIntervalRef.current); volumeIntervalRef.current = null; }
      if (audioContextRef.current) { try { audioContextRef.current.close(); } catch (_) {} audioContextRef.current = null; }
      cleanupStream();
    };
  }, [isRecording, onRecordingStart, onRecordingStop, onRecordingComplete, onError]);

  return null;
};

export default VoiceRecorder;