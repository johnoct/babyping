# V2 Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add event history, night mode, ROI, and menu bar app to BabyPing.

**Architecture:** Four incremental features added to the existing single-file script. Event history, night mode, and ROI are additive changes to `babyping.py`. The menu bar app splits the project into `babyping.py` (logic) and `app.py` (GUI entry point).

**Tech Stack:** OpenCV (CLAHE, selectROI), `os`/`glob` for file management, `rumps` for menu bar app.

---

### Task 1: Event History — save_snapshot function + tests

**Files:**
- Modify: `babyping.py` (add `save_snapshot` function after `send_notification`, around line 43)
- Modify: `tests/test_babyping.py` (add `TestSaveSnapshot` class)

**Step 1: Write the failing tests**

Add to `tests/test_babyping.py`:

```python
import glob

from babyping import save_snapshot


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
            # Create files with staggered names so oldest is deterministic
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
```

Also add `import cv2` and `import glob` to the test file imports, and `save_snapshot` to the import from `babyping`.

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_babyping.py::TestSaveSnapshot -v`
Expected: FAIL with `ImportError: cannot import name 'save_snapshot'`

**Step 3: Write the implementation**

Add to `babyping.py` after the `send_notification` function (after line 42):

```python
import glob
import os

def save_snapshot(frame, snapshot_dir="~/.babyping/events", max_snapshots=100):
    """Save a frame as a JPEG snapshot. Returns the file path."""
    snapshot_dir = os.path.expanduser(snapshot_dir)
    os.makedirs(snapshot_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filepath = os.path.join(snapshot_dir, f"{timestamp}.jpg")
    cv2.imwrite(filepath, frame)

    if max_snapshots > 0:
        files = sorted(glob.glob(os.path.join(snapshot_dir, "*.jpg")))
        while len(files) > max_snapshots:
            os.remove(files.pop(0))

    return filepath
```

Move `import glob` and `import os` to the top of the file with other stdlib imports.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_babyping.py::TestSaveSnapshot -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add babyping.py tests/test_babyping.py
git commit -m "feat: add save_snapshot function with cleanup"
```

---

### Task 2: Event History — CLI flags + integration into main loop

**Files:**
- Modify: `babyping.py` (update `parse_args` and `main`)
- Modify: `tests/test_babyping.py` (update `TestParseArgs`)

**Step 1: Write the failing tests**

Add to `TestParseArgs` in `tests/test_babyping.py`:

```python
    def test_snapshot_defaults(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.snapshot_dir == "~/.babyping/events"
        assert args.max_snapshots == 100
        assert args.no_snapshots is False

    def test_snapshot_custom_values(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "babyping", "--snapshot-dir", "/tmp/snaps",
            "--max-snapshots", "50", "--no-snapshots",
        ])
        args = parse_args()
        assert args.snapshot_dir == "/tmp/snaps"
        assert args.max_snapshots == 50
        assert args.no_snapshots is True
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_babyping.py::TestParseArgs::test_snapshot_defaults -v`
Expected: FAIL with `AttributeError: 'Namespace' object has no attribute 'snapshot_dir'`

**Step 3: Write the implementation**

Add to `parse_args()` in `babyping.py`, after the `--no-preview` argument:

```python
    parser.add_argument("--snapshot-dir", default="~/.babyping/events",
                        help="Directory for motion snapshots (default: ~/.babyping/events)")
    parser.add_argument("--max-snapshots", type=int, default=100,
                        help="Max snapshots to keep, 0=unlimited (default: 100)")
    parser.add_argument("--no-snapshots", action="store_true",
                        help="Disable snapshot saving")
```

In `main()`, update the notification block (around line 100-104) to also save a snapshot:

```python
                    now = time.time()
                    if now - last_alert_time >= args.cooldown:
                        timestamp = datetime.now().isoformat(timespec="seconds")
                        snap_msg = ""
                        if not args.no_snapshots:
                            snap_path = save_snapshot(frame, args.snapshot_dir, args.max_snapshots)
                            snap_msg = f" → {snap_path}"
                        print(f"[{timestamp}] Motion detected — area={area:.0f}px²{snap_msg}")
                        send_notification("BabyPing", f"Motion detected ({area:.0f}px²)")
                        last_alert_time = now
```

Add snapshot info to the startup log:

```python
    print(f"  Snapshots:    {'off' if args.no_snapshots else args.snapshot_dir} (max: {args.max_snapshots})")
```

**Step 4: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 5: Update existing parse_args tests for new defaults**

Update `test_defaults` to also assert the new fields. Update `test_custom_values` to include snapshot flags.

**Step 6: Run all tests again**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add babyping.py tests/test_babyping.py
git commit -m "feat: integrate event history into CLI and main loop"
```

---

### Task 3: Night Mode — apply_night_mode function + tests

**Files:**
- Modify: `babyping.py` (add `apply_night_mode` function)
- Modify: `tests/test_babyping.py` (add `TestApplyNightMode` class)

**Step 1: Write the failing tests**

Add to `tests/test_babyping.py`:

```python
from babyping import apply_night_mode


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
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_babyping.py::TestApplyNightMode -v`
Expected: FAIL with `ImportError: cannot import name 'apply_night_mode'`

**Step 3: Write the implementation**

Add to `babyping.py` after `save_snapshot`:

```python
def apply_night_mode(frame):
    """Enhance frame brightness/contrast for dark rooms using CLAHE."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_babyping.py::TestApplyNightMode -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add babyping.py tests/test_babyping.py
git commit -m "feat: add apply_night_mode function using CLAHE"
```

---

### Task 4: Night Mode — CLI flag + integration into main loop

**Files:**
- Modify: `babyping.py` (update `parse_args` and `main`)
- Modify: `tests/test_babyping.py` (update `TestParseArgs`)

**Step 1: Write the failing test**

Add to `TestParseArgs`:

```python
    def test_night_mode_default_off(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.night_mode is False

    def test_night_mode_enabled(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--night-mode"])
        args = parse_args()
        assert args.night_mode is True
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_babyping.py::TestParseArgs::test_night_mode_default_off -v`
Expected: FAIL with `AttributeError`

**Step 3: Write the implementation**

Add to `parse_args()`:

```python
    parser.add_argument("--night-mode", action="store_true",
                        help="Enhance preview brightness for dark rooms")
```

In `main()`, after drawing contours and before `imshow` and `save_snapshot`, apply night mode to a display copy:

```python
            display_frame = frame
            if args.night_mode:
                display_frame = apply_night_mode(frame)

            if not args.no_preview:
                cv2.imshow("BabyPing", display_frame)
```

Use `display_frame` instead of `frame` for snapshot saving too.

Add to startup log:

```python
    print(f"  Night mode:   {'on' if args.night_mode else 'off'}")
```

**Step 4: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add babyping.py tests/test_babyping.py
git commit -m "feat: integrate night mode into CLI and main loop"
```

---

### Task 5: ROI — crop_to_roi + offset_contours functions + tests

**Files:**
- Modify: `babyping.py` (add `crop_to_roi` and `offset_contours` functions)
- Modify: `tests/test_babyping.py` (add `TestROI` class)

**Step 1: Write the failing tests**

Add to `tests/test_babyping.py`:

```python
from babyping import crop_to_roi, offset_contours


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
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_babyping.py::TestROI -v`
Expected: FAIL with `ImportError`

**Step 3: Write the implementation**

Add to `babyping.py` after `apply_night_mode`:

```python
def crop_to_roi(frame, roi):
    """Crop frame to ROI (x, y, w, h). Returns original frame if roi is None."""
    if roi is None:
        return frame
    x, y, w, h = roi
    return frame[y:y+h, x:x+w]


def offset_contours(contours, roi):
    """Offset contour coordinates back to full-frame position."""
    if roi is None:
        return contours
    x, y, _, _ = roi
    return [c + np.array([x, y]) for c in contours]
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_babyping.py::TestROI -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add babyping.py tests/test_babyping.py
git commit -m "feat: add crop_to_roi and offset_contours functions"
```

---

### Task 6: ROI — CLI flag, interactive selection, integration into main loop

**Files:**
- Modify: `babyping.py` (update `parse_args`, add `select_roi`, update `main`)
- Modify: `tests/test_babyping.py` (update `TestParseArgs`, add ROI parsing test)

**Step 1: Write the failing tests**

Add to `TestParseArgs`:

```python
    def test_roi_default_none(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping"])
        args = parse_args()
        assert args.roi is None

    def test_roi_custom_value(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["babyping", "--roi", "100,80,400,300"])
        args = parse_args()
        assert args.roi == "100,80,400,300"
```

Add a new test class for ROI parsing:

```python
from babyping import parse_roi_string


class TestParseRoiString:
    def test_valid_roi_string(self):
        assert parse_roi_string("100,80,400,300") == (100, 80, 400, 300)

    def test_none_returns_none(self):
        assert parse_roi_string(None) is None

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_roi_string("100,80")
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_babyping.py::TestParseRoiString -v`
Expected: FAIL with `ImportError`

**Step 3: Write the implementation**

Add `parse_roi_string` to `babyping.py`:

```python
def parse_roi_string(roi_str):
    """Parse 'x,y,w,h' string into tuple. Returns None if input is None."""
    if roi_str is None:
        return None
    parts = roi_str.split(",")
    if len(parts) != 4:
        raise ValueError(f"ROI must be x,y,w,h — got: {roi_str}")
    return tuple(int(p) for p in parts)
```

Add to `parse_args()`:

```python
    parser.add_argument("--roi", default=None,
                        help="Region of interest as x,y,w,h (interactive selection if omitted)")
```

Add `select_roi` function (uses OpenCV's built-in `selectROI`):

```python
def select_roi(cap):
    """Show first frame and let user draw ROI. Returns (x,y,w,h) or None if skipped."""
    ret, frame = cap.read()
    if not ret:
        return None
    print("Draw ROI and press ENTER, or press ENTER to skip.")
    roi = cv2.selectROI("BabyPing — Select ROI", frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("BabyPing — Select ROI")
    if roi == (0, 0, 0, 0):
        return None
    return roi
```

In `main()`, after opening the camera and before the main loop:

```python
    roi = parse_roi_string(args.roi)
    if roi is None and not args.no_preview:
        roi = select_roi(cap)
    if roi:
        print(f"  ROI:          {roi}")
```

In the detection section of the main loop, crop frames before detection:

```python
            if prev_gray is not None:
                prev_cropped = crop_to_roi(prev_gray, roi)
                curr_cropped = crop_to_roi(gray, roi)
                motion, contours, area = detect_motion(prev_cropped, curr_cropped, threshold)

                if motion:
                    full_contours = offset_contours(contours, roi)
                    cv2.drawContours(frame, full_contours, -1, (0, 0, 255), 2)
                    if roi:
                        x, y, w, h = roi
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 1)
```

Draw the ROI boundary on every frame (not just motion frames) — move the rectangle draw outside the `if motion` block.

**Step 4: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add babyping.py tests/test_babyping.py
git commit -m "feat: integrate ROI selection into CLI and main loop"
```

---

### Task 7: Menu Bar App — split babyping.py into importable module

**Files:**
- Modify: `babyping.py` (ensure all functions are importable, guard `main()` behind `__name__`)
- No test changes needed — existing tests already import functions directly

**Step 1: Verify current imports work**

Run: `python3 -c "from babyping import detect_motion, save_snapshot, apply_night_mode, crop_to_roi, offset_contours, parse_roi_string; print('OK')"`
Expected: `OK`

This should already work since functions are at module level and `main()` is behind `if __name__ == "__main__"`. If it works, no changes needed.

**Step 2: Run all tests to confirm nothing broke**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 3: Commit (only if changes were needed)**

```bash
git commit -m "refactor: ensure babyping.py is importable as module" --allow-empty
```

---

### Task 8: Menu Bar App — app.py with rumps

**Files:**
- Create: `app.py`
- Modify: `requirements.txt` (add `rumps`)
- Create: `tests/test_app.py`

**Step 1: Write the failing tests**

Create `tests/test_app.py`:

```python
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import BabyPingApp


class TestBabyPingApp:
    def test_app_has_required_menu_items(self):
        app = BabyPingApp()
        menu_titles = [item.title if hasattr(item, 'title') else str(item) for item in app.menu]
        assert "Open Events Folder" in menu_titles
        assert "Show Preview" in menu_titles

    def test_default_sensitivity_is_medium(self):
        app = BabyPingApp()
        assert app.sensitivity == "medium"

    def test_default_night_mode_is_off(self):
        app = BabyPingApp()
        assert app.night_mode is False
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

**Step 3: Write the implementation**

Create `app.py`:

```python
import os
import subprocess
import threading
import time
from datetime import datetime

import cv2
import rumps

from babyping import (
    SENSITIVITY_THRESHOLDS,
    apply_night_mode,
    crop_to_roi,
    detect_motion,
    offset_contours,
    open_camera,
    save_snapshot,
    select_roi,
)

DEFAULT_SNAPSHOT_DIR = "~/.babyping/events"
DEFAULT_MAX_SNAPSHOTS = 100


class BabyPingApp(rumps.App):
    def __init__(self):
        super().__init__("BabyPing", icon=None, quit_button=None)
        self.sensitivity = "medium"
        self.night_mode = False
        self.monitoring = False
        self.camera_index = 0
        self.roi = None
        self.snapshot_dir = DEFAULT_SNAPSHOT_DIR
        self.max_snapshots = DEFAULT_MAX_SNAPSHOTS
        self.preview_visible = False
        self._monitor_thread = None

        self.menu = [
            rumps.MenuItem("Status: Idle"),
            None,  # separator
            rumps.MenuItem("Start Monitoring", callback=self.toggle_monitoring),
            None,
            rumps.MenuItem("Sensitivity: Low", callback=lambda _: self.set_sensitivity("low")),
            rumps.MenuItem("Sensitivity: Medium", callback=lambda _: self.set_sensitivity("medium")),
            rumps.MenuItem("Sensitivity: High", callback=lambda _: self.set_sensitivity("high")),
            None,
            rumps.MenuItem("Night Mode", callback=self.toggle_night_mode),
            rumps.MenuItem("Set ROI...", callback=self.set_roi),
            None,
            rumps.MenuItem("Open Events Folder", callback=self.open_events_folder),
            rumps.MenuItem("Show Preview", callback=self.toggle_preview),
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        self._update_sensitivity_marks()

    def set_sensitivity(self, level):
        self.sensitivity = level
        self._update_sensitivity_marks()

    def _update_sensitivity_marks(self):
        for level in ["Low", "Medium", "High"]:
            item = self.menu[f"Sensitivity: {level}"]
            item.state = 1 if level.lower() == self.sensitivity else 0

    def toggle_night_mode(self, sender):
        self.night_mode = not self.night_mode
        sender.state = 1 if self.night_mode else 0

    def toggle_monitoring(self, sender):
        if self.monitoring:
            self.monitoring = False
            sender.title = "Start Monitoring"
            self.menu["Status: Idle"].title = "Status: Idle"
        else:
            self.monitoring = True
            sender.title = "Stop Monitoring"
            self.menu["Status: Idle"].title = f"Status: Monitoring (camera {self.camera_index})"
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

    def _monitor_loop(self):
        cap = open_camera(self.camera_index)
        threshold = SENSITIVITY_THRESHOLDS[self.sensitivity]
        prev_gray = None
        last_alert_time = 0
        cooldown = 30

        try:
            while self.monitoring:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.5)
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                if prev_gray is not None:
                    prev_cropped = crop_to_roi(prev_gray, self.roi)
                    curr_cropped = crop_to_roi(gray, self.roi)
                    motion, contours, area = detect_motion(prev_cropped, curr_cropped, threshold)

                    if motion:
                        full_contours = offset_contours(contours, self.roi)
                        cv2.drawContours(frame, full_contours, -1, (0, 0, 255), 2)

                        now = time.time()
                        if now - last_alert_time >= cooldown:
                            display_frame = apply_night_mode(frame) if self.night_mode else frame
                            save_snapshot(display_frame, self.snapshot_dir, self.max_snapshots)
                            rumps.notification("BabyPing", "", f"Motion detected ({area:.0f}px²)")
                            last_alert_time = now

                    if self.roi:
                        x, y, w, h = self.roi
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 1)

                prev_gray = gray

                if self.preview_visible:
                    display_frame = apply_night_mode(frame) if self.night_mode else frame
                    cv2.imshow("BabyPing", display_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        self.preview_visible = False
                        cv2.destroyAllWindows()
                else:
                    cv2.waitKey(1)
        finally:
            cap.release()
            cv2.destroyAllWindows()

    def toggle_preview(self, sender):
        self.preview_visible = not self.preview_visible
        if not self.preview_visible:
            cv2.destroyAllWindows()

    def set_roi(self, _):
        if not self.monitoring:
            rumps.alert("Start monitoring first, then set ROI.")
            return
        # ROI selection happens in the preview window via the monitor thread
        self.preview_visible = True

    def open_events_folder(self, _):
        path = os.path.expanduser(self.snapshot_dir)
        os.makedirs(path, exist_ok=True)
        subprocess.run(["open", path])


def main():
    BabyPingApp().run()


if __name__ == "__main__":
    main()
```

Add `rumps` to `requirements.txt`.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: PASS (3 tests)

**Step 5: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add app.py tests/test_app.py requirements.txt
git commit -m "feat: add menu bar app with rumps"
```

---

### Task 9: Update README and docs

**Files:**
- Modify: `README.md`
- Modify: `requirements.txt`

**Step 1: Update README**

Add sections for:
- New CLI flags (`--snapshot-dir`, `--max-snapshots`, `--no-snapshots`, `--night-mode`, `--roi`)
- Menu bar app usage (`python app.py`)
- Updated Options table

**Step 2: Update requirements.txt**

Ensure `rumps` is listed.

**Step 3: Run all tests one final time**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add README.md requirements.txt
git commit -m "docs: update README with V2 features and menu bar app"
```

---

### Task 10: Final PR

**Step 1: Push branch**

```bash
git push -u origin feat/v2-features
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: V2 — event history, night mode, ROI, menu bar app" --body "..."
```
