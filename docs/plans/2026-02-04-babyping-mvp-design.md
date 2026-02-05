# BabyPing MVP Design

**Date:** February 4, 2026
**Status:** Approved

## Overview

A single Python file (`babyping.py`) that captures a Continuity Camera feed from an iPhone, detects motion via frame-diffing, draws contour overlays on a live preview window, and fires macOS notifications via `osascript`.

## Core Loop

1. Open camera (default index 0, configurable via `--camera`)
2. Read frame, convert to grayscale, apply Gaussian blur
3. Diff against previous frame, apply binary threshold, find contours
4. Draw contours on the live frame
5. Display frame in preview window
6. If total contour area > sensitivity threshold AND cooldown expired:
   - Fire macOS notification via `osascript`
   - Log event to terminal with ISO timestamp
   - Reset cooldown timer
7. Repeat until user presses `q` or `Ctrl+C`

## Dependencies

```
opencv-python
numpy
```

Notifications use `osascript` (built into macOS). No other installs.

## CLI Interface

```bash
python babyping.py [options]
```

| Flag | Default | Description |
|---|---|---|
| `--camera` | `0` | Camera index |
| `--sensitivity` | `medium` | `low` / `medium` / `high` |
| `--cooldown` | `30` | Seconds between notifications |
| `--no-preview` | off | Run headless (no window) |

## Sensitivity Thresholds

| Preset | Min contour area | Triggers on |
|---|---|---|
| Low | 5000 px² | Rolling over, standing up |
| Medium | 2000 px² | General movement |
| High | 500 px² | Small movements |

These are starting points to be tuned with the actual iPhone feed.

## Notifications

macOS native notifications via `osascript` subprocess call (`display notification`). Zero additional dependencies.

## Error Handling

- **Camera not found:** Print clear error message and exit
- **Camera disconnects mid-run:** Catch failed read, print warning, attempt reconnect (3 retries), notify user on permanent failure
- **Ctrl+C:** Clean shutdown — release camera, destroy preview window

## Key Implementation Risk

OpenCV + Continuity Camera on macOS. If `cv2.VideoCapture(0)` doesn't pick up the iPhone feed:
1. Try explicit backend: `cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)`
2. Fallback: `PyObjC` + `AVFoundation` wrapper (~20 lines, adds a dependency)

Test camera capture first before writing detection logic.

## File Structure

```
babyping/
├── babyping.py          # Everything
├── requirements.txt     # opencv-python, numpy
└── README.md            # Setup + usage instructions
```

## Deferred to V2

- Camera auto-detection/listing
- Snapshot saving on motion events
- ROI (Region of Interest) selection
- Audio monitoring / cry detection
- Always-on-top preview window
- Menu bar app wrapper
- Night mode
- Two-way audio

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Preview window | Included in MVP | Core to the user experience, not just alerting |
| Motion overlay | Full contour drawing | Helps tune sensitivity thresholds |
| Notifications | `osascript` | Zero dependencies, good enough for MVP |
| Camera selection | `--camera` flag, default 0 | Auto-detection adds complexity without much value |
| Project structure | Single file | Under 300 lines, no need to decompose |
