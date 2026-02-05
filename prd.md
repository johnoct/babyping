# BabyPing — Product Requirements Document

**Author:** John  
**Date:** February 4, 2026  
**Status:** Draft  
**Type:** Personal tool (solve-my-own-problem)

---

## 1. Problem Statement

When away from home without a dedicated baby monitor, there's no quick way to turn an iPhone + Mac (already owned) into a functional baby monitor with motion alerts. Existing solutions like CameraController give you a live feed via Continuity Camera but lack the critical monitoring features: motion detection, sound-level alerts, and notifications when something changes.

**The gap:** Live video exists natively via Continuity Camera. Intelligence on top of that feed does not.

---

## 2. Proposed Solution

A lightweight Python script that runs on macOS, captures the Continuity Camera feed from a nearby iPhone, and adds baby-monitor intelligence: frame-diffing for motion detection and macOS-native notifications when thresholds are crossed.

**One script. No iPhone app. No cloud. No account.**

---

## 3. User Flow

1. Mount iPhone pointing at the crib (tripod, propped against object, etc.)
2. Plug iPhone in (camera will stay active)
3. Ensure iPhone + Mac are on same Wi-Fi and signed into same Apple ID
4. Run the Python script on Mac
5. Script opens a small preview window showing the live feed
6. Script monitors in the background — sends macOS notification on detected motion
7. User clicks notification or glances at preview to check on baby
8. Press `q` or `Ctrl+C` to stop

---

## 4. Features

### 4.1 MVP (Build This First)

| Feature | Description | Implementation |
|---|---|---|
| **Live preview** | Small always-on-top window showing camera feed | OpenCV `VideoCapture` selecting iPhone as source via Continuity Camera |
| **Motion detection** | Detect movement in the frame above a configurable threshold | Frame-diffing with Gaussian blur → threshold → contour area calculation |
| **macOS notifications** | Push a native notification when motion is detected | `osascript` or `pync` / `terminal-notifier` |
| **Cooldown period** | Avoid notification spam — configurable quiet period after each alert | Simple timestamp-based cooldown (default: 30 seconds) |
| **Sensitivity control** | Adjustable motion sensitivity via CLI flag | `--sensitivity` flag (low / medium / high) mapping to contour area thresholds |
| **Logging** | Terminal output showing motion events with timestamps | `print()` with ISO timestamps |

### 4.2 V2 (If MVP Works Well)

| Feature | Description |
|---|---|
| **ROI (Region of Interest)** | Click-to-draw a rectangle on the preview to limit detection zone (ignore ceiling fan, pets, etc.) |
| **Audio monitoring** | Capture mic audio from iPhone, trigger alert on sustained loud sound (crying) |
| **Sound classification** | Use a lightweight ML model to distinguish crying from background noise |
| **Menu bar app** | Wrap the script in a macOS menu bar app with thumbnail + status indicator |
| **Event history** | Save motion-triggered snapshots with timestamps to a local folder |
| **Night mode** | Auto-adjust brightness/contrast of preview for dark rooms |
| **Two-way audio** | Play audio through iPhone speaker from Mac (talk to baby) |

### 4.3 Out of Scope

- Any cloud infrastructure or accounts
- iPhone-side app development
- Android / Windows / Linux support
- Recording / video storage (privacy concern, not needed)
- Multi-camera support (one iPhone is enough for now)

---

## 5. Technical Design

### 5.1 Architecture

```
┌─────────────┐    Continuity Camera     ┌──────────────────────────┐
│   iPhone     │ ──────────────────────── │   Mac (Python script)    │
│  (camera)    │    (native macOS)        │                          │
│              │                          │  ┌─ OpenCV capture       │
│              │                          │  ├─ Frame diffing        │
│              │                          │  ├─ Contour analysis     │
│              │                          │  ├─ Notification trigger │
│              │                          │  └─ Preview window       │
└─────────────┘                          └──────────────────────────┘
```

### 5.2 Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Fast to write, good OpenCV bindings |
| Video capture | `opencv-python` | Mature, handles Continuity Camera as standard video source |
| Motion detection | OpenCV frame-diffing | No ML needed, ~5 lines of code, proven approach |
| Notifications | `terminal-notifier` (via Homebrew) or `osascript` | Native macOS notifications, no dependencies if using osascript |
| CLI | `argparse` | Built-in, zero dependencies |
| Preview window | OpenCV `imshow` | Comes free with OpenCV, supports always-on-top |

### 5.3 Motion Detection Algorithm

```
1. Capture frame N and frame N-1
2. Convert both to grayscale
3. Apply Gaussian blur (reduce noise)
4. Compute absolute difference between frames
5. Apply binary threshold (pixel changed? yes/no)
6. Find contours in the thresholded image
7. Sum contour areas → if above threshold → MOTION DETECTED
8. If motion detected AND cooldown expired → fire notification
```

**Sensitivity presets:**

| Preset | Min contour area | Use case |
|---|---|---|
| Low | 5000 px² | Only trigger on large movements (rolling over, standing up) |
| Medium (default) | 2000 px² | General baby movement |
| High | 500 px² | Detect small movements (breathing-level sensitivity) |

### 5.4 Dependencies

```
opencv-python
numpy (comes with opencv)
```

That's it. Two pip packages.

### 5.5 Camera Source Selection

Continuity Camera exposes the iPhone as a standard video source in macOS. OpenCV's `VideoCapture(index)` will pick it up. The script should:

1. List all available cameras on launch
2. Let the user select by index or auto-detect iPhone by name if possible
3. Fall back to `--camera <index>` CLI flag

---

## 6. CLI Interface

```bash
# Basic usage
python babyping.py

# With options
python babyping.py \
  --camera 1 \                    # Camera index (0 = built-in, 1+ = external/iPhone)
  --sensitivity medium \           # low | medium | high
  --cooldown 30 \                  # Seconds between notifications
  --no-preview \                   # Run headless (no preview window)
  --snapshot-dir ~/baby-snapshots  # Save frame on motion event (v2)
```

---

## 7. Success Criteria

| Criteria | Target |
|---|---|
| Time to set up | < 2 minutes from `git clone` to running |
| Latency (feed) | < 500ms (Continuity Camera is near-instant) |
| Motion detection accuracy | No false negatives on baby standing/rolling; < 3 false positives per hour |
| Notification delivery | < 2 seconds from motion to macOS notification |
| Resource usage | < 5% CPU on M-series Mac |
| Battery impact on iPhone | Manageable with cable plugged in |

---

## 8. Known Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Continuity Camera disconnects | Lose feed entirely | Auto-reconnect loop with notification on disconnect |
| False positives from lighting changes | Notification fatigue | Gaussian blur + tunable sensitivity + cooldown |
| OpenCV can't enumerate camera names on macOS | User doesn't know which index is iPhone | Print resolution/FPS of each source to help identify; CLI flag override |
| iPhone screen timeout | Camera may stop | Disable auto-lock on iPhone or use Guided Access |
| Preview window steals focus | Annoying during work | OpenCV `WINDOW_NORMAL` flag + small default size |

---

## 9. Alternatives Considered

| Alternative | Why not |
|---|---|
| **Cloud Baby Monitor (App Store)** | Routes video through cloud servers. Privacy concern. $5/month. |
| **Annie Baby Monitor** | Requires app on both devices. Over-engineered for this use case. |
| **FaceTime (leave call open)** | No motion detection, no alerts, drains battery on both devices. |
| **Build native Swift apps (both sides)** | 10x the effort for a personal tool. Overkill. |
| **WebRTC-based solution** | Needs signaling server. More complexity than frame-diffing on a local feed. |

---

## 10. Implementation Plan

| Phase | Task | Time Estimate |
|---|---|---|
| **1** | Core script: capture → frame-diff → print motion events | 30 min |
| **2** | Add macOS notifications + cooldown | 15 min |
| **3** | Add CLI flags (sensitivity, camera index, cooldown) | 15 min |
| **4** | Preview window with motion overlay (draw contours) | 15 min |
| **5** | Test with actual iPhone + iterate on thresholds | 30 min |
| **Total** | | **~2 hours** |

---

## Self-Review & Vetting

### ✅ What's solid

- **Continuity Camera is real and works.** macOS 13+ natively supports using an iPhone as a webcam. OpenCV can read from it like any video source. This is not speculative.
- **Frame-diffing is proven.** This is the same technique security cameras have used for decades. It's computationally cheap and effective for the "is something moving?" question.
- **Minimal dependencies.** Two pip packages. No cloud. No accounts. No iPhone app to build. This is genuinely fast to build.
- **The algorithm is appropriate for the problem.** Baby monitors don't need ML-grade object detection — they need "did something change in the frame?" which is exactly what frame-diffing solves.

### ⚠️ Risks I'm flagging

1. **Continuity Camera + OpenCV compatibility is the biggest unknown.** I'm confident Continuity Camera works as a video source in macOS apps (confirmed in FaceTime, Zoom, OBS). However, OpenCV's `VideoCapture` on macOS sometimes has quirks with camera enumeration. **Mitigation:** If OpenCV can't grab the feed, fall back to `AVFoundation` via `PyObjC` — slightly more code but guaranteed macOS-native access.

2. **Camera index discovery is janky.** OpenCV doesn't expose camera names on macOS, only indices (0, 1, 2...). You'll have to trial-and-error or print frame sizes to identify which index is the iPhone. **Mitigation:** Could use `system_profiler SPCameraDataType` to list cameras with names and map to indices.

3. **iPhone must stay unlocked and plugged in.** Continuity Camera requires the iPhone screen to be on (or at minimum, not locked). This means disabling auto-lock or using Guided Access. Not a dealbreaker but worth noting in setup instructions.

4. **No audio in MVP.** This is a conscious tradeoff for speed. A baby could be crying without moving much. For V2, capturing the iPhone mic through Continuity Camera's audio stream (which macOS also exposes) would close this gap.

5. **False positives from shadows / lighting.** Frame-diffing is sensitive to gradual lighting changes (sunset, clouds). The Gaussian blur helps but isn't perfect. The ROI feature in V2 would significantly reduce this.

### 🔴 Honest assessment: Will this actually work?

**Yes, with one caveat.** The core loop (Continuity Camera → OpenCV → frame-diff → notification) is sound and each piece is individually proven. The only integration risk is OpenCV's camera capture on macOS, which may require using the AVFoundation backend explicitly (`cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)`). If that doesn't work, a ~20-line PyObjC wrapper would handle it.

**Build time is realistic.** 2 hours for a working MVP is achievable. The algorithm is simple, the dependencies are minimal, and the hardest part (getting video from iPhone to Mac) is already solved by Apple.

**This is not a product — it's a script.** And that's exactly right for the goal. Ship it, use it tonight, iterate if needed.
