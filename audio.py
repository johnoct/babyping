import threading
import time

import numpy as np
import sounddevice as sd


class AudioMonitor:
    """Captures audio from a microphone, computes RMS level, detects sound events."""

    SAMPLERATE = 44100
    CHUNK_DURATION = 0.1  # 100ms
    CALIBRATION_DURATION = 3.0  # seconds
    CALIBRATION_MARGIN = 2.0  # multiplier above ambient

    def __init__(self, device=None, threshold=None):
        self._device = device
        self._threshold = threshold
        self._lock = threading.Lock()
        self._level = 0.0
        self._last_sound_time = None
        self._running = False
        self._thread = None
        self._stream = None

        # Calibration state
        self._calibrating = threshold is None
        self._calibration_samples = []
        self._calibration_chunk_size = int(self.SAMPLERATE * self.CHUNK_DURATION)
        self._calibration_needed = int(self.CALIBRATION_DURATION / self.CHUNK_DURATION)

    def start(self):
        """Start audio capture in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop audio capture."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_level(self):
        """Get current audio level (0.0 to 1.0)."""
        with self._lock:
            return self._level

    def get_last_sound_time(self):
        """Get timestamp of last detected sound event, or None."""
        with self._lock:
            return self._last_sound_time

    def _run(self):
        """Background thread: open InputStream and block until stopped."""
        chunk_samples = int(self.SAMPLERATE * self.CHUNK_DURATION)
        try:
            with sd.InputStream(
                device=self._device,
                samplerate=self.SAMPLERATE,
                channels=1,
                dtype="float32",
                blocksize=chunk_samples,
                callback=self._audio_callback,
            ):
                while self._running:
                    time.sleep(0.05)
        except Exception as e:
            print(f"Audio error: {e}")
            self._running = False

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio chunk."""
        rms = self._compute_rms(indata)

        # During calibration, collect ambient noise samples
        if self._calibrating:
            self._calibration_samples.append(rms)
            if len(self._calibration_samples) >= self._calibration_needed:
                ambient = np.mean(self._calibration_samples)
                self._threshold = max(ambient * self.CALIBRATION_MARGIN, 0.005)
                self._calibrating = False
            with self._lock:
                self._level = min(rms, 1.0)
            return

        with self._lock:
            self._level = min(rms, 1.0)
            if self._threshold is not None and rms >= self._threshold:
                self._last_sound_time = time.time()

    @staticmethod
    def _compute_rms(data):
        """Compute root-mean-square amplitude of audio data."""
        return float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
