# BabyPing Web UI Design

**Date:** February 5, 2026
**Status:** Approved

## Overview

A Flask-based local web server that streams the BabyPing camera feed to any browser on the same Wi-Fi. Enables phone check-in when the Mac is the camera, or viewing from any device regardless of setup. Supports both Continuity Camera (iPhone-as-camera) and built-in Mac camera workflows.

## Architecture

Flask web server runs alongside the detection loop in the same process using two threads:

1. **Detection thread** — Existing main loop (capture, detect, notify, save). Also encodes each processed frame to JPEG and stores in a shared buffer.
2. **Flask thread** — Serves web UI and MJPEG stream. Reads frames from shared buffer.

Binds to `0.0.0.0:8080` (configurable with `--port`). Starts automatically — no opt-in flag needed. Startup log prints the URL.

New dependency: `flask`.

## Web UI

Single HTML page, mobile-first, no JS framework. Plain HTML with minimal inline CSS.

### Page Structure

- **Live feed** — `<img src="/stream">` showing MJPEG multipart response. Scales to screen width.
- **Status bar** — Sensitivity, night mode status, last motion time. Polled via `fetch('/status')` every 5 seconds.
- **Snapshots row** — Horizontal scroll of recent thumbnail JPEGs (latest first). Only visible when `--snapshots` is enabled. Tap to view full size.

### Routes

| Route | Purpose |
|---|---|
| `GET /` | HTML page |
| `GET /stream` | MJPEG video stream |
| `GET /status` | JSON: sensitivity, night_mode, last_motion_time, snapshots_enabled |
| `GET /snapshots` | JSON list of snapshot filenames |
| `GET /snapshots/<file>` | Serve a snapshot JPEG |

No authentication — local network only. Read-only, no controls.

## Frame Sharing

A `threading.Lock`-protected variable holds the latest JPEG-encoded frame bytes. Detection thread overwrites it each frame. Flask MJPEG endpoint reads in a loop (~30fps). No queue, no backpressure. Multiple browser clients read from the same buffer independently.

```
display_frame
  ├─ cv2.imshow (existing preview)
  ├─ save_snapshot (if enabled)
  └─ cv2.imencode → shared buffer (new)
```

## New CLI Flag

- `--port` (default: 8080)

## File Structure

- `babyping.py` — Add shared frame buffer, JPEG encoding in main loop
- `web.py` — Flask app (routes, MJPEG generator, HTML template)

## Testing

- Test Flask routes return correct status codes and content types
- Test MJPEG generator yields valid multipart frames
- Test status endpoint returns expected JSON structure
- Test snapshots endpoint lists files from snapshot directory
