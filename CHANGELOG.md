# Changelog

All notable changes to BabyPing will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [3.0.0] - 2026-02-07

### Added
- RTSP/IP camera support — `--camera rtsp://user:pass@ip/stream` with threaded frame reader
- `--rtsp-transport tcp|udp` flag for RTSP transport selection
- HTTP Basic Auth for the web UI via `--password`
- `--host` flag to control web UI bind address (default: `127.0.0.1`)
- Credential masking in all log output for RTSP URLs
- Fullscreen stream toggle with double-tap support
- 290 tests (unit, web, integration)

### Changed
- `--camera` accepts both integer indices and RTSP/HTTP URLs (backward compatible)
- Web UI defaults to `127.0.0.1` (localhost only) instead of `0.0.0.0`
- Tailscale IP lookup cached with 60s TTL (avoids subprocess per /status poll)
- EventLog uses in-memory deque — `get_events()` no longer reads from disk
- Event pruning runs periodically (every 100 events) instead of per-event
- JPEG encoding skipped when no web viewers are connected
- Gaussian blur applied after ROI crop instead of before (smaller work area)
- Camera reconnection supports both local and network sources

### Fixed
- Production hardening: snapshot disk errors, web server crash recovery, frame drop handling

## [2.0.0] - 2026-02-06

### Added
- Audio monitoring with auto-calibrating threshold and configurable device/threshold
- Event log with iOS-style bottom sheet (filterable by motion/sound)
- Tailscale integration — auto-detects Tailscale IP and shows "Secure" pill in web UI
- FPS throttle (`--fps`) to reduce CPU/energy usage
- Camera auto-reconnect with exponential backoff on disconnect
- ROI selection from the web UI (draw region directly on the stream)
- Web UI controls: cycle sensitivity and FPS, toggle motion/sound alerts live
- Audio VU meter in the web UI showing live microphone levels
- Browser audio alerts (bell icon) with vibration support
- `--no-audio`, `--audio-device`, `--audio-threshold`, `--max-events` CLI flags

### Changed
- Timeline page replaced with draggable bottom sheet triggered from motion card
- Events sheet supports swipe gestures and snap points (half/full/hidden)

### Fixed
- Production hardening: bug fixes, performance improvements, offline support
- Events sheet no longer shows as always-visible peek

## [1.0.0] - 2026-02-05

### Added
- Live video streaming via local web UI (MJPEG over Flask)
- Motion detection with adjustable sensitivity (low/medium/high)
- macOS notifications with configurable cooldown
- Night mode with CLAHE-based brightness enhancement
- Region of interest (interactive selection or CLI)
- Optional snapshot saving on motion events with auto-cleanup
- Feed health indicator (Live/Delayed/Offline) in web UI
- Camera auto-reconnection on disconnect
- Continuity Camera support (iPhone as webcam via AVFoundation fallback)
- Premium dark web UI with glassmorphism, motion glow effect
- Fullscreen snapshot viewer in web UI
- PWA-ready meta tags for iOS home screen install
