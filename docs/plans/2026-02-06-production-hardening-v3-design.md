# Production Hardening V3 Design

## Overview

Four targeted fixes addressing gaps found in a production readiness audit. Keeps scope tight — no auth, logging refactor, or CSRF (those are separate efforts).

## Fix 1: Snapshot Path Traversal

**File:** `web.py` — `/snapshots/<filename>` route

Add explicit filename validation before `send_from_directory`:

- Reject filenames containing `..` or `/`
- Return 400 with error JSON
- Defense-in-depth (Flask already prevents most traversal)

**Test:** Confirm `../etc/passwd` returns 400.

## Fix 2: Web Server Health Check

**File:** `babyping.py` — main loop

Extract `start_web_server(flask_app, port)` helper that returns a daemon thread. Use it at startup and in a health check inside the main loop:

- Check `web_thread.is_alive()` each iteration (same pattern as audio health check)
- On failure: print warning, send macOS notification, restart thread
- Avoids duplicating thread creation logic

**Tests:** Mock `is_alive()` returning False, verify restart + notification.

## Fix 3: Disk I/O Error Handling

**3a. Event log writes** — `events.py` `log_event()`

Wrap file write in try/except OSError. Silent pass — dropping an event is better than crashing the monitor.

**3b. Snapshot saving** — `babyping.py` `save_snapshot()`

Wrap entire function body in try/except OSError, return None on failure. Covers `os.makedirs`, `cv2.imwrite`, and glob cleanup.

**3c. Main loop warning** — `babyping.py` motion alert path

When `save_snapshot` returns None and snapshots were enabled, print "Warning: Snapshot save failed — disk may be full".

**Tests:** Mock OSError on file open in event log, verify no crash. Mock imwrite failure, verify warning.

## Fix 4: Fix pyproject.toml

Add `sounddevice>=0.4` to required dependencies. Audio is on by default, so it should install with `pip install .`.

## Files Modified

- `web.py` — path traversal validation
- `babyping.py` — web server helper, health check, snapshot warning, save_snapshot error handling
- `events.py` — log_event error handling
- `pyproject.toml` — add sounddevice
- `tests/test_web.py` — path traversal test
- `tests/test_babyping.py` — web server health, snapshot failure tests
- `tests/test_events.py` — event log disk error test
