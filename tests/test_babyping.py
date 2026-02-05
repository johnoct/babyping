import glob
import sys
import os

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from babyping import apply_night_mode, crop_to_roi, detect_motion, FrameBuffer, offset_contours, parse_args, parse_roi_string, save_snapshot, SENSITIVITY_THRESHOLDS


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
        assert args.camera == 0
        assert args.sensitivity == "medium"
        assert args.cooldown == 30
        assert args.no_preview is False

    def test_custom_values(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "babyping", "--camera", "2", "--sensitivity", "high",
            "--cooldown", "10", "--no-preview",
        ])
        args = parse_args()
        assert args.camera == 2
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
