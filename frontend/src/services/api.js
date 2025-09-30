import axios from 'axios';

// Setup axios with base URL from env
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000, // Reduced from 30s to 15s for faster failure detection
});

// Request counter for tracking retries
let requestCounter = 0;
let abortController = null;
let debounceTimer = null;

// Add axios interceptors for common errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Request failed:', error);

    // Handle common HTTP errors
    if (error.code === 'ECONNABORTED') {
      error.userMessage = 'Request timed out. Please check your connection and try again.';
    } else if (error.code === 'ERR_NETWORK') {
      error.userMessage = 'Network error. Please check your internet connection.';
    } else if (!error.response) {
      error.userMessage = 'Connection lost. Please check your internet connection.';
    } else {
      // Server responded with error status
      const status = error.response.status;
      if (status >= 500) {
        error.userMessage = 'Server error. Please try again in a moment.';
      } else if (status === 413) {
        error.userMessage = 'File too large. Please try a shorter recording.';
      } else if (status === 400) {
        error.userMessage = error.response.data?.detail || 'Invalid request. Please try again.';
      } else if (status === 503) {
        error.userMessage = error.response.data?.detail || 'Service temporarily unavailable.';
      } else {
        error.userMessage = error.response.data?.detail || 'An error occurred. Please try again.';
      }
    }

    return Promise.reject(error);
  }
);

// No retry logic - fail fast for voice interaction
// Retries add 1-3s of latency on failures which is unacceptable for voice

export const apiService = {
  // processAudio(audioBlob) function to upload audio - no retry for low latency
  async processAudio(audioBlob) {
    const currentRequestId = ++requestCounter;

    // Minimal debounce for rapid calls
    if (debounceTimer) clearTimeout(debounceTimer);

    return new Promise((resolve) => {
      debounceTimer = setTimeout(async () => {
        try {
          // Cancel any pending request
          if (abortController) {
            abortController.abort();
          }
          abortController = new AbortController();

          const formData = new FormData();
          formData.append('audio_file', audioBlob, 'recording.wav');

          const response = await api.post('/api/v1/process-audio', formData, {
            responseType: 'arraybuffer',
            signal: abortController.signal,
            timeout: 15000, // 15s timeout - fail fast
          });

          const responseAudioBlob = new Blob([response.data], { type: 'audio/wav' });
          const audioUrl = URL.createObjectURL(responseAudioBlob);
          const transcript = response.headers?.['x-transcript'] || '';
          const aiText = response.headers?.['x-ai-text'] || '';

          resolve({ success: true, audioUrl, data: response.data, transcript, aiText });
        } catch (error) {
          // Handle cancellation specifically
          if (error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
            resolve({ success: false, error: 'Request cancelled', canRetry: true, type: 'info' });
            return;
          }

          const userMessage = error.userMessage || error.message || 'Unknown error occurred';
          resolve({
            success: false,
            error: userMessage,
            canRetry: !error.response || error.response.status >= 500 || error.response.status === 408,
            type: error.response?.status >= 500 ? 'error' : 'warning'
          });
        }
      }, 20); // Reduced debounce from 100ms to 20ms for minimal delay
    });
  },

  cancelPendingRequests() {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
  },

  async healthCheck() {
    try {
      const response = await api.get('/health');
      return response.data;
    } catch (error) {
      throw new Error(`Health check failed: ${error.userMessage || error.message}`);
    }
  },
};