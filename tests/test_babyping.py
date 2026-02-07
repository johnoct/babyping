import glob
import sys
import os
import threading

import cv2
import numpy as np
import pytest

import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock, patch

from babyping import apply_night_mode, crop_to_roi, detect_motion, FrameBuffer, get_tailscale_ip, _is_network_source, _tailscale_cache, mask_credentials, offset_contours, open_camera_source, parse_args, parse_roi_string, reconnect_camera, save_snapshot, ThreadedVideoCapture, throttle_fps, try_open_camera, SENSITIVITY_THRESHOLDS


# --- detect_motion tests ---

def make_gray_frame(width=320, height=240, value=0):
    """Create a uniform grayscale frame."""
    return np.full((height, width), value, dtype=np.uint8)


class TestDetectMotion:
    def test_identical_frames_no_motion(self):
        frame = make_gray_frame(value=128)
        detected, contours, area = detect_motion(frame, frame.copy(), threshold=500)
        assert detected is False
        assert area == 0

    def test_different_frames_motion_detected(self):
        prev = make_gray_frame(value=0)
        curr = make_gray_frame(value=0)
        # Draw a white rectangle on the current frame to simulate movement
        curr[50:150, 50:200] = 255
        detected, contours, area = detect_motion(prev, curr, threshold=500)
        assert detected is True
        assert area > 0
        assert len(contours) > 0

    def test_motion_below_threshold_not_detected(self):
        prev = make_gray_frame(value=0)
        curr = make_gray_frame(value=0)
        # Small change — a tiny 5x5 square
        curr[10:15, 10:15] = 255
        detected, _, area = detect_motion(prev, curr, threshold=5000)
        assert detected is False
        assert area < 5000

    def test_motion_above_threshold_detected(self):
        prev = make_gray_frame(value=0)
        curr = make_gray_frame(value=0)
        # Large change — a 200x200 square
        curr[0:200, 0:200] = 255
        detected, _, area = detect_motion(prev, curr, threshold=500)
        assert detected is True
        assert area >= 500


# --- parse_args tests ---

class TestParseArgs:
    def test_defaults(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.camera == "0"
        assert args.sensitivity == "medium"
        assert args.cooldown == 30
        assert args.no_preview is False

    def test_custom_values(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "babyping", "--camera", "2", "--sensitivity", "high",
            "--cooldown", "10", "--no-preview",
        ])
        args = parse_args()
        assert args.camera == "2"
        assert args.sensitivity == "high"
        assert args.cooldown == 10
        assert args.no_preview is True

    def test_snapshot_defaults(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.snapshot_dir == "~/.babyping/events"
        assert args.max_snapshots == 100
        assert args.snapshots is False

    def test_snapshot_custom_values(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "babyping", "--snapshot-dir", "/tmp/snaps",
            "--max-snapshots", "50", "--snapshots",
        ])
        args = parse_args()
        assert args.snapshot_dir == "/tmp/snaps"
        assert args.max_snapshots == 50
        assert args.snapshots is True

    def test_night_mode_default_off(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.night_mode is False

    def test_night_mode_enabled(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--night-mode"])
        args = parse_args()
        assert args.night_mode is True

    def test_invalid_sensitivity_rejected(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--sensitivity", "ultra"])
        with pytest.raises(SystemExit):
            parse_args()

    def test_host_default_localhost(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.host == "127.0.0.1"

    def test_host_custom_value(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--host", "0.0.0.0"])
        args = parse_args()
        assert args.host == "0.0.0.0"

    def test_password_default_none(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.password is None

    def test_password_custom_value(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--password", "secret"])
        args = parse_args()
        assert args.password == "secret"

    def test_roi_default_none(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.roi is None

    def test_roi_custom_value(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--roi", "100,80,400,300"])
        args = parse_args()
        assert args.roi == "100,80,400,300"

    def test_port_default(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.port == 8080

    def test_port_custom(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--port", "9000"])
        args = parse_args()
        assert args.port == 9000


# --- SENSITIVITY_THRESHOLDS tests ---

class TestSensitivityThresholds:
    def test_all_presets_exist(self):
        assert set(SENSITIVITY_THRESHOLDS.keys()) == {"low", "medium", "high"}

    def test_expected_values(self):
        assert SENSITIVITY_THRESHOLDS["low"] == 5000
        assert SENSITIVITY_THRESHOLDS["medium"] == 2000
        assert SENSITIVITY_THRESHOLDS["high"] == 500

    def test_ordering(self):
        assert SENSITIVITY_THRESHOLDS["low"] > SENSITIVITY_THRESHOLDS["medium"] > SENSITIVITY_THRESHOLDS["high"]


# --- save_snapshot tests ---

class TestSaveSnapshot:
    def test_saves_jpg_file(self, tmp_path):
        frame = make_gray_frame(value=128)
        path = save_snapshot(frame, snapshot_dir=str(tmp_path))
        assert path is not None
        assert path.endswith(".jpg")
        assert os.path.exists(path)

    def test_filename_format(self, tmp_path):
        frame = make_gray_frame(value=128)
        path = save_snapshot(frame, snapshot_dir=str(tmp_path))
        filename = os.path.basename(path)
        # Format: YYYY-MM-DDTHH-MM-SS.jpg
        assert len(filename) == 23  # 19 chars + .jpg
        assert filename[4] == "-"
        assert filename[10] == "T"

    def test_creates_directory_if_missing(self, tmp_path):
        nested = str(tmp_path / "deep" / "nested")
        frame = make_gray_frame(value=128)
        path = save_snapshot(frame, snapshot_dir=nested)
        assert os.path.exists(path)

    def test_max_snapshots_enforced(self, tmp_path):
        frame = make_gray_frame(value=128)
        for i in range(5):
            filepath = str(tmp_path / f"2026-01-0{i+1}T00-00-00.jpg")
            cv2.imwrite(filepath, frame)
        save_snapshot(frame, snapshot_dir=str(tmp_path), max_snapshots=3)
        files = sorted(glob.glob(str(tmp_path / "*.jpg")))
        assert len(files) == 3

    def test_max_snapshots_zero_means_unlimited(self, tmp_path):
        frame = make_gray_frame(value=128)
        for i in range(5):
            filepath = str(tmp_path / f"2026-01-0{i+1}T00-00-00.jpg")
            cv2.imwrite(filepath, frame)
        save_snapshot(frame, snapshot_dir=str(tmp_path), max_snapshots=0)
        files = glob.glob(str(tmp_path / "*.jpg"))
        assert len(files) == 6  # 5 existing + 1 new


# --- apply_night_mode tests ---

class TestApplyNightMode:
    def test_output_same_shape_as_input(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        result = apply_night_mode(frame)
        assert result.shape == frame.shape
        assert result.dtype == frame.dtype

    def test_dark_frame_gets_brighter(self):
        # Dark frame (value 20 across all channels)
        frame = np.full((240, 320, 3), 20, dtype=np.uint8)
        result = apply_night_mode(frame)
        assert result.mean() > frame.mean()

    def test_does_not_modify_input_frame(self):
        frame = np.full((240, 320, 3), 50, dtype=np.uint8)
        original = frame.copy()
        apply_night_mode(frame)
        np.testing.assert_array_equal(frame, original)


# --- ROI tests ---

class TestROI:
    def test_crop_to_roi(self):
        frame = np.zeros((240, 320), dtype=np.uint8)
        frame[50:150, 100:250] = 255
        roi = (100, 50, 150, 100)  # x, y, w, h
        cropped = crop_to_roi(frame, roi)
        assert cropped.shape == (100, 150)
        assert cropped.mean() == 255

    def test_crop_to_roi_none_returns_original(self):
        frame = np.zeros((240, 320), dtype=np.uint8)
        result = crop_to_roi(frame, None)
        assert result is frame

    def test_offset_contours(self):
        # A single contour: a rectangle at (0,0)-(10,10) in cropped space
        contour = np.array([[[0, 0]], [[10, 0]], [[10, 10]], [[0, 10]]], dtype=np.int32)
        roi = (50, 30, 100, 100)  # x=50, y=30
        result = offset_contours([contour], roi)
        assert result[0][0][0][0] == 50  # x offset
        assert result[0][0][0][1] == 30  # y offset

    def test_offset_contours_none_roi_unchanged(self):
        contour = np.array([[[5, 5]], [[15, 5]], [[15, 15]], [[5, 15]]], dtype=np.int32)
        result = offset_contours([contour], None)
        np.testing.assert_array_equal(result[0], contour)

    def test_blur_after_crop_matches_full_frame_when_no_roi(self):
        """With no ROI, blur-after-crop should produce same result as blur-before-crop."""
        prev = make_gray_frame(value=0)
        curr = make_gray_frame(value=0)
        curr[50:150, 50:200] = 255

        # Old approach: blur full frame, then crop (no-op with roi=None)
        prev_old = cv2.GaussianBlur(prev, (21, 21), 0)
        curr_old = cv2.GaussianBlur(curr, (21, 21), 0)
        motion_old, _, area_old = detect_motion(prev_old, curr_old, 500)

        # New approach: crop (no-op), then blur
        prev_new = cv2.GaussianBlur(crop_to_roi(prev, None), (21, 21), 0)
        curr_new = cv2.GaussianBlur(crop_to_roi(curr, None), (21, 21), 0)
        motion_new, _, area_new = detect_motion(prev_new, curr_new, 500)

        assert motion_old == motion_new
        assert area_old == area_new

    def test_blur_after_crop_detects_motion_in_roi(self):
        """Blur-after-crop should correctly detect motion within a specified ROI."""
        prev = make_gray_frame(value=0)
        curr = make_gray_frame(value=0)
        # Put motion inside the ROI region
        curr[50:150, 100:250] = 255

        roi = (100, 50, 150, 100)
        prev_cropped = cv2.GaussianBlur(crop_to_roi(prev, roi), (21, 21), 0)
        curr_cropped = cv2.GaussianBlur(crop_to_roi(curr, roi), (21, 21), 0)
        motion, _, area = detect_motion(prev_cropped, curr_cropped, 500)
        assert motion is True
        assert area > 0


# --- parse_roi_string tests ---

class TestParseRoiString:
    def test_valid_roi_string(self):
        assert parse_roi_string("100,80,400,300") == (100, 80, 400, 300)

    def test_none_returns_none(self):
        assert parse_roi_string(None) is None

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_roi_string("100,80")


# --- FrameBuffer tests ---

class TestFrameBuffer:
    def test_initial_state_is_none(self):
        buf = FrameBuffer()
        assert buf.get() is None
        assert buf.get_last_motion_time() is None

    def test_update_and_get(self):
        buf = FrameBuffer()
        buf.update(b"fake-jpeg-data")
        assert buf.get() == b"fake-jpeg-data"

    def test_overwrites_previous(self):
        buf = FrameBuffer()
        buf.update(b"frame1")
        buf.update(b"frame2")
        assert buf.get() == b"frame2"

    def test_last_motion_time(self):
        buf = FrameBuffer()
        buf.set_last_motion_time(12345.0)
        assert buf.get_last_motion_time() == 12345.0

    def test_last_frame_time_initially_none(self):
        buf = FrameBuffer()
        assert buf.get_last_frame_time() is None

    def test_last_frame_time_set_on_update(self):
        buf = FrameBuffer()
        buf.update(b"frame")
        assert buf.get_last_frame_time() is not None
        assert buf.get_last_frame_time() > 0

    def test_roi_initially_none(self):
        buf = FrameBuffer()
        assert buf.get_roi() is None

    def test_set_and_get_roi(self):
        buf = FrameBuffer()
        buf.set_roi((10, 20, 100, 80))
        assert buf.get_roi() == (10, 20, 100, 80)

    def test_clear_roi(self):
        buf = FrameBuffer()
        buf.set_roi((10, 20, 100, 80))
        buf.set_roi(None)
        assert buf.get_roi() is None

    def test_audio_level_initially_zero(self):
        buf = FrameBuffer()
        assert buf.get_audio_level() == 0.0

    def test_set_and_get_audio_level(self):
        buf = FrameBuffer()
        buf.set_audio_level(0.42)
        assert buf.get_audio_level() == 0.42

    def test_last_sound_time_initially_none(self):
        buf = FrameBuffer()
        assert buf.get_last_sound_time() is None

    def test_set_and_get_last_sound_time(self):
        buf = FrameBuffer()
        buf.set_last_sound_time(99999.0)
        assert buf.get_last_sound_time() == 99999.0

    def test_audio_enabled_initially_false(self):
        buf = FrameBuffer()
        assert buf.get_audio_enabled() is False

    def test_set_and_get_audio_enabled(self):
        buf = FrameBuffer()
        buf.set_audio_enabled(True)
        assert buf.get_audio_enabled() is True
        buf.set_audio_enabled(False)
        assert buf.get_audio_enabled() is False

    def test_motion_alerts_enabled_by_default(self):
        buf = FrameBuffer()
        assert buf.get_motion_alerts_enabled() is True

    def test_set_and_get_motion_alerts_enabled(self):
        buf = FrameBuffer()
        buf.set_motion_alerts_enabled(False)
        assert buf.get_motion_alerts_enabled() is False
        buf.set_motion_alerts_enabled(True)
        assert buf.get_motion_alerts_enabled() is True

    def test_sound_alerts_enabled_by_default(self):
        buf = FrameBuffer()
        assert buf.get_sound_alerts_enabled() is True

    def test_set_and_get_sound_alerts_enabled(self):
        buf = FrameBuffer()
        buf.set_sound_alerts_enabled(False)
        assert buf.get_sound_alerts_enabled() is False
        buf.set_sound_alerts_enabled(True)
        assert buf.get_sound_alerts_enabled() is True

    def test_sensitivity_default(self):
        buf = FrameBuffer()
        assert buf.get_sensitivity() == "medium"

    def test_set_and_get_sensitivity(self):
        buf = FrameBuffer()
        buf.set_sensitivity("high")
        assert buf.get_sensitivity() == "high"
        buf.set_sensitivity("low")
        assert buf.get_sensitivity() == "low"

    def test_fps_default(self):
        buf = FrameBuffer()
        assert buf.get_fps() == 10

    def test_set_and_get_fps(self):
        buf = FrameBuffer()
        buf.set_fps(30)
        assert buf.get_fps() == 30
        buf.set_fps(5)
        assert buf.get_fps() == 5

    def test_has_viewers_true_after_get(self):
        buf = FrameBuffer()
        buf.update(b"frame")
        buf.get()
        assert buf.has_viewers() is True

    def test_has_viewers_false_initially(self):
        buf = FrameBuffer()
        assert buf.has_viewers() is False

    def test_has_viewers_false_after_timeout(self):
        buf = FrameBuffer()
        buf.update(b"frame")
        buf.get()
        # Manually expire the last_read_time
        with buf._lock:
            buf._last_read_time = time.monotonic() - 6.0
        assert buf.has_viewers() is False


# --- parse_args audio flag tests ---

class TestParseArgsAudio:
    def test_no_audio_default_off(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.no_audio is False

    def test_no_audio_flag(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--no-audio"])
        args = parse_args()
        assert args.no_audio is True

    def test_audio_device_default_none(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.audio_device is None

    def test_audio_device_custom(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--audio-device", "2"])
        args = parse_args()
        assert args.audio_device == 2

    def test_audio_threshold_default_none(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.audio_threshold is None

    def test_audio_threshold_custom(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--audio-threshold", "0.05"])
        args = parse_args()
        assert args.audio_threshold == 0.05


# --- parse_args --fps tests ---

class TestParseArgsFps:
    def test_fps_default_is_10(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.fps == 10

    def test_fps_custom_value(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--fps", "5"])
        args = parse_args()
        assert args.fps == 5


# --- throttle_fps tests ---

class TestThrottleFps:
    def test_sleeps_to_maintain_target_fps(self):
        """If frame processed instantly, should sleep ~1/fps seconds."""
        target_fps = 10
        frame_start = time.monotonic()
        # Simulate instant processing (frame_start is now)
        throttle_fps(frame_start, target_fps)
        elapsed = time.monotonic() - frame_start
        # Should have waited roughly 0.1s (1/10 fps)
        assert elapsed >= 0.08  # allow small tolerance

    def test_no_sleep_when_processing_exceeds_budget(self):
        """If processing took longer than frame budget, should not sleep."""
        target_fps = 10
        # Simulate frame_start 200ms ago — already over budget
        frame_start = time.monotonic() - 0.2
        before = time.monotonic()
        throttle_fps(frame_start, target_fps)
        after = time.monotonic()
        # Should return almost immediately (< 10ms)
        assert (after - before) < 0.01

    def test_fps_zero_means_no_throttle(self):
        """fps=0 should disable throttling entirely."""
        frame_start = time.monotonic()
        before = time.monotonic()
        throttle_fps(frame_start, 0)
        after = time.monotonic()
        assert (after - before) < 0.01


# --- try_open_camera tests ---

class TestTryOpenCamera:
    def test_returns_cap_when_camera_available(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            result = try_open_camera(0)
        assert result is mock_cap

    def test_returns_none_when_camera_unavailable(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            result = try_open_camera(0)
        assert result is None

    def test_tries_avfoundation_fallback(self):
        mock_cap_fail = MagicMock()
        mock_cap_fail.isOpened.return_value = False
        mock_cap_ok = MagicMock()
        mock_cap_ok.isOpened.return_value = True

        with patch("babyping.cv2.VideoCapture", side_effect=[mock_cap_fail, mock_cap_ok]) as mock_vc:
            result = try_open_camera(0)
        assert result is mock_cap_ok
        assert mock_vc.call_count == 2


# --- reconnect_camera tests ---

class TestReconnectCamera:
    def test_returns_cap_on_first_try(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        with patch("babyping.try_open_camera", return_value=mock_cap):
            result = reconnect_camera(0, max_attempts=3, base_delay=0.01)
        assert result is mock_cap

    def test_retries_with_backoff_then_succeeds(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        with patch("babyping.try_open_camera", side_effect=[None, None, mock_cap]) as mock_try:
            result = reconnect_camera(0, max_attempts=5, base_delay=0.01)
        assert result is mock_cap
        assert mock_try.call_count == 3

    def test_returns_none_after_max_attempts(self):
        with patch("babyping.try_open_camera", return_value=None):
            result = reconnect_camera(0, max_attempts=3, base_delay=0.01)
        assert result is None

    def test_backoff_increases_wait_time(self):
        with patch("babyping.try_open_camera", return_value=None), \
             patch("babyping.time.sleep") as mock_sleep:
            reconnect_camera(0, max_attempts=4, base_delay=1.0)
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        # Exponential: 1, 2, 4, 8 (capped at 60)
        assert delays == [1.0, 2.0, 4.0, 8.0]

    def test_backoff_caps_at_60_seconds(self):
        with patch("babyping.try_open_camera", return_value=None), \
             patch("babyping.time.sleep") as mock_sleep:
            reconnect_camera(0, max_attempts=8, base_delay=10.0)
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        # 10, 20, 40, 60, 60, 60, 60, 60
        assert all(d <= 60 for d in delays)


# --- get_tailscale_ip tests ---

class TestGetTailscaleIp:
    def setup_method(self):
        """Reset the tailscale cache before each test."""
        _tailscale_cache["ip"] = None
        _tailscale_cache["expires"] = 0

    def test_returns_tailscale_ip_when_present(self):
        """Should return 100.x.x.x address from network interfaces."""
        fake_output = (
            "utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1280\n"
            "\tinet 100.85.42.17 --> 100.85.42.17 netmask 0xffffffff\n"
        )
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result = get_tailscale_ip()
        assert result == "100.85.42.17"

    def test_returns_none_when_no_tailscale(self):
        """Should return None when no 100.x.x.x address found."""
        fake_output = (
            "en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n"
            "\tinet 192.168.1.50 netmask 0xffffff00 broadcast 192.168.1.255\n"
        )
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result = get_tailscale_ip()
        assert result is None

    def test_returns_none_on_subprocess_error(self):
        """Should return None if ifconfig fails."""
        with patch("babyping.subprocess.run", side_effect=Exception("command failed")):
            result = get_tailscale_ip()
        assert result is None

    def test_ignores_non_cgnat_100_addresses(self):
        """Should only match 100.64.0.0/10 range (100.64-127.x.x)."""
        fake_output = (
            "en1: flags=8863<UP> mtu 1500\n"
            "\tinet 100.0.0.1 netmask 0xffffff00\n"
        )
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result = get_tailscale_ip()
        assert result is None

    def test_matches_cgnat_boundary_low(self):
        """100.64.0.1 is within CGNAT range."""
        fake_output = "utun3: flags=8051<UP> mtu 1280\n\tinet 100.64.0.1 --> 100.64.0.1 netmask 0xffffffff\n"
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result = get_tailscale_ip()
        assert result == "100.64.0.1"

    def test_matches_cgnat_boundary_high(self):
        """100.127.255.254 is within CGNAT range."""
        fake_output = "utun3: flags=8051<UP> mtu 1280\n\tinet 100.127.255.254 --> 100.127.255.254 netmask 0xffffffff\n"
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result = get_tailscale_ip()
        assert result == "100.127.255.254"

    def test_returns_first_tailscale_ip_if_multiple(self):
        """If multiple Tailscale IPs found, return the first one."""
        fake_output = (
            "utun3: flags=8051<UP> mtu 1280\n"
            "\tinet 100.100.1.1 --> 100.100.1.1 netmask 0xffffffff\n"
            "utun4: flags=8051<UP> mtu 1280\n"
            "\tinet 100.100.2.2 --> 100.100.2.2 netmask 0xffffffff\n"
        )
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result = get_tailscale_ip()
        assert result == "100.100.1.1"


class TestTailscaleIpCache:
    def setup_method(self):
        """Reset the tailscale cache before each test."""
        from babyping import _tailscale_cache
        _tailscale_cache["ip"] = None
        _tailscale_cache["expires"] = 0

    def test_tailscale_ip_cached(self):
        """Second call within TTL should return cached result without subprocess."""
        fake_output = "utun4: flags=8051<UP> mtu 1280\n\tinet 100.85.42.17 --> 100.85.42.17 netmask 0xffffffff\n"
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result1 = get_tailscale_ip()
            result2 = get_tailscale_ip()
        assert result1 == "100.85.42.17"
        assert result2 == "100.85.42.17"
        assert mock_run.call_count == 1  # Only one subprocess call

    def test_tailscale_ip_cache_expires(self):
        """After TTL expires, should call subprocess again."""
        fake_output = "utun4: flags=8051<UP> mtu 1280\n\tinet 100.85.42.17 --> 100.85.42.17 netmask 0xffffffff\n"
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            get_tailscale_ip()
            # Expire the cache
            from babyping import _tailscale_cache
            _tailscale_cache["expires"] = 0
            get_tailscale_ip()
        assert mock_run.call_count == 2

    def test_tailscale_ip_none_cached(self):
        """None result should also be cached."""
        fake_output = "en0: flags=8863<UP> mtu 1500\n\tinet 192.168.1.50 netmask 0xffffff00\n"
        with patch("babyping.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result1 = get_tailscale_ip()
            result2 = get_tailscale_ip()
        assert result1 is None
        assert result2 is None
        assert mock_run.call_count == 1


class TestStartWebServer:
    def test_returns_thread(self):
        from babyping import start_web_server
        from flask import Flask
        app = Flask(__name__)
        thread = start_web_server(app, "127.0.0.1", 9999)
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True

    def test_thread_is_not_started(self):
        from babyping import start_web_server
        from flask import Flask
        app = Flask(__name__)
        thread = start_web_server(app, "127.0.0.1", 9999)
        assert not thread.is_alive()


class TestSaveSnapshotDiskError:
    def test_returns_none_on_os_error(self, tmp_path):
        """save_snapshot should return None if directory creation fails."""
        frame = make_gray_frame(value=128)
        # Use a path that will fail (file exists where dir is expected)
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        result = save_snapshot(frame, snapshot_dir=str(blocker / "subdir"))
        assert result is None


# --- mask_credentials tests ---

class TestMaskCredentials:
    def test_masks_user_and_password(self):
        url = "rtsp://admin:secret@192.168.1.100:554/stream"
        assert mask_credentials(url) == "rtsp://***:***@192.168.1.100:554/stream"

    def test_no_credentials_unchanged(self):
        url = "rtsp://192.168.1.100:554/stream"
        assert mask_credentials(url) == "rtsp://192.168.1.100:554/stream"

    def test_http_url_masked(self):
        url = "http://user:pass@example.com/mjpeg"
        assert mask_credentials(url) == "http://***:***@example.com/mjpeg"

    def test_local_camera_index_unchanged(self):
        assert mask_credentials("0") == "0"


# --- _is_network_source tests ---

class TestIsNetworkSource:
    def test_rtsp_url(self):
        assert _is_network_source("rtsp://192.168.1.100/stream") is True

    def test_http_url(self):
        assert _is_network_source("http://192.168.1.100/mjpeg") is True

    def test_https_url(self):
        assert _is_network_source("https://192.168.1.100/stream") is True

    def test_local_index_string(self):
        assert _is_network_source("0") is False

    def test_integer(self):
        assert _is_network_source(0) is False


# --- ThreadedVideoCapture tests ---

class TestThreadedVideoCapture:
    def test_init_starts_reader_thread(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((240, 320, 3), dtype=np.uint8))
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            tvc = ThreadedVideoCapture("rtsp://fake")
            time.sleep(0.1)  # Let reader thread run
            assert tvc.isOpened() is True
            tvc.release()

    def test_read_returns_latest_frame(self):
        frame = np.full((240, 320, 3), 128, dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, frame)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            tvc = ThreadedVideoCapture("rtsp://fake")
            time.sleep(0.1)
            ret, result = tvc.read()
            assert ret is True
            assert result is not None
            np.testing.assert_array_equal(result, frame)
            tvc.release()

    def test_read_returns_copy_not_reference(self):
        frame = np.full((240, 320, 3), 128, dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, frame)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            tvc = ThreadedVideoCapture("rtsp://fake")
            time.sleep(0.1)
            _, frame1 = tvc.read()
            _, frame2 = tvc.read()
            assert frame1 is not frame2
            tvc.release()

    def test_release_stops_thread(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            tvc = ThreadedVideoCapture("rtsp://fake")
            tvc.release()
            assert tvc._stopped is True

    def test_is_healthy_true_after_frame(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, frame)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            tvc = ThreadedVideoCapture("rtsp://fake")
            time.sleep(0.1)
            assert tvc.is_healthy() is True
            tvc.release()

    def test_is_healthy_false_initially(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # Simulate slow connection — no frames yet
        mock_cap.read.side_effect = lambda: (time.sleep(1) or (False, None))
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            tvc = ThreadedVideoCapture("rtsp://fake")
            assert tvc.is_healthy() is False
            tvc.release()

    def test_is_healthy_false_after_timeout(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, frame)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            tvc = ThreadedVideoCapture("rtsp://fake")
            time.sleep(0.1)
            # Manually expire
            with tvc._lock:
                tvc._last_frame_time = time.monotonic() - 11.0
            assert tvc.is_healthy() is False
            tvc.release()

    def test_sets_rtsp_transport_env(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap), \
             patch.dict(os.environ, {}, clear=False):
            tvc = ThreadedVideoCapture("rtsp://fake", rtsp_transport="udp")
            assert os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS") == "rtsp_transport;udp"
            tvc.release()


# --- open_camera_source tests ---

class TestOpenCameraSource:
    def test_local_camera_index(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        with patch("babyping.try_open_camera", return_value=mock_cap):
            result = open_camera_source("0")
        assert result is mock_cap

    def test_local_camera_not_found_exits(self):
        with patch("babyping.try_open_camera", return_value=None):
            with pytest.raises(SystemExit):
                open_camera_source("0")

    def test_invalid_source_exits(self):
        with pytest.raises(SystemExit):
            open_camera_source("not_a_number_or_url")

    def test_rtsp_url_returns_threaded_capture(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            result = open_camera_source("rtsp://192.168.1.100/stream")
            assert isinstance(result, ThreadedVideoCapture)
            result.release()

    def test_http_url_returns_threaded_capture(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            result = open_camera_source("http://192.168.1.100/mjpeg")
            assert isinstance(result, ThreadedVideoCapture)
            result.release()

    def test_rtsp_url_not_opened_exits(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap.read.return_value = (False, None)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(SystemExit):
                open_camera_source("rtsp://bad-url")


# --- parse_args RTSP tests ---

class TestParseArgsRtsp:
    def test_camera_accepts_rtsp_url(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--camera", "rtsp://192.168.1.100/stream"])
        args = parse_args()
        assert args.camera == "rtsp://192.168.1.100/stream"

    def test_camera_default_is_string_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.camera == "0"
        assert isinstance(args.camera, str)

    def test_rtsp_transport_default_tcp(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.rtsp_transport == "tcp"

    def test_rtsp_transport_udp(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--rtsp-transport", "udp"])
        args = parse_args()
        assert args.rtsp_transport == "udp"

    def test_rtsp_transport_invalid_rejected(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--rtsp-transport", "invalid"])
        with pytest.raises(SystemExit):
            parse_args()


# --- reconnect_camera with RTSP tests ---

class TestReconnectCameraRtsp:
    def test_reconnect_local_camera(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        with patch("babyping.try_open_camera", return_value=mock_cap):
            result = reconnect_camera("0", max_attempts=3, base_delay=0.01)
        assert result is mock_cap

    def test_reconnect_rtsp_camera(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            result = reconnect_camera("rtsp://192.168.1.100/stream", max_attempts=3, base_delay=0.01)
        assert result is not None
        assert isinstance(result, ThreadedVideoCapture)
        result.release()

    def test_reconnect_rtsp_fails_returns_none(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap.read.return_value = (False, None)
        with patch("babyping.cv2.VideoCapture", return_value=mock_cap):
            result = reconnect_camera("rtsp://bad-url", max_attempts=2, base_delay=0.01)
        assert result is None
