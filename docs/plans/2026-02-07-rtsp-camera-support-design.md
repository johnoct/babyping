# RTSP/IP Camera Support — Design

## Problem
BabyPing only supports local cameras via `cv2.VideoCapture(index)`. Users want to connect IP cameras (Reolink, TP-Link Tapo, Hikvision, etc.) that expose RTSP streams over the network.

## Decision
Support RTSP/IP cameras via a `ThreadedVideoCapture` wrapper. No cloud camera APIs, no multi-camera, no ONVIF discovery.

**Why RTSP:** OpenCV's `cv2.VideoCapture` already accepts RTSP URLs natively. Every major IP camera brand supports RTSP. Cloud camera APIs (Ring, Nest, Arlo) are walled gardens with no official streaming access.

## Design

### Camera Source Abstraction

The `--camera` argument changes from `int` to `str`:
- `--camera 0` — local camera by index (existing, unchanged)
- `--camera rtsp://user:pass@192.168.1.100:554/stream1` — RTSP stream
- `--camera http://192.168.1.100/mjpeg` — HTTP MJPEG stream

New CLI flag: `--rtsp-transport tcp|udp` (default: `tcp`)

A factory function `open_camera_source(source)` detects the format and returns either a plain `cv2.VideoCapture` (local) or `ThreadedVideoCapture` (network).

### ThreadedVideoCapture (~40 lines)

Uses "latest frame" pattern — a daemon thread continuously reads frames, main thread always gets the most recent one. No queue, no buffer buildup.

```
_reader thread:  cap.read() → self._frame (overwrite, continuous)
main thread:     source.read() → returns copy of self._frame
```

- Same API as cv2.VideoCapture: `read()`, `isOpened()`, `release()`, `get()`, `set()`
- `threading.Lock` protects shared frame
- Tracks `_last_frame_time` for health monitoring
- `is_healthy()` returns False if no frame for 10s

### Reconnection

Existing `reconnect_camera()` updated to accept string sources. Same exponential backoff. `ThreadedVideoCapture` releases old capture, creates new one, restarts reader thread.

### Credential Masking

`mask_credentials(url)` replaces `://user:pass@` with `://***:***@` in all print output.

## Files Modified

- **`babyping.py`** — ThreadedVideoCapture class, open_camera_source factory, mask_credentials, updated parse_args/try_open_camera/reconnect_camera/main
- **`tests/test_babyping.py`** — ~15 new tests

No changes to `web.py`, `events.py`, or the web UI.

## Out of Scope

- Multi-camera support (different architecture)
- ONVIF auto-discovery (extra dependency, users can find their RTSP URL)
- Config file (CLI args sufficient for one source)
- Cloud camera APIs (walled gardens, legal risk)
- go2rtc/GStreamer (OpenCV FFmpeg backend is sufficient)

## Tests (~15 new)

- ThreadedVideoCapture: init, read, release, is_healthy, reconnect
- open_camera_source: local index, RTSP URL, HTTP URL, invalid source
- mask_credentials: with creds, without creds, no auth
- Integration: RTSP source through detection loop (mocked)
