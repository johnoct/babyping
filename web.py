import glob
import os
import time

from flask import Flask, Response, jsonify, request, send_from_directory

from babyping import get_tailscale_ip


def create_app(args, frame_buffer=None, event_log=None):
    """Create Flask app for the BabyPing web UI."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return HTML_TEMPLATE

    @app.route("/stream")
    def stream():
        target_fps = args.fps if args.fps > 0 else 30
        stream_interval = 1.0 / target_fps

        def generate():
            while True:
                frame_bytes = frame_buffer.get()
                if frame_bytes is not None:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                time.sleep(stream_interval)

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/status")
    def status():
        last_motion = frame_buffer.get_last_motion_time()
        last_frame = frame_buffer.get_last_frame_time()
        roi = frame_buffer.get_roi()
        return jsonify({
            "sensitivity": args.sensitivity,
            "night_mode": args.night_mode,
            "snapshots_enabled": args.snapshots,
            "last_motion_time": last_motion,
            "last_frame_time": last_frame,
            "roi": {"x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3]} if roi else None,
            "tailscale_ip": get_tailscale_ip(),
            "audio_level": frame_buffer.get_audio_level(),
            "last_sound_time": frame_buffer.get_last_sound_time(),
            "audio_enabled": frame_buffer.get_audio_enabled(),
            "motion_alerts": frame_buffer.get_motion_alerts_enabled(),
            "sound_alerts": frame_buffer.get_sound_alerts_enabled(),
        })

    @app.route("/roi", methods=["POST"])
    def set_roi():
        data = request.get_json(force=True, silent=True)
        if data is None:
            frame_buffer.set_roi(None)
            return jsonify({"roi": None})
        try:
            x = int(data["x"])
            y = int(data["y"])
            w = int(data["w"])
            h = int(data["h"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "ROI must include x, y, w, h as integers"}), 400
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            return jsonify({"error": "Invalid ROI dimensions"}), 400
        roi = (x, y, w, h)
        frame_buffer.set_roi(roi)
        return jsonify({"roi": {"x": x, "y": y, "w": w, "h": h}})

    @app.route("/snapshots")
    def snapshots_list():
        snapshot_dir = os.path.expanduser(args.snapshot_dir)
        if not os.path.isdir(snapshot_dir):
            return jsonify([])
        files = sorted(glob.glob(os.path.join(snapshot_dir, "*.jpg")), reverse=True)
        return jsonify([os.path.basename(f) for f in files[:20]])

    @app.route("/snapshots/<filename>")
    def snapshot_file(filename):
        snapshot_dir = os.path.expanduser(args.snapshot_dir)
        return send_from_directory(snapshot_dir, filename)

    @app.route("/alerts", methods=["POST"])
    def set_alerts():
        data = request.get_json(force=True, silent=True) or {}
        if "motion" in data:
            frame_buffer.set_motion_alerts_enabled(bool(data["motion"]))
        if "sound" in data:
            frame_buffer.set_sound_alerts_enabled(bool(data["sound"]))
        return jsonify({
            "motion_alerts": frame_buffer.get_motion_alerts_enabled(),
            "sound_alerts": frame_buffer.get_sound_alerts_enabled(),
        })

    @app.route("/events")
    def events():
        if event_log is None:
            return jsonify([])
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        event_type = request.args.get("type")
        if event_type == "all":
            event_type = None
        return jsonify(event_log.get_events(limit=limit, offset=offset, event_type=event_type))

    return app


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#080810">
<title>BabyPing</title>
<style>
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg: #0c0c14;
  --bg-deep: #080810;
  --surface: rgba(14, 14, 24, 0.82);
  --glass-border: rgba(255, 255, 255, 0.07);
  --glass-shine: rgba(255, 255, 255, 0.04);
  --amber: #f0c674;
  --amber-soft: rgba(240, 198, 116, 0.1);
  --green: #a3be8c;
  --green-soft: rgba(163, 190, 140, 0.12);
  --text: #e5e9f0;
  --text-dim: rgba(229, 233, 240, 0.55);
  --text-muted: rgba(229, 233, 240, 0.28);
  --radius: 14px;
  --radius-sm: 8px;
  --sat: env(safe-area-inset-top, 0px);
  --sab: env(safe-area-inset-bottom, 0px);
}

html, body {
  height: 100%;
  background: var(--bg-deep);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased;
  overflow: hidden;
  user-select: none;
  -webkit-user-select: none;
}

/* ── Monitor container ── */
.monitor {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  overflow: hidden;
}

@media (min-width: 768px) {
  .header { padding-top: 16px; padding-left: 20px; padding-right: 20px; }
  .status-bar { padding-left: 16px; padding-right: 16px; }
}

/* ── Stream area ── */
.stream-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  background: var(--bg);
  overflow: hidden;
}

.stream-wrap img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* Vignette */
.stream-wrap::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 55%, rgba(8,8,16,0.45) 100%);
  pointer-events: none;
  z-index: 1;
}

/* Motion glow */
.stream-wrap::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  box-shadow: inset 0 0 40px rgba(240,198,116,0);
  transition: box-shadow 0.8s ease;
  z-index: 2;
}

.stream-wrap.has-motion::after {
  animation: motionGlow 2.2s ease-in-out infinite;
}

@keyframes motionGlow {
  0%, 100% { box-shadow: inset 0 0 35px rgba(240,198,116,0.04); }
  50% { box-shadow: inset 0 0 70px rgba(240,198,116,0.16); }
}

/* Loading overlay */
.loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  z-index: 5;
  transition: opacity 0.6s ease, visibility 0.6s ease;
}

.loading.hidden { opacity: 0; visibility: hidden; pointer-events: none; }

.loading-ring {
  width: 36px;
  height: 36px;
  border: 2.5px solid var(--text-muted);
  border-top-color: var(--amber);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  margin-bottom: 14px;
}

@keyframes spin { to { transform: rotate(360deg); } }

.loading span {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-dim);
  letter-spacing: 0.4px;
}

/* ── Header overlay ── */
.header {
  position: absolute;
  top: 0; left: 0; right: 0;
  padding: calc(14px + var(--sat)) 16px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 10;
  background: linear-gradient(to bottom, rgba(8,8,16,0.75) 0%, transparent 100%);
}

.logo {
  font-family: 'SF Pro Rounded', -apple-system, BlinkMacSystemFont, sans-serif;
  font-weight: 700;
  font-size: 21px;
  color: var(--text);
  letter-spacing: -0.3px;
}

.header-right { display: flex; align-items: center; gap: 10px; }

.clock {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
}

.live-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px 4px 7px;
  background: var(--green-soft);
  border: 1px solid rgba(163,190,140,0.2);
  border-radius: 20px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.2px;
  color: var(--green);
  text-transform: uppercase;
  transition: background 0.4s, border-color 0.4s, color 0.4s;
}

.live-pill.delayed {
  background: var(--amber-soft);
  border-color: rgba(240,198,116,0.2);
  color: var(--amber);
}

.live-pill.offline {
  background: rgba(191,97,106,0.1);
  border-color: rgba(191,97,106,0.2);
  color: #bf616a;
}

.live-dot {
  width: 6px;
  height: 6px;
  background: var(--green);
  border-radius: 50%;
  animation: pulse 2.5s ease-in-out infinite;
  transition: background 0.4s;
}

.live-pill.delayed .live-dot { background: var(--amber); animation-duration: 1.2s; }
.live-pill.offline .live-dot { background: #bf616a; animation: none; opacity: 0.6; }

.secure-pill {
  display: none;
  align-items: center;
  gap: 4px;
  padding: 4px 9px 4px 7px;
  background: var(--green-soft);
  border: 1px solid rgba(163,190,140,0.2);
  border-radius: 20px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.2px;
  color: var(--green);
  text-transform: uppercase;
}

.secure-pill.visible { display: flex; }

.secure-pill svg { width: 11px; height: 11px; }

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.75); }
}

/* ── Status bar overlay ── */
.status-bar {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  z-index: 10;
  padding: 48px 12px calc(10px + var(--sab));
  background: linear-gradient(to top, rgba(8,8,16,0.85) 0%, transparent 100%);
}

.status-row {
  display: flex;
  gap: 6px;
}

.status-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  background: var(--surface);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  transition: background 0.4s, border-color 0.4s;
}

.status-card.primary { flex: 1; cursor: pointer; -webkit-tap-highlight-color: transparent; }

.status-card.motion-on {
  background: rgba(240,198,116,0.07);
  border-color: rgba(240,198,116,0.14);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
  transition: background 0.4s, box-shadow 0.4s;
}

.motion-on .status-dot {
  background: var(--amber);
  box-shadow: 0 0 8px rgba(240,198,116,0.4);
}

.status-text {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-dim);
  white-space: nowrap;
  transition: color 0.4s;
}

.motion-on .status-text { color: var(--amber); }

.status-card.tag {
  padding: 9px 11px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  white-space: nowrap;
}

.night-icon { font-size: 14px; line-height: 1; }

/* ── Alert toggles ── */
.alert-toggle {
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.3s, border-color 0.3s, color 0.3s;
}

.alert-toggle.off {
  color: var(--text-muted);
  text-decoration: line-through;
  opacity: 0.5;
}

/* ── Audio VU meter ── */
.audio-card {
  display: none;
  flex-direction: column;
  gap: 4px;
  min-width: 80px;
}

.audio-card.visible { display: flex; }

.audio-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  text-transform: uppercase;
  transition: color 0.4s;
}

.audio-card.sound-on .audio-label { color: var(--amber); }

.vu-track {
  width: 100%;
  height: 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 2px;
  overflow: hidden;
}

.vu-fill {
  height: 100%;
  width: 0%;
  border-radius: 2px;
  background: var(--text-muted);
  transition: width 0.15s ease, background 0.3s ease;
}

/* ── Audio alert button ── */
.notify-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1px solid var(--glass-border);
  background: var(--surface);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: var(--text-muted);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: color 0.3s, border-color 0.3s, background 0.3s;
}

.notify-btn.active {
  color: var(--amber);
  border-color: rgba(240,198,116,0.3);
  background: var(--amber-soft);
}

.notify-btn svg { width: 14px; height: 14px; }

/* ── Bottom sheet ── */
.sheet-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0);
  z-index: 49;
  pointer-events: none;
  transition: background 0.4s cubic-bezier(0.32, 0.72, 0, 1);
}

.sheet-backdrop.visible {
  pointer-events: auto;
}

.sheet {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 92vh;
  z-index: 50;
  background: var(--surface);
  border-radius: 20px 20px 0 0;
  border-top: 1px solid var(--glass-border);
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
  transform: translateY(100%);
  transition: transform 0.4s cubic-bezier(0.32, 0.72, 0, 1);
  display: flex;
  flex-direction: column;
  will-change: transform;
  touch-action: none;
}

.sheet.dragging {
  transition: none !important;
}

.sheet-handle {
  flex-shrink: 0;
  padding: 0 16px;
  cursor: grab;
  -webkit-tap-highlight-color: transparent;
}

.sheet-handle:active { cursor: grabbing; }

.sheet-pill {
  width: 36px;
  height: 4px;
  background: var(--text-muted);
  border-radius: 2px;
  margin: 10px auto 8px;
}

.sheet-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 10px;
}

.sheet-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.2px;
}

.sheet-count {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--glass-shine);
  padding: 2px 8px;
  border-radius: 10px;
  min-width: 22px;
  text-align: center;
}

.sheet-filters {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
  padding: 4px 16px 12px;
}

.sheet-filter {
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid var(--glass-border);
  background: var(--surface);
  color: var(--text-dim);
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.3s, border-color 0.3s, color 0.3s;
}

.sheet-filter.active {
  background: var(--amber-soft);
  border-color: rgba(240, 198, 116, 0.3);
  color: var(--amber);
}

.sheet-body {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 0 16px calc(16px + var(--sab));
  overscroll-behavior: contain;
}

.sheet-body::-webkit-scrollbar { width: 4px; }
.sheet-body::-webkit-scrollbar-track { background: transparent; }
.sheet-body::-webkit-scrollbar-thumb { background: var(--glass-border); border-radius: 2px; }

/* ── Event cards ── */
.evt-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  margin-bottom: 8px;
  background: var(--surface);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  transition: border-color 0.3s;
}

.evt-card.motion { border-left: 3px solid var(--amber); }
.evt-card.sound { border-left: 3px solid #81a1c1; }

.evt-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 15px;
}

.evt-icon.motion {
  background: var(--amber-soft);
  color: var(--amber);
}

.evt-icon.sound {
  background: rgba(129, 161, 193, 0.1);
  color: #81a1c1;
}

.evt-body {
  flex: 1;
  min-width: 0;
}

.evt-type {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 2px;
}

.evt-detail {
  font-size: 11.5px;
  color: var(--text-dim);
}

.evt-time {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.evt-snap {
  width: 48px;
  height: 36px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--glass-border);
  flex-shrink: 0;
  cursor: pointer;
}

.evt-empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
  font-size: 14px;
}

.evt-empty-icon {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.4;
}

/* ── ROI selection ── */
.roi-btn { cursor: pointer; -webkit-tap-highlight-color: transparent; }
.roi-btn.has-roi { border-color: rgba(240,198,116,0.25); background: var(--amber-soft); }
.roi-btn.has-roi .roi-label { color: var(--amber); }

.roi-label { font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }

.roi-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: none;
  flex-direction: column;
}

.roi-overlay.active { display: flex; }

.roi-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
  touch-action: none;
}

.roi-hint {
  position: absolute;
  top: calc(50px + var(--sat));
  left: 0; right: 0;
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-dim);
  pointer-events: none;
  z-index: 21;
}

.roi-actions {
  position: absolute;
  bottom: calc(70px + var(--sab));
  left: 0; right: 0;
  display: none;
  justify-content: center;
  gap: 10px;
  z-index: 21;
}

.roi-actions.visible { display: flex; }

.roi-action-btn {
  padding: 8px 20px;
  border-radius: 20px;
  border: 1px solid var(--glass-border);
  background: var(--surface);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.roi-action-btn.confirm {
  background: rgba(163,190,140,0.15);
  border-color: rgba(163,190,140,0.3);
  color: var(--green);
}

.roi-action-btn.clear {
  background: rgba(191,97,106,0.1);
  border-color: rgba(191,97,106,0.2);
  color: #bf616a;
}

/* ── Fullscreen image viewer ── */
.viewer {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(8,8,16,0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.25s ease, visibility 0.25s ease;
  cursor: pointer;
}

.viewer.show { opacity: 1; visibility: visible; }

.viewer img {
  max-width: 94%;
  max-height: 88vh;
  border-radius: var(--radius);
  object-fit: contain;
}

.viewer-close {
  position: absolute;
  top: calc(16px + var(--sat));
  right: 16px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid var(--glass-border);
  background: var(--surface);
  color: var(--text-dim);
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
</style>
</head>
<body>

<div class="monitor">
  <!-- Stream -->
  <div class="stream-wrap" id="stream-wrap">
    <img src="/stream" alt="Live">

    <div class="loading" id="loading">
      <div class="loading-ring"></div>
      <span>Connecting...</span>
    </div>

    <header class="header">
      <div class="logo">BabyPing</div>
      <div class="header-right">
        <button class="notify-btn" id="notify-btn" onclick="toggleAudio()">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>
        </button>
        <span class="clock" id="clock"></span>
        <div class="secure-pill" id="secure-pill">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1s3.1 1.39 3.1 3.1v2z"/></svg>
          <span>Secure</span>
        </div>
        <div class="live-pill">
          <span class="live-dot"></span>
          <span id="live-label">Live</span>
        </div>
      </div>
    </header>

    <div class="status-bar">
      <div class="status-row">
        <div class="status-card primary" id="motion-card" onclick="toggleSheet()">
          <div class="status-dot"></div>
          <span class="status-text" id="motion-text">No motion</span>
        </div>
        <div class="status-card tag audio-card" id="audio-card">
          <span class="audio-label" id="audio-label">Audio</span>
          <div class="vu-track"><div class="vu-fill" id="vu-fill"></div></div>
        </div>
        <div class="status-card tag" id="sens-card"></div>
        <div class="status-card tag" id="night-card" style="display:none">
          <span class="night-icon">&#9790;</span>
        </div>
        <div class="status-card tag alert-toggle" id="motion-alert-toggle" onclick="toggleMotionAlerts()">
          <span id="motion-alert-label">Motion</span>
        </div>
        <div class="status-card tag alert-toggle" id="sound-alert-toggle" onclick="toggleSoundAlerts()" style="display:none">
          <span id="sound-alert-label">Sound</span>
        </div>
        <div class="status-card tag roi-btn" id="roi-btn" onclick="enterRoiMode()">
          <span class="roi-label">ROI</span>
        </div>
      </div>
    </div>

    <div class="roi-overlay" id="roi-overlay">
      <canvas class="roi-canvas" id="roi-canvas"></canvas>
      <div class="roi-hint" id="roi-hint">Draw a region to monitor</div>
      <div class="roi-actions" id="roi-actions">
        <button class="roi-action-btn confirm" onclick="confirmRoi()">Confirm</button>
        <button class="roi-action-btn" onclick="cancelRoi()">Cancel</button>
        <button class="roi-action-btn clear" id="roi-clear-btn" onclick="clearRoi()" style="display:none">Clear</button>
      </div>
    </div>
  </div>
</div>

<!-- Sheet backdrop -->
<div class="sheet-backdrop" id="sheet-backdrop"></div>

<!-- Events bottom sheet -->
<div class="sheet" id="sheet">
  <div class="sheet-handle" id="sheet-handle">
    <div class="sheet-pill"></div>
    <div class="sheet-header">
      <span class="sheet-title">Events</span>
      <span class="sheet-count" id="sheet-count">0</span>
    </div>
  </div>
  <div class="sheet-filters" id="sheet-filters">
    <button class="sheet-filter active" data-type="all">All</button>
    <button class="sheet-filter" data-type="motion">Motion</button>
    <button class="sheet-filter" data-type="sound">Sound</button>
  </div>
  <div class="sheet-body" id="sheet-body"></div>
</div>

<!-- Image viewer -->
<div class="viewer" id="viewer" onclick="closeViewer()">
  <button class="viewer-close" onclick="closeViewer()">&times;</button>
  <img id="viewer-img" src="" alt="Snapshot">
</div>

<script>
const streamWrap = document.getElementById('stream-wrap');
const motionCard = document.getElementById('motion-card');
const motionText = document.getElementById('motion-text');
const sensCard = document.getElementById('sens-card');
const nightCard = document.getElementById('night-card');
const clockEl = document.getElementById('clock');
const loadingEl = document.getElementById('loading');
const viewer = document.getElementById('viewer');
const viewerImg = document.getElementById('viewer-img');
const livePill = document.querySelector('.live-pill');
const liveLabel = document.getElementById('live-label');
const streamImg = streamWrap.querySelector('img');
const securePill = document.getElementById('secure-pill');
const audioCard = document.getElementById('audio-card');
const audioLabel = document.getElementById('audio-label');
const vuFill = document.getElementById('vu-fill');
const motionAlertToggle = document.getElementById('motion-alert-toggle');
const soundAlertToggle = document.getElementById('sound-alert-toggle');

/* ROI state (initialized early for status polling) */
var currentRoi = null;

/* Alert toggle state */
var motionAlertsEnabled = true;
var soundAlertsEnabled = true;

function updateAlertToggles() {
  motionAlertToggle.classList.toggle('off', !motionAlertsEnabled);
  soundAlertToggle.classList.toggle('off', !soundAlertsEnabled);
}

function toggleMotionAlerts() {
  motionAlertsEnabled = !motionAlertsEnabled;
  updateAlertToggles();
  fetch('/alerts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ motion: motionAlertsEnabled }) });
}

function toggleSoundAlerts() {
  soundAlertsEnabled = !soundAlertsEnabled;
  updateAlertToggles();
  fetch('/alerts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sound: soundAlertsEnabled }) });
}

/* Audio alert state (initialized early for status polling) */
var audioCtx = null;
var audioEnabled = false;
var lastMotionAlerted = 0;
var lastSoundAlerted = 0;
var statusInitialized = false;
var notifyBtn = document.getElementById('notify-btn');

try { audioEnabled = localStorage.getItem('bp_audio') === '1'; } catch(e) {}

function updateNotifyBtn() {
  if (audioEnabled) { notifyBtn.classList.add('active'); }
  else { notifyBtn.classList.remove('active'); }
}
updateNotifyBtn();

function ensureAudio() {
  if (!audioCtx) {
    try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) {}
  }
  if (audioCtx && audioCtx.state === 'suspended') { audioCtx.resume(); }
}

function playAlertSound() {
  if (!audioCtx) return;
  try {
    var now = audioCtx.currentTime;
    var o1 = audioCtx.createOscillator();
    var g1 = audioCtx.createGain();
    o1.connect(g1); g1.connect(audioCtx.destination);
    o1.frequency.value = 523;
    g1.gain.setValueAtTime(0.2, now);
    g1.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
    o1.start(now); o1.stop(now + 0.3);
    var o2 = audioCtx.createOscillator();
    var g2 = audioCtx.createGain();
    o2.connect(g2); g2.connect(audioCtx.destination);
    o2.frequency.value = 659;
    g2.gain.setValueAtTime(0.2, now + 0.15);
    g2.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
    o2.start(now + 0.15); o2.stop(now + 0.45);
  } catch(e) {}
}

function toggleAudio() {
  audioEnabled = !audioEnabled;
  try { localStorage.setItem('bp_audio', audioEnabled ? '1' : '0'); } catch(e) {}
  updateNotifyBtn();
  if (audioEnabled) {
    ensureAudio();
    playAlertSound();
  }
}

/* Clock */
function updateClock() {
  const d = new Date();
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  const ampm = h >= 12 ? 'PM' : 'AM';
  clockEl.textContent = ((h % 12) || 12) + ':' + m + ':' + s + ' ' + ampm;
}
updateClock();
setInterval(updateClock, 1000);

/* Stream load detection */
streamImg.onload = function() { loadingEl.classList.add('hidden'); };
setTimeout(function() { loadingEl.classList.add('hidden'); }, 4000);

/* Status polling */
let lastMotionActive = false;

function updateStatus() {
  fetch('/status').then(function(r) { return r.json(); }).then(function(data) {
    sensCard.textContent = data.sensitivity.charAt(0).toUpperCase() + data.sensitivity.slice(1);

    if (data.night_mode) { nightCard.style.display = ''; }
    else { nightCard.style.display = 'none'; }

    /* Feed freshness */
    if (data.last_frame_time) {
      const frameAgo = Math.round(Date.now() / 1000 - data.last_frame_time);
      livePill.classList.remove('delayed', 'offline');
      if (frameAgo > 15) {
        livePill.classList.add('offline');
        liveLabel.textContent = 'Offline';
      } else if (frameAgo > 5) {
        livePill.classList.add('delayed');
        liveLabel.textContent = 'Delayed';
      } else {
        liveLabel.textContent = 'Live';
      }
    }

    /* ROI sync */
    currentRoi = data.roi;
    updateRoiBtn();

    /* Tailscale secure indicator */
    if (data.tailscale_ip) {
      securePill.classList.add('visible');
    } else {
      securePill.classList.remove('visible');
    }

    /* Motion status */
    if (data.last_motion_time) {
      const ago = Math.round(Date.now() / 1000 - data.last_motion_time);
      const isRecent = ago < 120;

      if (isRecent) {
        motionCard.classList.add('motion-on');
        streamWrap.classList.add('has-motion');
      } else {
        motionCard.classList.remove('motion-on');
        streamWrap.classList.remove('has-motion');
      }

      if (ago < 5) motionText.textContent = 'Motion now';
      else if (ago < 60) motionText.textContent = 'Motion ' + ago + 's ago';
      else if (ago < 3600) motionText.textContent = 'Motion ' + Math.round(ago / 60) + 'm ago';
      else motionText.textContent = 'Motion ' + Math.round(ago / 3600) + 'h ago';
    } else {
      motionCard.classList.remove('motion-on');
      streamWrap.classList.remove('has-motion');
      motionText.textContent = 'No motion';
    }

    /* Audio level VU meter */
    if (data.audio_enabled) {
      audioCard.classList.add('visible');
      var level = data.audio_level || 0;
      var pct = Math.min(level * 100 / 0.5, 100);
      vuFill.style.width = pct + '%';
      if (pct < 10) { vuFill.style.background = 'var(--text-muted)'; }
      else if (pct < 40) { vuFill.style.background = 'var(--green)'; }
      else if (pct < 70) { vuFill.style.background = 'var(--amber)'; }
      else { vuFill.style.background = '#bf616a'; }

      if (data.last_sound_time) {
        var soundAgo = Math.round(Date.now() / 1000 - data.last_sound_time);
        if (soundAgo < 5) {
          audioCard.classList.add('sound-on');
          audioLabel.textContent = 'Sound now';
        } else if (soundAgo < 60) {
          audioCard.classList.remove('sound-on');
          audioLabel.textContent = 'Sound ' + soundAgo + 's ago';
        } else {
          audioCard.classList.remove('sound-on');
          audioLabel.textContent = 'Audio';
        }
      } else {
        audioCard.classList.remove('sound-on');
        audioLabel.textContent = 'Audio';
      }
    } else {
      audioCard.classList.remove('visible');
    }

    /* Sync alert toggle state */
    motionAlertsEnabled = data.motion_alerts;
    soundAlertsEnabled = data.sound_alerts;
    updateAlertToggles();
    if (data.audio_enabled) { soundAlertToggle.style.display = ''; }
    else { soundAlertToggle.style.display = 'none'; }

    /* Audio alert on new motion or sound events */
    if (!statusInitialized) {
      lastMotionAlerted = data.last_motion_time || 0;
      lastSoundAlerted = data.last_sound_time || 0;
      statusInitialized = true;
    } else if (audioEnabled) {
      if (data.last_motion_time && data.last_motion_time > lastMotionAlerted) {
        lastMotionAlerted = data.last_motion_time;
        ensureAudio();
        playAlertSound();
        try { if (navigator.vibrate) navigator.vibrate([200, 100, 200]); } catch(e) {}
      }
      if (data.last_sound_time && data.last_sound_time > lastSoundAlerted) {
        lastSoundAlerted = data.last_sound_time;
        ensureAudio();
        playAlertSound();
        try { if (navigator.vibrate) navigator.vibrate([200, 100, 200]); } catch(e) {}
      }
    }
  }).catch(function() {});
}

/* Image viewer */
function openViewer(src) {
  viewerImg.src = src;
  viewer.classList.add('show');
}

function closeViewer() {
  viewer.classList.remove('show');
}

/* Init */
updateStatus();
setInterval(updateStatus, 3000);

/* ── Bottom sheet ── */
var sheet = document.getElementById('sheet');
var sheetBackdrop = document.getElementById('sheet-backdrop');
var sheetBody = document.getElementById('sheet-body');
var sheetCount = document.getElementById('sheet-count');
var sheetFilters = document.getElementById('sheet-filters');

var sheetHeight = sheet.offsetHeight;
var SNAP_HIDDEN = sheetHeight;
var SNAP_HALF = sheetHeight * 0.5;
var SNAP_FULL = 0;
var sheetY = SNAP_HIDDEN;
var sheetOpen = false;
var sheetFilter = 'all';
var sheetDragging = false;
var sheetStartY = 0;
var sheetStartTranslate = 0;
var sheetLastMoveY = 0;
var sheetLastMoveTime = 0;
var sheetVelocity = 0;

function setSheetY(y) {
  sheetY = y;
  sheet.style.transform = 'translateY(' + y + 'px)';
  /* Interpolate backdrop: 0 at hidden, 0.5 at full */
  var range = SNAP_HIDDEN - SNAP_FULL;
  var progress = range > 0 ? 1 - ((y - SNAP_FULL) / range) : 0;
  progress = Math.max(0, Math.min(1, progress));
  var opacity = progress * 0.5;
  sheetBackdrop.style.background = 'rgba(0,0,0,' + opacity + ')';
  if (progress > 0.02) { sheetBackdrop.classList.add('visible'); }
  else { sheetBackdrop.classList.remove('visible'); }
  sheetOpen = y < SNAP_HIDDEN;
}

function snapSheet(target) {
  sheet.classList.remove('dragging');
  setSheetY(target);
  if (target >= SNAP_HIDDEN) { loadSheetEvents(); }
}

function toggleSheet() {
  if (sheetOpen) {
    snapSheet(SNAP_HIDDEN);
  } else {
    loadSheetEvents();
    snapSheet(SNAP_HALF);
  }
}

function recalcSnaps() {
  sheetHeight = sheet.offsetHeight;
  SNAP_HIDDEN = sheetHeight;
  SNAP_HALF = sheetHeight * 0.5;
  SNAP_FULL = 0;
}

function onSheetPointerDown(e) {
  /* Allow scrolling inside sheet-body when expanded */
  if (sheetBody.contains(e.target) && sheetY <= SNAP_HALF && sheetBody.scrollTop > 0) return;

  var clientY = e.touches ? e.touches[0].clientY : e.clientY;
  sheetDragging = true;
  sheetStartY = clientY;
  sheetStartTranslate = sheetY;
  sheetLastMoveY = clientY;
  sheetLastMoveTime = Date.now();
  sheetVelocity = 0;
  sheet.classList.add('dragging');
}

function onSheetPointerMove(e) {
  if (!sheetDragging) return;
  var clientY = e.touches ? e.touches[0].clientY : e.clientY;
  var deltaY = clientY - sheetStartY;
  var newY = sheetStartTranslate + deltaY;

  /* Rubber band past top */
  if (newY < SNAP_FULL) {
    newY = SNAP_FULL + (newY - SNAP_FULL) * 0.3;
  }
  /* Clamp at hidden */
  if (newY > SNAP_HIDDEN) { newY = SNAP_HIDDEN; }

  setSheetY(newY);

  /* Track velocity */
  var now = Date.now();
  var dt = now - sheetLastMoveTime;
  if (dt > 0) {
    sheetVelocity = (clientY - sheetLastMoveY) / dt * 1000;
  }
  sheetLastMoveY = clientY;
  sheetLastMoveTime = now;

  e.preventDefault();
}

function onSheetPointerUp() {
  if (!sheetDragging) return;
  sheetDragging = false;

  /* Fast swipe detection */
  if (sheetVelocity < -800) { snapSheet(SNAP_FULL); return; }
  if (sheetVelocity > 800) { snapSheet(SNAP_HIDDEN); return; }

  /* Snap to nearest */
  var snaps = [SNAP_FULL, SNAP_HALF, SNAP_HIDDEN];
  var closest = snaps[0];
  var minDist = Math.abs(sheetY - snaps[0]);
  for (var i = 1; i < snaps.length; i++) {
    var d = Math.abs(sheetY - snaps[i]);
    if (d < minDist) { minDist = d; closest = snaps[i]; }
  }
  snapSheet(closest);
}

/* Touch events on sheet */
sheet.addEventListener('touchstart', function(e) {
  if (sheetBody.contains(e.target) && sheetY <= SNAP_HALF && sheetBody.scrollTop > 0) return;
  onSheetPointerDown(e);
}, { passive: false });
sheet.addEventListener('touchmove', function(e) {
  if (!sheetDragging) return;
  onSheetPointerMove(e);
}, { passive: false });
sheet.addEventListener('touchend', onSheetPointerUp);

/* Mouse events on sheet */
sheet.addEventListener('mousedown', function(e) {
  if (sheetBody.contains(e.target) && sheetY <= SNAP_HALF && sheetBody.scrollTop > 0) return;
  onSheetPointerDown(e);
});
document.addEventListener('mousemove', function(e) {
  if (!sheetDragging) return;
  onSheetPointerMove(e);
});
document.addEventListener('mouseup', onSheetPointerUp);

/* Backdrop tap to dismiss */
sheetBackdrop.addEventListener('click', function() { snapSheet(SNAP_HIDDEN); });

/* Recalculate on resize */
window.addEventListener('resize', function() {
  recalcSnaps();
  if (sheetOpen) { snapSheet(SNAP_HALF); }
});

/* Handle sheet-body scroll: only drag sheet when scrolled to top and swiping down */
sheetBody.addEventListener('touchstart', function(e) {
  if (sheetY > SNAP_HALF) return;
  if (sheetBody.scrollTop <= 0) { return; }
  e.stopPropagation();
}, { passive: true });

sheetBody.addEventListener('touchmove', function(e) {
  if (sheetDragging) return;
  if (sheetBody.scrollTop <= 0 && sheetY <= SNAP_HALF) { return; }
  e.stopPropagation();
}, { passive: true });

/* Filter buttons */
sheetFilters.addEventListener('click', function(e) {
  var btn = e.target.closest('.sheet-filter');
  if (!btn) return;
  sheetFilter = btn.getAttribute('data-type');
  var all = sheetFilters.querySelectorAll('.sheet-filter');
  all.forEach(function(b) { b.classList.toggle('active', b === btn); });
  loadSheetEvents();
});

/* Event loading */
function formatEvtTime(ts) {
  var d = new Date(ts * 1000);
  var now = Date.now();
  var ago = Math.round((now - d.getTime()) / 1000);
  if (ago < 5) return 'Just now';
  if (ago < 60) return ago + 's ago';
  if (ago < 3600) return Math.round(ago / 60) + 'm ago';
  if (ago < 86400) return Math.round(ago / 3600) + 'h ago';
  var h = d.getHours();
  var m = String(d.getMinutes()).padStart(2, '0');
  var ampm = h >= 12 ? 'PM' : 'AM';
  var month = d.toLocaleString('default', { month: 'short' });
  return month + ' ' + d.getDate() + ', ' + ((h % 12) || 12) + ':' + m + ' ' + ampm;
}

function renderSheetEvents(events) {
  if (events.length === 0) {
    sheetBody.innerHTML = '<div class="evt-empty"><div class="evt-empty-icon">&#9203;</div>No events yet</div>';
    sheetCount.textContent = '0';
    return;
  }
  sheetCount.textContent = events.length;
  var html = '';
  events.forEach(function(e) {
    var isMotion = e.type === 'motion';
    var icon = isMotion ? '&#128065;' : '&#128266;';
    var label = isMotion ? 'Motion Detected' : 'Sound Detected';
    var detail = '';
    if (isMotion && e.area !== null && e.area !== undefined) {
      detail = 'Area: ' + Math.round(e.area) + 'px&#178;';
    } else if (!isMotion && e.audio_level !== null && e.audio_level !== undefined) {
      detail = 'Level: ' + (e.audio_level * 100).toFixed(0) + '%';
    }
    var snap = '';
    if (e.snapshot) {
      snap = '<img class="evt-snap" src="/snapshots/' + e.snapshot + '" alt="snap" onclick="openViewer(this.src)">';
    }
    html += '<div class="evt-card ' + e.type + '">' +
      '<div class="evt-icon ' + e.type + '">' + icon + '</div>' +
      '<div class="evt-body">' +
        '<div class="evt-type">' + label + '</div>' +
        (detail ? '<div class="evt-detail">' + detail + '</div>' : '') +
      '</div>' +
      '<span class="evt-time">' + formatEvtTime(e.timestamp) + '</span>' +
      snap +
    '</div>';
  });
  sheetBody.innerHTML = html;
}

function loadSheetEvents() {
  var url = '/events?limit=50';
  if (sheetFilter !== 'all') { url += '&type=' + sheetFilter; }
  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    renderSheetEvents(data);
  }).catch(function() {});
}

loadSheetEvents();
setInterval(loadSheetEvents, 5000);

/* ── ROI selection ── */
const roiOverlay = document.getElementById('roi-overlay');
const roiCanvas = document.getElementById('roi-canvas');
const roiActions = document.getElementById('roi-actions');
const roiHint = document.getElementById('roi-hint');
const roiBtn = document.getElementById('roi-btn');
const roiClearBtn = document.getElementById('roi-clear-btn');
const roiCtx = roiCanvas.getContext('2d');
var roiMode = false;
var roiDrawing = false;
var roiStartX = 0, roiStartY = 0, roiEndX = 0, roiEndY = 0;

function getStreamMapping() {
  var cw = streamImg.clientWidth, ch = streamImg.clientHeight;
  var nw = streamImg.naturalWidth, nh = streamImg.naturalHeight;
  if (!nw || !nh) return null;
  var scale, ox, oy;
  if (nw / nh > cw / ch) {
    scale = ch / nh; ox = (cw - nw * scale) / 2; oy = 0;
  } else {
    scale = cw / nw; ox = 0; oy = (ch - nh * scale) / 2;
  }
  return { scale: scale, ox: ox, oy: oy, nw: nw, nh: nh };
}

function cssToFrame(cx, cy) {
  var m = getStreamMapping();
  if (!m) return null;
  var fx = Math.round((cx - m.ox) / m.scale);
  var fy = Math.round((cy - m.oy) / m.scale);
  return { x: Math.max(0, Math.min(fx, m.nw)), y: Math.max(0, Math.min(fy, m.nh)) };
}

function enterRoiMode() {
  roiMode = true;
  roiCanvas.width = streamImg.clientWidth;
  roiCanvas.height = streamImg.clientHeight;
  roiActions.classList.remove('visible');
  roiHint.textContent = 'Draw a region to monitor';
  roiClearBtn.style.display = currentRoi ? '' : 'none';
  if (currentRoi) { roiActions.classList.add('visible'); }
  roiCtx.clearRect(0, 0, roiCanvas.width, roiCanvas.height);
  drawDimOverlay();
  roiOverlay.classList.add('active');
}

function drawDimOverlay() {
  roiCtx.clearRect(0, 0, roiCanvas.width, roiCanvas.height);
  roiCtx.fillStyle = 'rgba(0, 0, 0, 0.45)';
  roiCtx.fillRect(0, 0, roiCanvas.width, roiCanvas.height);
}

function drawRoiRect() {
  var x = Math.min(roiStartX, roiEndX);
  var y = Math.min(roiStartY, roiEndY);
  var w = Math.abs(roiEndX - roiStartX);
  var h = Math.abs(roiEndY - roiStartY);

  drawDimOverlay();

  /* Cut out the selected region */
  roiCtx.clearRect(x, y, w, h);

  /* Amber border */
  roiCtx.strokeStyle = 'rgba(240, 198, 116, 0.85)';
  roiCtx.lineWidth = 2;
  roiCtx.strokeRect(x, y, w, h);

  /* Corner markers */
  roiCtx.fillStyle = 'rgba(240, 198, 116, 0.9)';
  var cs = 8;
  [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].forEach(function(p) {
    roiCtx.fillRect(p[0] - cs/2, p[1] - cs/2, cs, cs);
  });
}

function getPos(e) {
  var rect = roiCanvas.getBoundingClientRect();
  if (e.touches) {
    return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
  }
  return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

function onPointerDown(e) {
  if (!roiMode) return;
  e.preventDefault();
  roiDrawing = true;
  var p = getPos(e);
  roiStartX = p.x; roiStartY = p.y;
  roiEndX = p.x; roiEndY = p.y;
  roiActions.classList.remove('visible');
  roiHint.textContent = '';
}

function onPointerMove(e) {
  if (!roiDrawing) return;
  e.preventDefault();
  var p = getPos(e);
  roiEndX = p.x; roiEndY = p.y;
  drawRoiRect();
}

function onPointerUp(e) {
  if (!roiDrawing) return;
  roiDrawing = false;
  var w = Math.abs(roiEndX - roiStartX);
  var h = Math.abs(roiEndY - roiStartY);
  if (w < 15 || h < 15) {
    drawDimOverlay();
    roiHint.textContent = 'Draw a region to monitor';
    return;
  }
  roiClearBtn.style.display = currentRoi ? '' : 'none';
  roiActions.classList.add('visible');
}

roiCanvas.addEventListener('mousedown', onPointerDown);
roiCanvas.addEventListener('mousemove', onPointerMove);
roiCanvas.addEventListener('mouseup', onPointerUp);
roiCanvas.addEventListener('touchstart', onPointerDown, { passive: false });
roiCanvas.addEventListener('touchmove', onPointerMove, { passive: false });
roiCanvas.addEventListener('touchend', onPointerUp);

function confirmRoi() {
  var x = Math.min(roiStartX, roiEndX);
  var y = Math.min(roiStartY, roiEndY);
  var w = Math.abs(roiEndX - roiStartX);
  var h = Math.abs(roiEndY - roiStartY);
  var tl = cssToFrame(x, y);
  var br = cssToFrame(x + w, y + h);
  if (!tl || !br) return;
  var roi = { x: tl.x, y: tl.y, w: br.x - tl.x, h: br.y - tl.y };
  if (roi.w <= 0 || roi.h <= 0) return;
  fetch('/roi', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(roi)
  }).then(function(r) { return r.json(); }).then(function(data) {
    currentRoi = data.roi;
    updateRoiBtn();
    exitRoiMode();
  });
}

function clearRoi() {
  fetch('/roi', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: 'null'
  }).then(function(r) { return r.json(); }).then(function() {
    currentRoi = null;
    updateRoiBtn();
    exitRoiMode();
  });
}

function cancelRoi() { exitRoiMode(); }

function exitRoiMode() {
  roiMode = false;
  roiDrawing = false;
  roiOverlay.classList.remove('active');
  roiActions.classList.remove('visible');
  roiCtx.clearRect(0, 0, roiCanvas.width, roiCanvas.height);
}

function updateRoiBtn() {
  if (currentRoi) { roiBtn.classList.add('has-roi'); }
  else { roiBtn.classList.remove('has-roi'); }
}

window.addEventListener('resize', function() { if (roiMode) exitRoiMode(); });
</script>
</body>
</html>"""


