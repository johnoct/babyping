import argparse
import sys

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
    return parser.parse_args()


def detect_motion(prev_gray, curr_gray, threshold):
    """Detect motion by frame-diffing. Returns (motion_detected, contours, total_area)."""
    diff = cv2.absdiff(prev_gray, curr_gray)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_area = sum(cv2.contourArea(c) for c in contours)
    return total_area >= threshold, contours, total_area


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


if __name__ == "__main__":
    main()
