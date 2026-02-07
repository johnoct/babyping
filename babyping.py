import argparse
import glob
import os
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime

import cv2
import numpy as np

class FrameBuffer:
    """Thread-safe buffer for sharing the latest frame between detection and web threads."""
    def __init__(self):
        self._lock = threading.Lock()
        self._frame_bytes = None
        self._last_motion_time = None
        self._last_frame_time = None
        self._last_read_time = None
        self._roi = None
        self._audio_level = 0.0
        self._last_sound_time = None
        self._audio_enabled = False
        self._motion_alerts_enabled = True
        self._sound_alerts_enabled = True
        self._sensitivity = "medium"
        self._fps = 10

    def update(self, frame_bytes):
        with self._lock:
            self._frame_bytes = frame_bytes
            self._last_frame_time = time.time()

    def get(self):
        with self._lock:
            self._last_read_time = time.monotonic()
            return self._frame_bytes

    def has_viewers(self):
        with self._lock:
            return (self._last_read_time is not None
                    and (time.monotonic() - self._last_read_time) < 5.0)

    def set_last_motion_time(self, t):
        with self._lock:
            self._last_motion_time = t

    def get_last_motion_time(self):
        with self._lock:
            return self._last_motion_time

    def get_last_frame_time(self):
        with self._lock:
            return self._last_frame_time

    def set_roi(self, roi):
        with self._lock:
            self._roi = roi

    def get_roi(self):
        with self._lock:
            return self._roi

    def set_audio_level(self, level):
        with self._lock:
            self._audio_level = level

    def get_audio_level(self):
        with self._lock:
            return self._audio_level

    def set_last_sound_time(self, t):
        with self._lock:
            self._last_sound_time = t

    def get_last_sound_time(self):
        with self._lock:
            return self._last_sound_time

    def set_audio_enabled(self, enabled):
        with self._lock:
            self._audio_enabled = enabled

    def get_audio_enabled(self):
        with self._lock:
            return self._audio_enabled

    def set_motion_alerts_enabled(self, enabled):
        with self._lock:
            self._motion_alerts_enabled = enabled

    def get_motion_alerts_enabled(self):
        with self._lock:
            return self._motion_alerts_enabled

    def set_sound_alerts_enabled(self, enabled):
        with self._lock:
            self._sound_alerts_enabled = enabled

    def get_sound_alerts_enabled(self):
        with self._lock:
            return self._sound_alerts_enabled

    def set_sensitivity(self, sensitivity):
        with self._lock:
            self._sensitivity = sensitivity

    def get_sensitivity(self):
        with self._lock:
            return self._sensitivity

    def set_fps(self, fps):
        with self._lock:
            self._fps = fps

    def get_fps(self):
        with self._lock:
            return self._fps


frame_buffer = FrameBuffer()

SENSITIVITY_THRESHOLDS = {
    "low": 5000,
    "medium": 2000,
    "high": 500,
}


def mask_credentials(url):
    """Mask username:password in a URL for safe logging."""
    return re.sub(r'(://)[^@]+@', r'\1***:***@', url)


class ThreadedVideoCapture:
    """Thread-safe video capture that reads frames in a background thread.

    Prevents RTSP/network stream lag by continuously reading frames and
    always providing the latest one to the caller.
    """

    def __init__(self, source, rtsp_transport="tcp"):
        if isinstance(source, str) and source.startswith("rtsp://"):
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{rtsp_transport}"
        self._cap = cv2.VideoCapture(source)
        self._lock = threading.Lock()
        self._ret = False
        self._frame = None
        self._stopped = False
        self._last_frame_time = None
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        while not self._stopped:
            ret, frame = self._cap.read()
            with self._lock:
                self._ret = ret
                self._frame = frame
                if ret:
                    self._last_frame_time = time.monotonic()

    def read(self):
        with self._lock:
            frame = self._frame.copy() if self._frame is not None else None
            return self._ret, frame

    def isOpened(self):
        return self._cap.isOpened()

    def release(self):
        self._stopped = True
        self._thread.join(timeout=2.0)
        self._cap.release()

    def get(self, prop):
        return self._cap.get(prop)

    def set(self, prop, value):
        return self._cap.set(prop, value)

    def is_healthy(self, timeout=10.0):
        with self._lock:
            if self._last_frame_time is None:
                return False
            return (time.monotonic() - self._last_frame_time) < timeout


def _is_network_source(source):
    """Check if a camera source string is a network URL."""
    return isinstance(source, str) and (
        source.startswith("rtsp://") or source.startswith("http://") or source.startswith("https://")
    )


def open_camera_source(source, rtsp_transport="tcp"):
    """Open a camera source. Returns VideoCapture (local) or ThreadedVideoCapture (network).

    Args:
        source: Camera index as string ("0") or URL ("rtsp://...")
        rtsp_transport: "tcp" or "udp" for RTSP streams
    """
    if _is_network_source(source):
        cap = ThreadedVideoCapture(source, rtsp_transport=rtsp_transport)
        if not cap.isOpened():
            cap.release()
            print(f"Error: Could not open camera at {mask_credentials(source)}")
            sys.exit(1)
        return cap

    try:
        index = int(source)
    except ValueError:
        print(f"Error: Invalid camera source: {source}")
        sys.exit(1)

    cap = try_open_camera(index)
    if cap is None:
        print(f"Error: Could not open camera at index {index}")
        sys.exit(1)
    return cap


def parse_args():
    parser = argparse.ArgumentParser(description="BabyPing — lightweight baby monitor with motion detection")
    parser.add_argument("--camera", type=str, default="0",
                        help="Camera index or RTSP/HTTP URL (default: 0)")
    parser.add_argument("--rtsp-transport", choices=["tcp", "udp"], default="tcp",
                        help="RTSP transport protocol (default: tcp)")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high"], default="medium",
                        help="Motion sensitivity (default: medium)")
    parser.add_argument("--cooldown", type=int, default=30, help="Seconds between notifications (default: 30)")
    parser.add_argument("--no-preview", action="store_true", help="Run without preview window")
    parser.add_argument("--snapshot-dir", default="~/.babyping/events",
                        help="Directory for motion snapshots (default: ~/.babyping/events)")
    parser.add_argument("--max-snapshots", type=int, default=100,
                        help="Max snapshots to keep, 0=unlimited (default: 100)")
    parser.add_argument("--snapshots", action="store_true",
                        help="Enable snapshot saving on motion events")
    parser.add_argument("--night-mode", action="store_true",
                        help="Enhance preview brightness for dark rooms")
    parser.add_argument("--roi", default=None,
                        help="Region of interest as x,y,w,h (interactive selection if omitted)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Web UI bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080,
                        help="Web UI port (default: 8080)")
    parser.add_argument("--password", default=None,
                        help="Web UI password (enables HTTP Basic Auth)")
    parser.add_argument("--fps", type=int, default=10,
                        help="Max frames per second, 0=unlimited (default: 10)")
    parser.add_argument("--no-audio", action="store_true",
                        help="Disable audio monitoring")
    parser.add_argument("--audio-device", type=int, default=None,
                        help="Audio input device index (default: system default)")
    parser.add_argument("--audio-threshold", type=float, default=None,
                        help="Audio threshold (0-1), omit for auto-calibration")
    parser.add_argument("--max-events", type=int, default=1000,
                        help="Max events to keep in log, 0=unlimited (default: 1000)")
    return parser.parse_args()


def detect_motion(prev_gray, curr_gray, threshold):
    """Detect motion by frame-diffing. Returns (motion_detected, contours, total_area)."""
    diff = cv2.absdiff(prev_gray, curr_gray)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_area = sum(cv2.contourArea(c) for c in contours)
    return total_area >= threshold, contours, total_area


def send_notification(title, message):
    safe_title = str(title).replace('\\', '\\\\').replace('"', '\\"')
    safe_message = str(message).replace('\\', '\\\\').replace('"', '\\"')
    subprocess.run([
        "osascript", "-e",
        f'display notification "{safe_message}" with title "{safe_title}" sound name "Glass"'
    ], capture_output=True)


def start_web_server(flask_app, host, port):
    """Create and return a daemon thread running the web server."""
    try:
        from waitress import serve as waitress_serve
        thread = threading.Thread(
            target=lambda: waitress_serve(flask_app, host=host, port=port, threads=4, _quiet=True),
            daemon=True
        )
    except ImportError:
        thread = threading.Thread(
            target=lambda: flask_app.run(host=host, port=port, threaded=True),
            daemon=True
        )
    return thread


def save_snapshot(frame, snapshot_dir="~/.babyping/events", max_snapshots=100):
    """Save a frame as a JPEG snapshot. Returns the file path, or None on failure."""
    try:
        snapshot_dir = os.path.expanduser(snapshot_dir)
        os.makedirs(snapshot_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        filepath = os.path.join(snapshot_dir, f"{timestamp}.jpg")
        success = cv2.imwrite(filepath, frame)
        if not success:
            return None

        if max_snapshots > 0:
            files = sorted(glob.glob(os.path.join(snapshot_dir, "*.jpg")))
            while len(files) > max_snapshots:
                try:
                    os.remove(files.pop(0))
                except FileNotFoundError:
                    pass

        return filepath
    except OSError:
        return None


_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def apply_night_mode(frame):
    """Enhance frame brightness/contrast for dark rooms using CLAHE."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def crop_to_roi(frame, roi):
    """Crop frame to ROI (x, y, w, h). Returns original frame if roi is None."""
    if roi is None:
        return frame
    x, y, w, h = roi
    return frame[y:y+h, x:x+w]


def offset_contours(contours, roi):
    """Offset contour coordinates back to full-frame position."""
    if roi is None:
        return contours
    x, y, _, _ = roi
    return [c + np.array([x, y]) for c in contours]


def parse_roi_string(roi_str):
    """Parse 'x,y,w,h' string into tuple. Returns None if input is None."""
    if roi_str is None:
        return None
    parts = roi_str.split(",")
    if len(parts) != 4:
        raise ValueError(f"ROI must be x,y,w,h — got: {roi_str}")
    return tuple(int(p) for p in parts)


def throttle_fps(frame_start, target_fps):
    """Sleep to maintain target frame rate. No-op if target_fps is 0."""
    if target_fps <= 0:
        return
    frame_budget = 1.0 / target_fps
    elapsed = time.monotonic() - frame_start
    remaining = frame_budget - elapsed
    if remaining > 0:
        time.sleep(remaining)


def get_local_ip():
    """Get the local network IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


_tailscale_cache = {"ip": None, "expires": 0}


def get_tailscale_ip():
    """Get the Tailscale IP address (100.64.0.0/10 CGNAT range), or None if not connected."""
    now = time.monotonic()
    if now < _tailscale_cache["expires"]:
        return _tailscale_cache["ip"]
    try:
        result = subprocess.run(["ifconfig"], capture_output=True, text=True)
        for match in re.finditer(r'inet\s+(100\.(\d+)\.\d+\.\d+)', result.stdout):
            ip = match.group(1)
            second_octet = int(match.group(2))
            # Tailscale uses CGNAT range 100.64.0.0/10 (second octet 64-127)
            if 64 <= second_octet <= 127:
                _tailscale_cache["ip"] = ip
                _tailscale_cache["expires"] = now + 60
                return ip
    except Exception:
        pass
    _tailscale_cache["ip"] = None
    _tailscale_cache["expires"] = now + 60
    return None


def select_roi(cap):
    """Show first frame and let user draw ROI. Returns (x,y,w,h) or None if skipped."""
    ret, frame = cap.read()
    if not ret:
        return None
    print("Draw ROI and press ENTER, or press ENTER to skip.")
    roi = cv2.selectROI("BabyPing - Select ROI", frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("BabyPing - Select ROI")
    if roi == (0, 0, 0, 0):
        return None
    return roi


def try_open_camera(index):
    """Try to open a camera. Returns the VideoCapture or None if unavailable."""
    cap = cv2.VideoCapture(index)
    if cap.isOpened():
        return cap
    cap.release()
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if cap.isOpened():
        return cap
    cap.release()
    return None


def reconnect_camera(source, max_attempts=10, base_delay=2.0, rtsp_transport="tcp"):
    """Retry opening camera with exponential backoff. Returns cap or None."""
    for attempt in range(max_attempts):
        delay = min(base_delay * (2 ** attempt), 60)
        print(f"  Reconnect attempt {attempt + 1}/{max_attempts} (waiting {delay:.0f}s)...")
        time.sleep(delay)
        if _is_network_source(source):
            cap = ThreadedVideoCapture(source, rtsp_transport=rtsp_transport)
            if cap.isOpened():
                return cap
            cap.release()
        else:
            try:
                index = int(source)
            except ValueError:
                return None
            cap = try_open_camera(index)
            if cap is not None:
                return cap
    return None


def main():
    args = parse_args()
    frame_buffer.set_sensitivity(args.sensitivity)
    frame_buffer.set_fps(args.fps)
    threshold = SENSITIVITY_THRESHOLDS[args.sensitivity]
    camera_label = mask_credentials(args.camera) if _is_network_source(args.camera) else args.camera
    print(f"BabyPing starting — camera={camera_label}, sensitivity={args.sensitivity} ({threshold}px²), cooldown={args.cooldown}s")

    cap = open_camera_source(args.camera, rtsp_transport=args.rtsp_transport)
    print("Camera opened. Press 'q' to quit.")
    print(f"  Camera:       {camera_label}")
    print(f"  Sensitivity:  {args.sensitivity} ({threshold}px² threshold)")
    print(f"  Cooldown:     {args.cooldown}s")
    print(f"  Preview:      {'off' if args.no_preview else 'on'}")
    print(f"  Snapshots:    {args.snapshot_dir + ' (max: ' + str(args.max_snapshots) + ')' if args.snapshots else 'off'}")
    print(f"  Night mode:   {'on' if args.night_mode else 'off'}")

    roi = parse_roi_string(args.roi)
    if roi is None and not args.no_preview:
        roi = select_roi(cap)
    frame_buffer.set_roi(roi)
    if roi:
        print(f"  ROI:          {roi}")

    # Audio monitoring
    audio_monitor = None
    if not args.no_audio:
        try:
            from audio import AudioMonitor
            audio_monitor = AudioMonitor(
                device=args.audio_device,
                threshold=args.audio_threshold,
            )
            audio_monitor.start()
            frame_buffer.set_audio_enabled(True)
            print(f"  Audio:        on (device={args.audio_device or 'default'}, threshold={'auto' if args.audio_threshold is None else args.audio_threshold})")
        except Exception as e:
            print(f"  Audio:        failed ({e})")
    else:
        print(f"  Audio:        off")

    from events import EventLog
    event_log = EventLog(max_events=args.max_events)

    from web import create_app
    local_ip = get_local_ip()
    if args.host == "127.0.0.1":
        print(f"  Web UI:       http://127.0.0.1:{args.port} (localhost only)")
    else:
        print(f"  Web UI:       http://{local_ip}:{args.port}")
    tailscale_ip = get_tailscale_ip()
    if tailscale_ip:
        print(f"  Web UI:       http://{tailscale_ip}:{args.port} (Tailscale)")

    if args.host == "0.0.0.0" and not args.password:
        print("  WARNING:      Binding to 0.0.0.0 without --password exposes the web UI to the network without auth")
    if args.password:
        print(f"  Auth:         HTTP Basic Auth enabled")
    else:
        print(f"  Auth:         off")

    flask_app = create_app(args, frame_buffer, event_log=event_log)
    web_thread = start_web_server(flask_app, args.host, args.port)
    web_thread.start()
    print()

    prev_gray = None
    last_alert_time = 0
    last_sound_alert_time = 0
    consecutive_failures = 0
    max_frame_failures = 30
    event_count = 0

    try:
        while True:
            frame_start = time.monotonic()

            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures == 1:
                    print("Warning: Dropped frame — camera may be intermittent")
                if consecutive_failures >= max_frame_failures:
                    print(f"Camera lost after {consecutive_failures} dropped frames. Reconnecting...")
                    send_notification("BabyPing", "Camera disconnected — reconnecting...")
                    cap.release()
                    cap = reconnect_camera(args.camera, rtsp_transport=args.rtsp_transport)
                    if cap is None:
                        print("Error: Could not reconnect to camera. Exiting.")
                        send_notification("BabyPing", "Camera reconnect failed — stopping")
                        break
                    consecutive_failures = 0
                    prev_gray = None
                    print("Reconnected to camera.")
                    send_notification("BabyPing", "Camera reconnected")
                time.sleep(0.1)
                continue
            consecutive_failures = 0

            roi = frame_buffer.get_roi()
            threshold = SENSITIVITY_THRESHOLDS[frame_buffer.get_sensitivity()]

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            motion = False
            area = 0
            if prev_gray is not None:
                prev_cropped = cv2.GaussianBlur(crop_to_roi(prev_gray, roi), (21, 21), 0)
                curr_cropped = cv2.GaussianBlur(crop_to_roi(gray, roi), (21, 21), 0)
                motion, contours, area = detect_motion(prev_cropped, curr_cropped, threshold)

                if motion:
                    full_contours = offset_contours(contours, roi)
                    cv2.drawContours(frame, full_contours, -1, (0, 0, 255), 2)

            prev_gray = gray

            if roi:
                x, y, w, h = roi
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 1)

            display_frame = apply_night_mode(frame) if args.night_mode else frame

            if motion:
                now = time.time()
                if now - last_alert_time >= args.cooldown:
                    timestamp = datetime.now().isoformat(timespec="seconds")
                    snap_path = None
                    snap_msg = ""
                    if args.snapshots:
                        snap_path = save_snapshot(display_frame, args.snapshot_dir, args.max_snapshots)
                        if snap_path:
                            snap_msg = f" → {snap_path}"
                        else:
                            print("Warning: Snapshot save failed — disk may be full")
                    print(f"[{timestamp}] Motion detected — area={area:.0f}px²{snap_msg}")
                    if frame_buffer.get_motion_alerts_enabled():
                        send_notification("BabyPing", f"Motion detected ({area:.0f}px²)")
                    last_alert_time = now
                    frame_buffer.set_last_motion_time(now)

                    snap_filename = os.path.basename(snap_path) if args.snapshots and snap_path else None
                    event_log.log_event("motion", area=float(area), snapshot=snap_filename)
                    event_count += 1
                    if event_count % 100 == 0:
                        event_log.sync_to_disk()

            # Check audio monitor health
            if audio_monitor is not None and not audio_monitor.is_alive():
                print("Warning: Audio monitor stopped — disabling audio")
                send_notification("BabyPing", "Audio monitor disconnected")
                frame_buffer.set_audio_enabled(False)
                audio_monitor = None

            # Check web server health
            if not web_thread.is_alive():
                print("Warning: Web server stopped — restarting")
                send_notification("BabyPing", "Web server crashed — restarting")
                web_thread = start_web_server(flask_app, args.host, args.port)
                web_thread.start()

            # Sync audio state to frame buffer
            if audio_monitor is not None:
                frame_buffer.set_audio_level(audio_monitor.get_level())
                sound_time = audio_monitor.get_last_sound_time()
                if sound_time is not None:
                    frame_buffer.set_last_sound_time(sound_time)
                    if sound_time > last_sound_alert_time and time.time() - last_sound_alert_time >= args.cooldown:
                        last_sound_alert_time = sound_time
                        timestamp = datetime.now().isoformat(timespec="seconds")
                        print(f"[{timestamp}] Sound detected")
                        if frame_buffer.get_sound_alerts_enabled():
                            send_notification("BabyPing", "Sound detected")
                        event_log.log_event("sound")
                        event_count += 1
                        if event_count % 100 == 0:
                            event_log.sync_to_disk()

            if frame_buffer.has_viewers() or not args.no_preview:
                _, jpeg = cv2.imencode('.jpg', display_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                frame_buffer.update(jpeg.tobytes())
            if not args.no_preview:
                cv2.imshow("BabyPing", display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

            throttle_fps(frame_start, frame_buffer.get_fps())
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if audio_monitor is not None:
            audio_monitor.stop()
        cap.release()
        cv2.destroyAllWindows()
        print("BabyPing stopped.")


if __name__ == "__main__":
    main()
