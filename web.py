import glob
import os
import time

from flask import Flask, Response, jsonify, send_from_directory


def create_app(args):
    """Create Flask app for the BabyPing web UI."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        snapshots_enabled = args.snapshots
        return HTML_TEMPLATE.replace("{{SNAPSHOTS_ENABLED}}", "true" if snapshots_enabled else "false")

    @app.route("/stream")
    def stream():
        def generate():
            from babyping import frame_buffer
            while True:
                frame_bytes = frame_buffer.get()
                if frame_bytes is not None:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                time.sleep(0.033)  # ~30fps

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/status")
    def status():
        from babyping import frame_buffer
        last_motion = frame_buffer.get_last_motion_time()
        return jsonify({
            "sensitivity": args.sensitivity,
            "night_mode": args.night_mode,
            "snapshots_enabled": args.snapshots,
            "last_motion_time": last_motion,
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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BabyPing</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #111; color: #eee; font-family: -apple-system, system-ui, sans-serif; }
  .stream { width: 100%; display: block; }
  .status { padding: 12px 16px; background: #1a1a1a; font-size: 14px; display: flex; justify-content: space-between; }
  .status span { opacity: 0.7; }
  .snapshots { padding: 12px 16px; }
  .snapshots h3 { font-size: 13px; opacity: 0.5; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
  .snap-row { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; }
  .snap-row img { height: 80px; border-radius: 4px; cursor: pointer; flex-shrink: 0; }
  .snap-row img:hover { opacity: 0.8; }
  .no-snapshots { display: none; }
</style>
</head>
<body>
<img class="stream" src="/stream" alt="BabyPing Live">
<div class="status">
  <span id="sensitivity"></span>
  <span id="night-mode"></span>
  <span id="last-motion">No motion detected</span>
</div>
<div class="snapshots" id="snapshots-section">
  <h3>Recent Events</h3>
  <div class="snap-row" id="snap-row"></div>
</div>
<script>
const snapshotsEnabled = {{SNAPSHOTS_ENABLED}};

function updateStatus() {
  fetch('/status').then(r => r.json()).then(data => {
    document.getElementById('sensitivity').textContent = 'Sensitivity: ' + data.sensitivity;
    document.getElementById('night-mode').textContent = data.night_mode ? 'Night mode: on' : '';
    if (data.last_motion_time) {
      const ago = Math.round((Date.now()/1000) - data.last_motion_time);
      if (ago < 60) document.getElementById('last-motion').textContent = 'Motion: ' + ago + 's ago';
      else if (ago < 3600) document.getElementById('last-motion').textContent = 'Motion: ' + Math.round(ago/60) + 'm ago';
      else document.getElementById('last-motion').textContent = 'Motion: ' + Math.round(ago/3600) + 'h ago';
    }
  }).catch(() => {});
}

function updateSnapshots() {
  if (!snapshotsEnabled) {
    document.getElementById('snapshots-section').style.display = 'none';
    return;
  }
  fetch('/snapshots').then(r => r.json()).then(files => {
    const row = document.getElementById('snap-row');
    row.innerHTML = files.map(f => '<img src="/snapshots/' + f + '" onclick="window.open(this.src)" alt="' + f + '">').join('');
  }).catch(() => {});
}

updateStatus();
updateSnapshots();
setInterval(updateStatus, 5000);
setInterval(updateSnapshots, 10000);
</script>
</body>
</html>"""
