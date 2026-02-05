import glob
import os
import time

from flask import Flask, Response, jsonify, send_from_directory


def create_app(args, frame_buffer=None):
    """Create Flask app for the BabyPing web UI."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        snapshots_enabled = args.snapshots
        return HTML_TEMPLATE.replace("{{SNAPSHOTS_ENABLED}}", "true" if snapshots_enabled else "false")

    @app.route("/stream")
    def stream():
        def generate():
            while True:
                frame_bytes = frame_buffer.get()
                if frame_bytes is not None:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                time.sleep(0.033)  # ~30fps

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/status")
    def status():
        last_motion = frame_buffer.get_last_motion_time()
        last_frame = frame_buffer.get_last_frame_time()
        return jsonify({
            "sensitivity": args.sensitivity,
            "night_mode": args.night_mode,
            "snapshots_enabled": args.snapshots,
            "last_motion_time": last_motion,
            "last_frame_time": last_frame,
        })

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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@500;700&family=Nunito:wght@400;600;700&display=swap" rel="stylesheet">
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
  font-family: 'Nunito', -apple-system, BlinkMacSystemFont, sans-serif;
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
  font-family: 'Comfortaa', cursive;
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

.status-card.primary { flex: 1; }

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

/* ── Snapshots panel ── */
.snap-panel {
  flex-shrink: 0;
  background: var(--surface);
  border-top: 1px solid var(--glass-border);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  max-height: 40px;
  overflow: hidden;
  transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.snap-panel.open { max-height: 152px; }

.snap-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 16px;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.snap-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-muted);
}

.snap-badge {
  font-size: 10px;
  color: var(--text-muted);
  background: var(--glass-shine);
  padding: 2px 7px;
  border-radius: 8px;
  margin-left: 6px;
}

.snap-chevron {
  font-size: 10px;
  color: var(--text-muted);
  transition: transform 0.3s ease;
}

.snap-panel.open .snap-chevron { transform: rotate(180deg); }

.snap-scroll {
  display: flex;
  gap: 8px;
  padding: 2px 16px 12px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.snap-scroll::-webkit-scrollbar { display: none; }

.snap-thumb {
  flex-shrink: 0;
  scroll-snap-align: start;
  width: 90px;
  height: 68px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, opacity 0.2s ease;
}

.snap-thumb:active { transform: scale(0.96); opacity: 0.8; }

@media (hover: hover) {
  .snap-thumb:hover { transform: scale(1.04); border-color: rgba(255,255,255,0.14); }
}

.snap-empty {
  padding: 2px 16px 14px;
  font-size: 12px;
  color: var(--text-muted);
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
        <span class="clock" id="clock"></span>
        <div class="live-pill">
          <span class="live-dot"></span>
          <span id="live-label">Live</span>
        </div>
      </div>
    </header>

    <div class="status-bar">
      <div class="status-row">
        <div class="status-card primary" id="motion-card">
          <div class="status-dot"></div>
          <span class="status-text" id="motion-text">No motion</span>
        </div>
        <div class="status-card tag" id="sens-card"></div>
        <div class="status-card tag" id="night-card" style="display:none">
          <span class="night-icon">&#9790;</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Snapshots -->
  <div class="snap-panel" id="snap-panel">
    <div class="snap-toggle" id="snap-toggle">
      <div>
        <span class="snap-label">Recent Events</span>
        <span class="snap-badge" id="snap-count"></span>
      </div>
      <span class="snap-chevron">&#9660;</span>
    </div>
    <div class="snap-scroll" id="snap-scroll"></div>
  </div>
</div>

<!-- Image viewer -->
<div class="viewer" id="viewer" onclick="closeViewer()">
  <button class="viewer-close" onclick="closeViewer()">&times;</button>
  <img id="viewer-img" src="" alt="Snapshot">
</div>

<script>
const snapshotsEnabled = {{SNAPSHOTS_ENABLED}};
const streamWrap = document.getElementById('stream-wrap');
const motionCard = document.getElementById('motion-card');
const motionText = document.getElementById('motion-text');
const sensCard = document.getElementById('sens-card');
const nightCard = document.getElementById('night-card');
const clockEl = document.getElementById('clock');
const loadingEl = document.getElementById('loading');
const snapPanel = document.getElementById('snap-panel');
const snapScroll = document.getElementById('snap-scroll');
const snapCount = document.getElementById('snap-count');
const viewer = document.getElementById('viewer');
const viewerImg = document.getElementById('viewer-img');
const livePill = document.querySelector('.live-pill');
const liveLabel = document.getElementById('live-label');
const streamImg = streamWrap.querySelector('img');

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
  }).catch(function() {});
}

/* Snapshots */
function updateSnapshots() {
  if (!snapshotsEnabled) { snapPanel.style.display = 'none'; return; }
  fetch('/snapshots').then(function(r) { return r.json(); }).then(function(files) {
    snapCount.textContent = files.length || '';
    if (files.length === 0) {
      snapScroll.innerHTML = '<div class="snap-empty">No events yet</div>';
      return;
    }
    snapScroll.innerHTML = files.map(function(f) {
      return '<img class="snap-thumb" src="/snapshots/' + f + '" alt="' + f + '" onclick="openViewer(this.src)">';
    }).join('');
  }).catch(function() {});
}

/* Drawer toggle */
document.getElementById('snap-toggle').addEventListener('click', function() {
  snapPanel.classList.toggle('open');
});

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
updateSnapshots();
setInterval(updateStatus, 3000);
setInterval(updateSnapshots, 10000);
</script>
</body>
</html>"""
