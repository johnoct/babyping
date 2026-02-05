import argparse
import glob
import os
import subprocess
import sys
import time
from datetime import datetime

import cv2
import numpy as np

SENSITIVITY_THRESHOLDS = {
    "low": 5000,
    "medium": 2000,
    "high": 500,
}


def parse_args():
    parser = argparse.ArgumentParser(description="BabyPing — lightweight baby monitor with motion detection")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high"], default="medium",
                        help="Motion sensitivity (default: medium)")
    parser.add_argument("--cooldown", type=int, default=30, help="Seconds between notifications (default: 30)")
    parser.add_argument("--no-preview", action="store_true", help="Run without preview window")
    parser.add_argument("--snapshot-dir", default="~/.babyping/events",
                        help="Directory for motion snapshots (default: ~/.babyping/events)")
    parser.add_argument("--max-snapshots", type=int, default=100,
                        help="Max snapshots to keep, 0=unlimited (default: 100)")
    parser.add_argument("--snapshots", action="store_true",
                        help="Enable snapshot saving on motion events")
    parser.add_argument("--night-mode", action="store_true",
                        help="Enhance preview brightness for dark rooms")
    parser.add_argument("--roi", default=None,
                        help="Region of interest as x,y,w,h (interactive selection if omitted)")
    return parser.parse_args()


def detect_motion(prev_gray, curr_gray, threshold):
    """Detect motion by frame-diffing. Returns (motion_detected, contours, total_area)."""
    diff = cv2.absdiff(prev_gray, curr_gray)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_area = sum(cv2.contourArea(c) for c in contours)
    return total_area >= threshold, contours, total_area


def send_notification(title, message):
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}" sound name "Glass"'
    ], capture_output=True)


def save_snapshot(frame, snapshot_dir="~/.babyping/events", max_snapshots=100):
    """Save a frame as a JPEG snapshot. Returns the file path."""
    snapshot_dir = os.path.expanduser(snapshot_dir)
    os.makedirs(snapshot_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filepath = os.path.join(snapshot_dir, f"{timestamp}.jpg")
    success = cv2.imwrite(filepath, frame)
    if not success:
        return None

    if max_snapshots > 0:
        files = sorted(glob.glob(os.path.join(snapshot_dir, "*.jpg")))
        while len(files) > max_snapshots:
            try:
                os.remove(files.pop(0))
            except FileNotFoundError:
                pass

    return filepath


def apply_night_mode(frame):
    """Enhance frame brightness/contrast for dark rooms using CLAHE."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


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


def parse_roi_string(roi_str):
    """Parse 'x,y,w,h' string into tuple. Returns None if input is None."""
    if roi_str is None:
        return None
    parts = roi_str.split(",")
    if len(parts) != 4:
        raise ValueError(f"ROI must be x,y,w,h — got: {roi_str}")
    return tuple(int(p) for p in parts)


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
    print(f"  Camera index: {args.camera}")
    print(f"  Sensitivity:  {args.sensitivity} ({threshold}px² threshold)")
    print(f"  Cooldown:     {args.cooldown}s")
    print(f"  Preview:      {'off' if args.no_preview else 'on'}")
    print(f"  Snapshots:    {args.snapshot_dir + ' (max: ' + str(args.max_snapshots) + ')' if args.snapshots else 'off'}")
    print(f"  Night mode:   {'on' if args.night_mode else 'off'}")

    roi = parse_roi_string(args.roi)
    if roi is None and not args.no_preview:
        roi = select_roi(cap)
    if roi:
        print(f"  ROI:          {roi}")
    print()

    prev_gray = None
    last_alert_time = 0
    consecutive_failures = 0
    max_retries = 3

    try:
        while True:
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

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_gray is not None:
                prev_cropped = crop_to_roi(prev_gray, roi)
                curr_cropped = crop_to_roi(gray, roi)
                motion, contours, area = detect_motion(prev_cropped, curr_cropped, threshold)

                if motion:
                    full_contours = offset_contours(contours, roi)
                    cv2.drawContours(frame, full_contours, -1, (0, 0, 255), 2)

                    now = time.time()
                    if now - last_alert_time >= args.cooldown:
                        timestamp = datetime.now().isoformat(timespec="seconds")
                        snap_msg = ""
                        display_frame = apply_night_mode(frame) if args.night_mode else frame
                        if args.snapshots:
                            snap_path = save_snapshot(display_frame, args.snapshot_dir, args.max_snapshots)
                            if snap_path:
                                snap_msg = f" → {snap_path}"
                        print(f"[{timestamp}] Motion detected — area={area:.0f}px²{snap_msg}")
                        send_notification("BabyPing", f"Motion detected ({area:.0f}px²)")
                        last_alert_time = now

            prev_gray = gray

            if roi:
                x, y, w, h = roi
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 1)

            display_frame = apply_night_mode(frame) if args.night_mode else frame
            if not args.no_preview:
                cv2.imshow("BabyPing", display_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("BabyPing stopped.")


if __name__ == "__main__":
    main()
