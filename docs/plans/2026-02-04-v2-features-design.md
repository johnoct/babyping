# BabyPing V2 Features Design

**Date:** February 4, 2026
**Status:** Approved

## Overview

Four features added to BabyPing in this order: event history, night mode, ROI, menu bar app. The first three are additive changes to the existing script. The menu bar app wraps everything with a native macOS UI.

## 1. Event History

Save a JPEG snapshot when motion triggers a notification (above threshold AND cooldown expired).

**Storage:** `~/.babyping/events/` by default, overridable with `--snapshot-dir`. Directory created automatically on first event.

**Filename format:** `YYYY-MM-DDTHH-MM-SS.jpg` — human-readable, naturally sorted.

**What gets saved:** The frame with contour overlays drawn (same as preview). If night mode is active, the enhanced frame is saved.

**Cleanup:** `--max-snapshots` flag (default: 100). Oldest files deleted when exceeded.

**New CLI flags:**
- `--snapshot-dir PATH` (default: `~/.babyping/events/`)
- `--max-snapshots N` (default: 100, 0 = unlimited)
- `--no-snapshots` to disable entirely

**Terminal output:** Snapshot path appended to the existing motion log line:
```
[2026-02-04T21:38:00] Motion detected — area=3500px² → ~/.babyping/events/2026-02-04T21-38-00.jpg
```

## 2. Night Mode

Boost preview brightness/contrast for dark rooms using CLAHE (Contrast Limited Adaptive Histogram Equalization).

**Scope:** Affects preview display and saved snapshots only. Motion detection pipeline is untouched — it works on grayscale diffs independently.

**Activation:** `--night-mode` CLI flag. No auto-detection.

**Implementation:** After drawing contours, before `imshow` and snapshot save:
1. Convert frame to LAB color space
2. Apply CLAHE to the L (lightness) channel (clip limit 2.0, grid 8x8)
3. Convert back to BGR
4. Display / save the enhanced frame

No new dependencies. ~5 lines of OpenCV code.

## 3. ROI (Region of Interest)

Limit motion detection to a user-defined rectangle (e.g., just the crib). Eliminates false positives from ceiling fans, pets, curtains.

**Selection flow:** On startup (unless `--no-preview`), the first frame displays with a prompt. User draws a rectangle using OpenCV's `selectROI`. Press ENTER to confirm, or ENTER with no selection to skip (full frame).

**Detection change:** Before frame-diffing, both `prev_gray` and `curr_gray` are cropped to the ROI. Contour coordinates are offset back to full-frame position for overlay drawing.

**CLI override:** `--roi x,y,w,h` to skip interactive selection. Example: `--roi 100,80,400,300`.

**Visual indicator:** Green rectangle on preview showing active ROI boundary. Also drawn on saved snapshots.

**No ROI = full frame.** Identical to current behavior. Zero breaking changes.

## 4. Menu Bar App

Native macOS menu bar app using `rumps` as an alternative to the terminal workflow.

**Menu structure:**
```
[icon] BabyPing
├── Status: Monitoring (camera 0)
├── ─────────────────
├── Sensitivity ▶  ● Low / ● Medium / ● High
├── Night Mode      ☐ On
├── ─────────────────
├── Open Events Folder
├── Show Preview Window
├── ─────────────────
├── Quit
```

**Icon states:** Green = monitoring. Red = motion detected. Gray = stopped/error.

**Architecture:** `rumps` provides the menu bar run loop. The existing detection loop runs in a background thread. `rumps` callbacks handle menu interactions.

**ROI selection:** Triggered from a menu item — opens preview with selection prompt, then returns to background monitoring.

**New dependency:** `rumps` (pure Python, pip-installable, macOS-only).

**File structure change:**
- `babyping.py` — detection logic, camera handling, snapshots (importable, no GUI)
- `app.py` — menu bar app entry point, imports from `babyping.py`

The CLI script still works standalone. The menu bar app is an alternative entry point.

## Build Order

1. **Event history** — hooks into existing notification path, no architecture changes
2. **Night mode** — display-only enhancement, ~5 lines
3. **ROI** — adds startup interaction and detection crop, medium complexity
4. **Menu bar app** — rearchitects entry point, wraps all features

Each feature is a separate PR that can be tested independently.
