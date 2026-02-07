# Auth Design — HTTP Basic Auth + Host Binding

**Issue:** #19
**Date:** 2026-02-06

## Problem
Web UI is accessible to anyone on the network without authentication.

## Solution
Two-layer defense:

1. **`--host` flag** (default `127.0.0.1`) — web server binds to localhost only by default, preventing network access unless explicitly enabled
2. **`--password` flag** — enables HTTP Basic Auth when set

## Why HTTP Basic Auth
- MJPEG streaming uses `<img src="/stream">` which cannot set custom headers → bearer tokens require URL params (leak in logs/history)
- Basic Auth is native to HTTP — browser sends credentials automatically after first prompt
- ~20 lines of code vs 50-100 for token-based auth
- Zero frontend changes needed (browser handles the auth prompt)

## Changes

### `babyping.py`
- Add `--host` arg (default `127.0.0.1`)
- Add `--password` arg (default None)
- Update `start_web_server()` to accept host parameter
- Warning when `--host 0.0.0.0` without `--password`
- Print auth/host status in startup info

### `web.py`
- Add `before_request` hook when `args.password` is set
- Check `request.authorization.password` against configured password
- Return 401 + `WWW-Authenticate: Basic realm="BabyPing"` on failure
- Any username accepted (simplest UX — user only remembers password)

### Tests
- 401 when password set and no auth
- 200 with correct credentials
- 401 with wrong password
- No auth when `--password` not set
- `--host` default is `127.0.0.1`

## Usage Examples
```bash
# Local only (default) — no auth needed
babyping

# Network accessible with auth
babyping --host 0.0.0.0 --password mysecret

# Tailscale remote access with auth
babyping --host 0.0.0.0 --password mysecret
```
