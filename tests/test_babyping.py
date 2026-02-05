import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from babyping import detect_motion, parse_args, SENSITIVITY_THRESHOLDS


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

    def test_invalid_sensitivity_rejected(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--sensitivity", "ultra"])
        with pytest.raises(SystemExit):
            parse_args()


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
