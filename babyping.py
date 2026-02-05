import argparse
import sys

import cv2

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


if __name__ == "__main__":
    main()
