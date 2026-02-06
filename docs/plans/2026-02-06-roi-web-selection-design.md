# ROI Web Selection Design

## Goal

Allow users to select, reselect, or clear the motion detection Region of Interest (ROI) directly from the web UI, eliminating the need to restart BabyPing or use CLI flags.

## Design Decisions

- **Draw on stream**: Users click/drag a rectangle on the live video feed (most intuitive)
- **Session-only**: ROI resets when BabyPing restarts (matches current CLI behavior, keeps things simple)
- **Overlay only during selection**: The canvas overlay appears while drawing, disappears once confirmed (clean viewing experience; the green ROI rectangle drawn by OpenCV on the stream provides ongoing visibility)

## Architecture

### Backend

**FrameBuffer** gets thread-safe `get_roi()` / `set_roi()` methods. The detection loop reads `frame_buffer.get_roi()` each iteration instead of using a local variable, allowing the web UI to update ROI at any time.

**New endpoint**: `POST /roi` accepts `{"x", "y", "w", "h"}` to set or `null` to clear. Validates non-negative coordinates and positive dimensions.

**Updated endpoint**: `GET /status` now includes `"roi"` field (object or null).

### Frontend

- **ROI button** in the status bar (styled as a status card tag)
- **Canvas overlay** on the stream for drawing rectangles
- **Coordinate mapping** handles `object-fit: cover` scaling (CSS pixels to frame pixels)
- **Touch + mouse** support for mobile and desktop
- **Confirm / Cancel / Clear** actions after drawing
- **Resize safety**: exits ROI mode on window resize to prevent stale coordinate mapping

## API

```
POST /roi
Body: {"x": 10, "y": 20, "w": 100, "h": 80}  ->  sets ROI
Body: null                                      ->  clears ROI
Response: {"roi": {"x": 10, "y": 20, "w": 100, "h": 80}} or {"roi": null}

GET /status
Response: {...existing fields, "roi": {"x":..,"y":..,"w":..,"h":..} | null}
```

## Files Changed

- `babyping.py`: FrameBuffer ROI methods, detection loop reads from buffer
- `web.py`: POST /roi endpoint, status includes ROI, HTML/CSS/JS for selection UI
- `tests/test_babyping.py`: FrameBuffer ROI tests
- `tests/test_web.py`: ROI endpoint and UI tests
