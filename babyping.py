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
