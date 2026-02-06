import sys
import os
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock, patch, call

from audio import AudioMonitor


class TestAudioMonitorInit:
    def test_default_threshold_is_none(self):
        """Auto-calibrate mode when no threshold provided."""
        with patch("audio.sd"):
            mon = AudioMonitor()
        assert mon._threshold is None

    def test_explicit_threshold_stored(self):
        with patch("audio.sd"):
            mon = AudioMonitor(threshold=0.05)
        assert mon._threshold == 0.05

    def test_default_device_is_none(self):
        with patch("audio.sd"):
            mon = AudioMonitor()
        assert mon._device is None

    def test_custom_device_stored(self):
        with patch("audio.sd"):
            mon = AudioMonitor(device=3)
        assert mon._device == 3

    def test_initial_level_is_zero(self):
        with patch("audio.sd"):
            mon = AudioMonitor()
        assert mon.get_level() == 0.0

    def test_initial_last_sound_time_is_none(self):
        with patch("audio.sd"):
            mon = AudioMonitor()
        assert mon.get_last_sound_time() is None


class TestAudioMonitorStartStop:
    def test_start_opens_stream(self):
        mock_sd = MagicMock()
        with patch("audio.sd", mock_sd):
            mon = AudioMonitor()
            mon.start()
        mock_sd.InputStream.assert_called_once()
        mock_sd.InputStream.return_value.__enter__ = MagicMock()
        # Stream thread should be started
        assert mon._thread is not None
        assert mon._running is True
        mon.stop()

    def test_stop_sets_running_false(self):
        mock_sd = MagicMock()
        with patch("audio.sd", mock_sd):
            mon = AudioMonitor()
            mon._running = True
            mock_thread = MagicMock()
            mon._thread = mock_thread
            mon.stop()
        assert mon._running is False
        mock_thread.join.assert_called_once()

    def test_stop_without_start_is_safe(self):
        with patch("audio.sd"):
            mon = AudioMonitor()
            mon.stop()  # Should not raise


class TestAudioMonitorRMS:
    def test_compute_rms_silence(self):
        """RMS of silence should be 0."""
        with patch("audio.sd"):
            mon = AudioMonitor()
        data = np.zeros((4410, 1), dtype=np.float32)
        assert mon._compute_rms(data) == 0.0

    def test_compute_rms_known_signal(self):
        """RMS of constant 0.5 signal should be 0.5."""
        with patch("audio.sd"):
            mon = AudioMonitor()
        data = np.full((4410, 1), 0.5, dtype=np.float32)
        rms = mon._compute_rms(data)
        assert abs(rms - 0.5) < 0.001

    def test_compute_rms_sine_wave(self):
        """RMS of a sine wave with amplitude 1.0 should be ~0.707."""
        with patch("audio.sd"):
            mon = AudioMonitor()
        t = np.linspace(0, 1, 44100, dtype=np.float32)
        data = np.sin(2 * np.pi * 440 * t).reshape(-1, 1)
        rms = mon._compute_rms(data)
        assert abs(rms - 0.7071) < 0.01


class TestAudioMonitorCallback:
    def test_callback_updates_level(self):
        """Audio callback should update the current level."""
        with patch("audio.sd"):
            mon = AudioMonitor(threshold=0.01)
        # Simulate a loud audio chunk
        data = np.full((4410, 1), 0.3, dtype=np.float32)
        mon._audio_callback(data, None, None, None)
        assert mon.get_level() > 0.0

    def test_callback_detects_sound_above_threshold(self):
        """Sound above threshold should update last_sound_time."""
        with patch("audio.sd"):
            mon = AudioMonitor(threshold=0.01)
        data = np.full((4410, 1), 0.3, dtype=np.float32)
        mon._audio_callback(data, None, None, None)
        assert mon.get_last_sound_time() is not None

    def test_callback_silence_no_sound_time(self):
        """Silence should not update last_sound_time."""
        with patch("audio.sd"):
            mon = AudioMonitor(threshold=0.1)
        data = np.zeros((4410, 1), dtype=np.float32)
        mon._audio_callback(data, None, None, None)
        assert mon.get_last_sound_time() is None

    def test_level_is_normalized_0_to_1(self):
        """Level should be clamped between 0 and 1."""
        with patch("audio.sd"):
            mon = AudioMonitor(threshold=0.01)
        # Very loud signal
        data = np.full((4410, 1), 1.0, dtype=np.float32)
        mon._audio_callback(data, None, None, None)
        level = mon.get_level()
        assert 0.0 <= level <= 1.0


class TestAudioMonitorCalibration:
    def test_calibration_collects_samples(self):
        """During calibration, threshold should remain None until enough samples."""
        with patch("audio.sd"):
            mon = AudioMonitor()  # auto-calibrate mode
        assert mon._threshold is None
        assert mon._calibrating is True

    def test_calibration_sets_threshold_after_enough_samples(self):
        """After 3s worth of samples, threshold should be set."""
        with patch("audio.sd"):
            mon = AudioMonitor()  # auto-calibrate, samplerate=44100

        # Feed ~3s of quiet audio (30 chunks of 100ms at 44100Hz = 4410 samples each)
        quiet_data = np.full((4410, 1), 0.01, dtype=np.float32)
        for _ in range(30):
            mon._audio_callback(quiet_data, None, None, None)

        assert mon._calibrating is False
        assert mon._threshold is not None
        assert mon._threshold > 0

    def test_calibration_threshold_is_above_ambient(self):
        """Calibrated threshold should be above ambient noise level."""
        with patch("audio.sd"):
            mon = AudioMonitor()

        quiet_data = np.full((4410, 1), 0.01, dtype=np.float32)
        for _ in range(30):
            mon._audio_callback(quiet_data, None, None, None)

        ambient_rms = mon._compute_rms(quiet_data)
        assert mon._threshold > ambient_rms


class TestAudioMonitorThreadSafety:
    def test_get_level_is_thread_safe(self):
        """get_level should use the lock."""
        with patch("audio.sd"):
            mon = AudioMonitor()
        # Just verify it works without deadlocking
        mon.get_level()
        mon.get_level()

    def test_get_last_sound_time_is_thread_safe(self):
        with patch("audio.sd"):
            mon = AudioMonitor()
        mon.get_last_sound_time()
        mon.get_last_sound_time()
