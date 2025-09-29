export async function getAudioDuration(blob) {
  return new Promise((resolve) => {
    const audio = document.createElement('audio');
    audio.src = URL.createObjectURL(blob);
    audio.addEventListener('loadedmetadata', () => {
      resolve(audio.duration || 0);
    });
  });
}

export function visualizeAudio(stream, onLevel) {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const interval = setInterval(() => {
      analyser.getByteTimeDomainData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const val = (dataArray[i] - 128) / 128;
        sum += val * val;
      }
      const rms = Math.sqrt(sum / dataArray.length);
      const level = Math.max(0, Math.min(1, rms * 4));
      onLevel && onLevel(level);
    }, 100);

    return {
      stop() { clearInterval(interval); audioContext.close().catch(() => {}); },
    };
  } catch (e) {
    return { stop() {} };
  }
}

export async function convertToWav(blob) {
  // Browser-side conversion omitted for MVP; backend handles WebM.
  return blob;
}

