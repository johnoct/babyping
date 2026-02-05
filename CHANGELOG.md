# Changelog

All notable changes to BabyPing will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

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
- 47 tests with GitHub Actions CI
