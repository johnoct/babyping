# BabyPing MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single-file Python baby monitor that captures Continuity Camera feed, detects motion via frame-diffing with contour overlay, and fires macOS notifications.

**Architecture:** Single file (`babyping.py`) with a main loop that reads frames from OpenCV VideoCapture, diffs consecutive frames to detect motion, draws contours on a preview window, and triggers `osascript` notifications with cooldown. CLI via `argparse`.

**Tech Stack:** Python 3.11+, opencv-python, numpy, osascript (macOS built-in)

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `babyping.py` (skeleton only)

**Step 1: Create requirements.txt**

```
opencv-python
numpy
```

**Step 2: Create babyping.py skeleton with argparse CLI**

```python
import argparse
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="BabyPing — lightweight baby monitor with motion detection")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high"], default="medium",
                        help="Motion sensitivity (default: medium)")
    parser.add_argument("--cooldown", type=int, default=30, help="Seconds between notifications (default: 30)")
    parser.add_argument("--no-preview", action="store_true", help="Run without preview window")
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"BabyPing starting — camera={args.camera}, sensitivity={args.sensitivity}, cooldown={args.cooldown}s")


if __name__ == "__main__":
    main()
```

**Step 3: Install dependencies and verify CLI**

Run: `pip install -r requirements.txt`
Run: `python babyping.py --help`
Expected: Help text showing all four flags

Run: `python babyping.py --sensitivity high --cooldown 10`
Expected: `BabyPing starting — camera=0, sensitivity=high, cooldown=10s`

**Step 4: Commit**

```bash
git add requirements.txt babyping.py
git commit -m "feat: project scaffolding with CLI argument parsing"
```

---

### Task 2: Camera capture and preview window

**Files:**
- Modify: `babyping.py`

**Step 1: Add camera capture and display loop**

Add to `babyping.py` — replace the `main()` function:

```python
import cv2

SENSITIVITY_THRESHOLDS = {
    "low": 5000,
    "medium": 2000,
    "high": 500,
}


def open_camera(index):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print(f"Error: Could not open camera at index {index}")
        sys.exit(1)
    return cap


def main():
    args = parse_args()
    threshold = SENSITIVITY_THRESHOLDS[args.sensitivity]
    print(f"BabyPing starting — camera={args.camera}, sensitivity={args.sensitivity} ({threshold}px²), cooldown={args.cooldown}s")

    cap = open_camera(args.camera)
    print("Camera opened. Press 'q' to quit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Warning: Failed to read frame")
                break

            if not args.no_preview:
                cv2.imshow("BabyPing", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("BabyPing stopped.")
```

**Step 2: Test with built-in webcam**

Run: `python babyping.py`
Expected: Preview window opens showing webcam feed. Press 'q' to quit.

Run: `python babyping.py --no-preview`
Expected: No window opens. Ctrl+C to quit.

**Step 3: Commit**

```bash
git add babyping.py
git commit -m "feat: camera capture with live preview window"
```

---

### Task 3: Motion detection with contour overlay

**Files:**
- Modify: `babyping.py`

**Step 1: Add frame-diffing and contour drawing**

Add the `detect_motion` function and integrate it into the main loop:

```python
import numpy as np


def detect_motion(prev_gray, curr_gray, threshold):
    """Detect motion by frame-diffing. Returns (motion_detected, contours, total_area)."""
    diff = cv2.absdiff(prev_gray, curr_gray)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_area = sum(cv2.contourArea(c) for c in contours)
    return total_area >= threshold, contours, total_area
```

Update the main loop to use it — replace the `while True` block inside `main()`:

```python
    prev_gray = None

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Warning: Failed to read frame")
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_gray is not None:
                motion, contours, area = detect_motion(prev_gray, gray, threshold)

                if motion:
                    cv2.drawContours(frame, contours, -1, (0, 0, 255), 2)

            prev_gray = gray

            if not args.no_preview:
                cv2.imshow("BabyPing", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("BabyPing stopped.")
```

**Step 2: Test motion detection visually**

Run: `python babyping.py --sensitivity high`
Expected: Red contour outlines appear on the preview when you wave your hand. No contours when still.

Run: `python babyping.py --sensitivity low`
Expected: Only large movements trigger contours.

**Step 3: Commit**

```bash
git add babyping.py
git commit -m "feat: motion detection with contour overlay on preview"
```

---

### Task 4: Notifications and cooldown

**Files:**
- Modify: `babyping.py`

**Step 1: Add notification and cooldown logic**

Add the `send_notification` function:

```python
import subprocess
import time
from datetime import datetime


def send_notification(title, message):
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}" sound name "Glass"'
    ], capture_output=True)
```

Update the motion detection block in the main loop — replace the `if motion:` section:

```python
    prev_gray = None
    last_alert_time = 0

    # ... inside the while loop, after detect_motion:

            if prev_gray is not None:
                motion, contours, area = detect_motion(prev_gray, gray, threshold)

                if motion:
                    cv2.drawContours(frame, contours, -1, (0, 0, 255), 2)

                    now = time.time()
                    if now - last_alert_time >= args.cooldown:
                        timestamp = datetime.now().isoformat(timespec="seconds")
                        print(f"[{timestamp}] Motion detected — area={area:.0f}px²")
                        send_notification("BabyPing", f"Motion detected ({area:.0f}px²)")
                        last_alert_time = now
```

**Step 2: Test notifications**

Run: `python babyping.py --cooldown 5 --sensitivity high`
Expected:
- Wave hand in front of camera
- macOS notification appears with "Motion detected" and Glass sound
- Terminal shows `[timestamp] Motion detected — area=XXXpx²`
- No repeat notification for 5 seconds despite continued motion

**Step 3: Commit**

```bash
git add babyping.py
git commit -m "feat: macOS notifications with cooldown on motion detection"
```

---

### Task 5: Camera reconnection logic

**Files:**
- Modify: `babyping.py`

**Step 1: Add reconnection on failed reads**

Replace the simple `break` on failed read with retry logic in the main loop:

```python
    consecutive_failures = 0
    max_retries = 3

    # ... inside the while loop, replace the ret/frame handling:

            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                print(f"Warning: Failed to read frame ({consecutive_failures}/{max_retries})")
                if consecutive_failures >= max_retries:
                    print("Error: Camera disconnected. Attempting to reconnect...")
                    cap.release()
                    time.sleep(2)
                    cap = open_camera(args.camera)
                    consecutive_failures = 0
                    prev_gray = None
                    print("Reconnected.")
                continue
            consecutive_failures = 0
```

**Step 2: Test by briefly covering/uncovering camera**

Run: `python babyping.py`
Expected: Normal operation. If camera is disrupted, see retry messages. Recovery on reconnect.

**Step 3: Commit**

```bash
git add babyping.py
git commit -m "feat: camera reconnection with retry logic"
```

---

### Task 6: Final polish and README

**Files:**
- Modify: `babyping.py` (startup log)
- Create: `README.md`

**Step 1: Add startup summary log**

After camera opens in `main()`, add:

```python
    print(f"  Camera index: {args.camera}")
    print(f"  Sensitivity:  {args.sensitivity} ({threshold}px² threshold)")
    print(f"  Cooldown:     {args.cooldown}s")
    print(f"  Preview:      {'off' if args.no_preview else 'on'}")
    print()
```

**Step 2: Create README.md**

```markdown
# BabyPing

Turn your iPhone + Mac into a baby monitor with motion detection alerts.

Uses Apple's Continuity Camera for the video feed and OpenCV for motion detection. No cloud, no accounts, no iPhone app needed.

## Setup

1. Mount your iPhone pointing at the crib
2. Plug iPhone into Mac (or ensure same Wi-Fi + Apple ID for wireless)
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run:

```bash
python babyping.py
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--camera` | `0` | Camera index (0 = built-in, 1+ = external/iPhone) |
| `--sensitivity` | `medium` | `low` / `medium` / `high` |
| `--cooldown` | `30` | Seconds between notifications |
| `--no-preview` | off | Run without preview window |

## Examples

```bash
# Use iPhone camera (usually index 1), high sensitivity
python babyping.py --camera 1 --sensitivity high

# Quick cooldown for testing
python babyping.py --cooldown 5

# Headless mode (no preview window)
python babyping.py --no-preview
```

## How It Works

1. Captures live video from your iPhone via Continuity Camera
2. Compares consecutive frames to detect movement
3. Draws red contour outlines on the preview where motion is detected
4. Sends a macOS notification when motion exceeds the sensitivity threshold
5. Waits for the cooldown period before sending another alert

## Troubleshooting

- **Camera not found:** Try different `--camera` values (0, 1, 2...)
- **Too many false alerts:** Lower sensitivity with `--sensitivity low` or increase `--cooldown`
- **iPhone disconnects:** Make sure it's plugged in and not locked
- **No notifications:** Check macOS notification settings for "Script Editor"

## Requirements

- macOS 13+ (Ventura) for Continuity Camera
- iPhone and Mac signed into the same Apple ID
- Python 3.11+
```

**Step 3: Full end-to-end test**

Run: `python babyping.py --sensitivity medium --cooldown 10`
Expected:
- Startup log shows all settings
- Preview window opens with live feed
- Motion triggers red contours + notification + terminal log
- Cooldown prevents notification spam
- 'q' or Ctrl+C cleanly exits

**Step 4: Commit**

```bash
git add babyping.py README.md
git commit -m "feat: startup summary log and README with setup instructions"
```
