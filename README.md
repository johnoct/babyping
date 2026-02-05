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

## Development

Install dev dependencies and run tests:

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

CI runs automatically on pull requests to `main` via GitHub Actions.

## Requirements

- macOS 13+ (Ventura) for Continuity Camera
- iPhone and Mac signed into the same Apple ID
- Python 3.11+
