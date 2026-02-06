# BabyPing

A lightweight baby monitor that turns your Mac (or iPhone via Continuity Camera) into a motion-detecting video feed with real-time alerts and a web UI you can check from any device on your Wi-Fi.

No cloud. No accounts. No app install. Just `python babyping.py` and open the URL on your phone.

<p align="center">
  <img src="assets/hero.png" alt="BabyPing — baby monitor for Mac" width="500">
</p>

## Features

- **Live video stream** via a local web page — check from your phone, tablet, or another computer
- **Motion detection** with adjustable sensitivity and cooldown between alerts
- **Audio monitoring** — detects baby sounds with auto-calibrating threshold
- **macOS notifications** with sound when motion or sound is detected
- **Night mode** — enhances brightness for dark rooms using adaptive histogram equalization
- **Region of interest** — limit detection to a specific area (interactive, CLI, or from the web UI)
- **Snapshot history** — optionally save JPEGs of motion events
- **Event log** — scrollable history of motion and sound events in an iOS-style bottom sheet
- **Web UI controls** — adjust sensitivity, FPS, and toggle motion/sound alerts live from the browser
- **Feed health indicator** — the web UI shows Live / Delayed / Offline so you know the stream isn't frozen
- **FPS throttle** — reduce CPU/energy usage by capping frame rate
- **Tailscale support** — access BabyPing remotely with a green "Secure" indicator
- **Camera auto-reconnect** — exponential backoff reconnection on disconnect
- **Mobile-friendly** — add to your iPhone home screen for a full-screen app experience

## Quick Start

```bash
pip install .
babyping
```

Or without installing:

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
| `--fps` | `10` | Max frames per second (0 = unlimited) |
| `--no-audio` | off | Disable audio monitoring |
| `--audio-device` | system default | Audio input device index |
| `--audio-threshold` | auto | Audio threshold (0-1), omit for auto-calibration |
| `--max-events` | `1000` | Max events to keep in log (0 = unlimited) |

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

# Lower FPS for less CPU usage
python babyping.py --fps 5

# Disable audio monitoring
python babyping.py --no-audio
```

## Web UI

The web UI starts automatically on `0.0.0.0:8080`. Open it from any device on the same network.

The interface shows:
- Full-screen live MJPEG stream
- **Live / Delayed / Offline** indicator tied to actual frame delivery
- Clock with seconds so you can verify the feed isn't frozen
- Motion and sound status with time since last detection
- Audio VU meter showing live microphone levels
- Tappable controls to cycle sensitivity (Low/Medium/High) and FPS (5/10/15/30)
- Toggles to enable/disable motion and sound alerts
- ROI selection — draw a monitoring region directly on the stream
- Events bottom sheet with filterable motion/sound history and snapshot thumbnails
- Browser audio alerts (bell icon) with vibration on supported devices

On iPhone, tap Share > Add to Home Screen to run it as a full-screen app.

## Remote Access via Tailscale

Access BabyPing from anywhere (not just your local Wi-Fi) using [Tailscale](https://tailscale.com):

1. Install Tailscale on the Mac running BabyPing and on your phone/laptop
2. Sign in on both devices with the same Tailscale account
3. Run `babyping` — if Tailscale is connected, the startup log will show a second URL like `http://100.x.x.x:8080 (Tailscale)`
4. Open that `100.x.x.x` URL from any device on your Tailscale network

The web UI shows a green **Secure** pill in the header when accessed over Tailscale. No port forwarding or cloud setup required.

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
pip install -e ".[dev]"
pytest tests/ -v
```

CI runs on pull requests via GitHub Actions.

### Releasing

Releases are tag-based. Push a version tag and GitHub Actions creates the release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow runs tests, extracts notes from `CHANGELOG.md`, and publishes a GitHub Release.

## Requirements

- macOS 13+ (Ventura or later)
- Python 3.9+
- For Continuity Camera: iPhone with iOS 16+ on the same Apple ID

## License

MIT
