import axios from 'axios';

// Setup axios with base URL from env
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000, // Reduced from 30s to 15s for faster failure detection
});

// Request counter for tracking retries
let requestCounter = 0;
let cancelSource = null;
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

// Retry function with exponential backoff and strict limits
const retryRequest = async (fn, maxRetries = 1, baseDelay = 1000) => { // Reduced maxRetries from 2 to 1
  let lastError;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // Don't retry on client errors (4xx) except 408 (timeout)
      if (error.response?.status >= 400 && error.response?.status < 500 && error.response?.status !== 408) {
        throw error;
      }

      // Don't retry on cancellation
      if (axios.isCancel(error)) {
        throw error;
      }

      if (attempt === maxRetries) {
        throw error;
      }

      // Shorter delay to prevent long waits
      const delay = Math.min(baseDelay * Math.pow(1.5, attempt), 3000); // Max 3s delay
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw lastError;
};

export const apiService = {
  // processAudio(audioBlob) function to upload audio with retry logic
  async processAudio(audioBlob) {
    const currentRequestId = ++requestCounter;

    // Debounce rapid calls
    if (debounceTimer) clearTimeout(debounceTimer);

    return new Promise((resolve) => {
      debounceTimer = setTimeout(async () => {
        try {
          // Cancel any pending request
          if (cancelSource) {
            cancelSource.cancel('New recording started, cancel previous request');
          }
          cancelSource = axios.CancelToken.source();

          const result = await retryRequest(async () => {
            const formData = new FormData();
            formData.append('audio_file', audioBlob, 'recording.wav');

            const response = await api.post('/api/v1/process-audio', formData, {
              responseType: 'arraybuffer',
              cancelToken: cancelSource.token,
              timeout: 12000, // 12s timeout per request
            });

            return response;
          });

          const responseAudioBlob = new Blob([result.data], { type: 'audio/wav' });
          const audioUrl = URL.createObjectURL(responseAudioBlob);

          resolve({ success: true, audioUrl, data: result.data });
        } catch (error) {
          // Handle cancellation specifically
          if (axios.isCancel(error)) {
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
      }, 100); // Reduced debounce from 200ms to 100ms
    });
  },

  cancelPendingRequests() {
    if (cancelSource) {
      cancelSource.cancel('Operation canceled by the user');
      cancelSource = null;
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