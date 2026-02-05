# BabyPing

A lightweight baby monitor that turns your Mac (or iPhone via Continuity Camera) into a motion-detecting video feed with real-time alerts and a web UI you can check from any device on your Wi-Fi.

No cloud. No accounts. No app install. Just `python babyping.py` and open the URL on your phone.

## Features

- **Live video stream** via a local web page — check from your phone, tablet, or another computer
- **Motion detection** with adjustable sensitivity and cooldown between alerts
- **macOS notifications** with sound when motion is detected
- **Night mode** — enhances brightness for dark rooms using adaptive histogram equalization
- **Region of interest** — limit detection to a specific area (interactive or CLI)
- **Snapshot history** — optionally save JPEGs of motion events
- **Feed health indicator** — the web UI shows Live / Delayed / Offline so you know the stream isn't frozen
- **Mobile-friendly** — add to your iPhone home screen for a full-screen app experience

## Quick Start

```bash
pip install -r requirements.txt
python babyping.py
```

Open the URL printed in the terminal (e.g. `http://192.168.1.x:8080`) on any device on the same Wi-Fi.

## Setup

**Option A: Mac's built-in camera**

Just run `python babyping.py`. The Mac webcam is camera index 0 by default.

**Option B: iPhone as camera (Continuity Camera)**

1. Mount your iPhone pointing at the crib
2. Connect iPhone to Mac via USB, or ensure both are on the same Wi-Fi and signed into the same Apple ID
3. Run with `--camera 1` (or try 2, 3 if needed):

```bash
python babyping.py --camera 1
```

Requires macOS 13+ (Ventura) and iOS 16+.

## Options

| Flag | Default | Description |
|---|---|---|
| `--camera` | `0` | Camera index (0 = built-in, 1+ = external/iPhone) |
| `--sensitivity` | `medium` | `low` / `medium` / `high` |
| `--cooldown` | `30` | Seconds between notifications |
| `--no-preview` | off | Run without the desktop preview window |
| `--night-mode` | off | Enhance brightness for dark rooms |
| `--roi` | none | Region of interest as `x,y,w,h` (interactive if omitted) |
| `--snapshots` | off | Save a JPEG on each motion event |
| `--snapshot-dir` | `~/.babyping/events` | Directory for snapshots |
| `--max-snapshots` | `100` | Max snapshots to keep (0 = unlimited) |
| `--port` | `8080` | Web UI port |

## Examples

```bash
# iPhone camera, high sensitivity
python babyping.py --camera 1 --sensitivity high

# Night mode + snapshots enabled
python babyping.py --night-mode --snapshots

# Headless (web UI only, no desktop window)
python babyping.py --no-preview

# Fixed ROI (skip interactive selection)
python babyping.py --roi 100,80,400,300

# Custom port
python babyping.py --port 9090
```

## Web UI

The web UI starts automatically on `0.0.0.0:8080`. Open it from any device on the same network.

The interface shows:
- Full-screen live MJPEG stream
- **Live / Delayed / Offline** indicator tied to actual frame delivery
- Clock with seconds so you can verify the feed isn't frozen
- Motion status with time since last detection
- Sensitivity and night mode indicators
- Expandable recent snapshots gallery (when `--snapshots` is enabled)

On iPhone, tap Share > Add to Home Screen to run it as a full-screen app.

## How It Works

1. Captures video from the camera (built-in or iPhone via Continuity Camera)
2. Converts each frame to grayscale and applies Gaussian blur
3. Computes the absolute difference between consecutive frames
4. Thresholds and dilates the diff to find contours
5. If total contour area exceeds the sensitivity threshold, triggers an alert
6. Sends a macOS notification and optionally saves a snapshot
7. Streams the processed frame (with contour overlays) to the web UI via MJPEG

## Troubleshooting

- **Camera not found:** Try `--camera 0`, `--camera 1`, `--camera 2` etc.
- **Too many false alerts:** Use `--sensitivity low`, increase `--cooldown`, or set a `--roi`
- **iPhone disconnects:** Keep it plugged in via USB and unlocked during initial setup
- **No notifications:** Check macOS Settings > Notifications > Script Editor
- **Web UI not loading:** Make sure your phone is on the same Wi-Fi network as the Mac
- **Stream shows "Offline":** The camera may have disconnected — BabyPing will auto-reconnect

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

CI runs on pull requests via GitHub Actions.

## Requirements

- macOS 13+ (Ventura or later)
- Python 3.9+
- For Continuity Camera: iPhone with iOS 16+ on the same Apple ID

## License

MIT
