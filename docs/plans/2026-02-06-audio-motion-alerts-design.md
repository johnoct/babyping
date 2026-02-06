# Audio Motion Alerts Design

## Problem

When the MacBook camera is the source and the user monitors from their phone, macOS `osascript` notifications only appear on the Mac — useless when you're in another room.

## Solution

Play an audio chime and vibrate the phone through the web UI when motion is detected. The existing `/status` endpoint already provides `last_motion_time`, so this is entirely frontend — no backend changes needed.

### Why not Web Push?

Web Push (Service Workers + Push API) requires HTTPS. BabyPing runs over HTTP on the LAN (`http://192.168.x.x:8080`), which is not a secure context. Adding self-signed HTTPS would introduce cert management complexity and poor UX on iOS (certificate trust settings). Audio alerts solve the same core problem — phone makes noise when baby moves — with zero setup.

## Design

- **Bell button** in the header (next to clock) — tap to enable/disable audio alerts
- **Web Audio API** generates a two-tone ascending chime (C5 → E5, ~0.45s) — gentle but noticeable
- **Vibration API** pulses the phone on motion (200ms-100ms-200ms pattern)
- **localStorage** persists the mute/unmute preference across page refreshes
- **AudioContext** created on first bell tap (satisfies browser autoplay policy via user gesture)
- **First-poll initialization** prevents false alerts on page load — `lastMotionAlerted` is set to the current `last_motion_time` on first status response

### How it triggers

The existing status polling (every 3s) already fetches `last_motion_time`. When this timestamp is newer than `lastMotionAlerted`, a new motion event occurred (these only fire once per cooldown period, matching when macOS notifications are sent). The chime plays and vibration fires.

### Coexistence

macOS `osascript` notifications continue to work alongside audio alerts. Both fire independently — useful when at the Mac vs. monitoring remotely.

## Files Changed

- `web.py`: Bell button HTML, notify-btn CSS, audio alert JavaScript
- `tests/test_web.py`: 3 new tests (bell button, audio scripts, vibration API in HTML)
