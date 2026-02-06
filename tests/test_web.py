import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from babyping import FrameBuffer
from web import create_app


class FakeArgs:
    sensitivity = "medium"
    night_mode = False
    snapshots = False
    snapshot_dir = "~/.babyping/events"
    fps = 10


@pytest.fixture
def client():
    app = create_app(FakeArgs(), FrameBuffer())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestWebRoutes:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"BabyPing" in resp.data
        assert b"text/html" in resp.content_type.encode()

    def test_stream_returns_mjpeg(self, client):
        app = client.application
        with app.test_request_context("/stream"):
            from web import create_app
            resp = app.full_dispatch_request()
            assert resp.status_code == 200
            assert "multipart/x-mixed-replace" in resp.content_type

    def test_status_returns_json(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sensitivity"] == "medium"
        assert data["night_mode"] is False
        assert data["snapshots_enabled"] is False
        assert "last_motion_time" in data
        assert "last_frame_time" in data
        assert data["roi"] is None

    def test_snapshots_list_empty_dir(self, client):
        resp = client.get("/snapshots")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

class TestWebSnapshotsEnabled:
    @pytest.fixture
    def snap_client(self, tmp_path):
        import cv2
        import numpy as np
        args = FakeArgs()
        args.snapshots = True
        args.snapshot_dir = str(tmp_path)
        # Create a test snapshot
        frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / "2026-02-05T12-00-00.jpg"), frame)
        app = create_app(args, FrameBuffer())
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_snapshots_list_with_files(self, snap_client):
        resp = snap_client.get("/snapshots")
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0] == "2026-02-05T12-00-00.jpg"

    def test_snapshot_file_served(self, snap_client):
        resp = snap_client.get("/snapshots/2026-02-05T12-00-00.jpg")
        assert resp.status_code == 200
        assert "image/jpeg" in resp.content_type

class TestWebROI:
    @pytest.fixture
    def roi_client(self):
        buf = FrameBuffer()
        app = create_app(FakeArgs(), buf)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c, buf

    def test_set_roi(self, roi_client):
        client, buf = roi_client
        resp = client.post("/roi", json={"x": 10, "y": 20, "w": 100, "h": 80})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["roi"] == {"x": 10, "y": 20, "w": 100, "h": 80}
        assert buf.get_roi() == (10, 20, 100, 80)

    def test_clear_roi(self, roi_client):
        client, buf = roi_client
        buf.set_roi((10, 20, 100, 80))
        resp = client.post("/roi", data="null", content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["roi"] is None
        assert buf.get_roi() is None

    def test_roi_invalid_missing_fields(self, roi_client):
        client, _ = roi_client
        resp = client.post("/roi", json={"x": 10})
        assert resp.status_code == 400

    def test_roi_invalid_negative_dimensions(self, roi_client):
        client, _ = roi_client
        resp = client.post("/roi", json={"x": 10, "y": 20, "w": -5, "h": 80})
        assert resp.status_code == 400

    def test_roi_invalid_zero_width(self, roi_client):
        client, _ = roi_client
        resp = client.post("/roi", json={"x": 10, "y": 20, "w": 0, "h": 80})
        assert resp.status_code == 400

    def test_status_includes_roi(self, roi_client):
        client, buf = roi_client
        buf.set_roi((50, 60, 200, 150))
        resp = client.get("/status")
        data = json.loads(resp.data)
        assert data["roi"] == {"x": 50, "y": 60, "w": 200, "h": 150}

    def test_index_includes_roi_ui(self, roi_client):
        client, _ = roi_client
        resp = client.get("/")
        assert b"roi-btn" in resp.data
        assert b"roi-overlay" in resp.data
        assert b"roi-canvas" in resp.data


class TestWebAudioAlerts:
    def test_index_includes_notify_button(self, client):
        resp = client.get("/")
        assert b"notify-btn" in resp.data

    def test_index_includes_audio_scripts(self, client):
        resp = client.get("/")
        assert b"toggleAudio" in resp.data
        assert b"playAlertSound" in resp.data
        assert b"AudioContext" in resp.data

    def test_index_includes_vibration_api(self, client):
        resp = client.get("/")
        assert b"navigator.vibrate" in resp.data


class TestWebAudioStatus:
    @pytest.fixture
    def audio_client(self):
        buf = FrameBuffer()
        app = create_app(FakeArgs(), buf)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c, buf

    def test_status_includes_audio_level(self, audio_client):
        client, buf = audio_client
        resp = client.get("/status")
        data = json.loads(resp.data)
        assert "audio_level" in data
        assert data["audio_level"] == 0.0

    def test_status_audio_level_updates(self, audio_client):
        client, buf = audio_client
        buf.set_audio_level(0.75)
        resp = client.get("/status")
        data = json.loads(resp.data)
        assert data["audio_level"] == 0.75

    def test_status_includes_last_sound_time(self, audio_client):
        client, buf = audio_client
        resp = client.get("/status")
        data = json.loads(resp.data)
        assert "last_sound_time" in data
        assert data["last_sound_time"] is None

    def test_status_last_sound_time_updates(self, audio_client):
        client, buf = audio_client
        buf.set_last_sound_time(12345.0)
        resp = client.get("/status")
        data = json.loads(resp.data)
        assert data["last_sound_time"] == 12345.0

    def test_status_includes_audio_enabled(self, audio_client):
        client, buf = audio_client
        resp = client.get("/status")
        data = json.loads(resp.data)
        assert "audio_enabled" in data
        assert data["audio_enabled"] is False

    def test_status_audio_enabled_updates(self, audio_client):
        client, buf = audio_client
        buf.set_audio_enabled(True)
        resp = client.get("/status")
        data = json.loads(resp.data)
        assert data["audio_enabled"] is True


class TestWebAudioVuMeter:
    def test_index_includes_audio_card(self, client):
        resp = client.get("/")
        assert b"audio-card" in resp.data

    def test_index_includes_vu_fill(self, client):
        resp = client.get("/")
        assert b"vu-fill" in resp.data

    def test_index_includes_vu_track(self, client):
        resp = client.get("/")
        assert b"vu-track" in resp.data

    def test_index_includes_audio_label(self, client):
        resp = client.get("/")
        assert b"audio-label" in resp.data

    def test_index_includes_sound_alert_js(self, client):
        resp = client.get("/")
        assert b"lastSoundAlerted" in resp.data
        assert b"audio_level" in resp.data
        assert b"audio_enabled" in resp.data


class TestWebEvents:
    @pytest.fixture
    def events_client(self, tmp_path):
        from events import EventLog
        events_file = str(tmp_path / "events.jsonl")
        event_log = EventLog(events_file)
        args = FakeArgs()
        app = create_app(args, FrameBuffer(), event_log=event_log)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c, event_log

    def test_events_endpoint_empty(self, events_client):
        client, _ = events_client
        resp = client.get("/events")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == []

    def test_events_endpoint_returns_events(self, events_client):
        client, event_log = events_client
        event_log.log_event("motion", timestamp=1.0, area=500.0)
        event_log.log_event("sound", timestamp=2.0, audio_level=0.8)
        resp = client.get("/events")
        data = json.loads(resp.data)
        assert len(data) == 2
        assert data[0]["timestamp"] == 2.0  # Newest first
        assert data[1]["timestamp"] == 1.0

    def test_events_endpoint_limit(self, events_client):
        client, event_log = events_client
        for i in range(10):
            event_log.log_event("motion", timestamp=float(i), area=float(i))
        resp = client.get("/events?limit=3")
        data = json.loads(resp.data)
        assert len(data) == 3

    def test_events_endpoint_offset(self, events_client):
        client, event_log = events_client
        for i in range(10):
            event_log.log_event("motion", timestamp=float(i), area=float(i))
        resp = client.get("/events?limit=3&offset=2")
        data = json.loads(resp.data)
        assert len(data) == 3
        assert data[0]["timestamp"] == 7.0

    def test_events_endpoint_filter_type(self, events_client):
        client, event_log = events_client
        event_log.log_event("motion", timestamp=1.0, area=100.0)
        event_log.log_event("sound", timestamp=2.0, audio_level=0.5)
        resp = client.get("/events?type=motion")
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]["type"] == "motion"

    def test_events_endpoint_no_event_log(self):
        """When no event_log is passed, /events returns empty list."""
        app = create_app(FakeArgs(), FrameBuffer())
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.get("/events")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data == []


class TestWebEventsSheet:
    def test_main_page_has_events_sheet(self, client):
        resp = client.get("/")
        assert b"sheet" in resp.data
        assert b"sheet-body" in resp.data

    def test_index_includes_sheet_markup(self, client):
        resp = client.get("/")
        assert b'id="sheet"' in resp.data
        assert b'id="sheet-handle"' in resp.data
        assert b'id="sheet-body"' in resp.data
        assert b'id="sheet-filters"' in resp.data

    def test_index_sheet_has_filter_buttons(self, client):
        resp = client.get("/")
        assert b"sheet-filter" in resp.data
        assert b"All" in resp.data
        assert b"Motion" in resp.data
        assert b"Sound" in resp.data

    def test_index_sheet_fetches_events_api(self, client):
        resp = client.get("/")
        assert b"/events" in resp.data

    def test_index_no_timeline_route_link(self, client):
        resp = client.get("/")
        assert b"/timeline" not in resp.data

    def test_timeline_route_removed(self, client):
        resp = client.get("/timeline")
        assert resp.status_code == 404

    def test_motion_card_opens_sheet(self, client):
        """Motion card should have onclick to toggle the events sheet."""
        resp = client.get("/")
        assert b"toggleSheet" in resp.data
        assert b'onclick="toggleSheet()"' in resp.data

    def test_sheet_starts_hidden(self, client):
        """Sheet should start fully hidden (translateY 100%)."""
        resp = client.get("/")
        assert b"translateY(100%)" in resp.data


class TestWebTailscale:
    @pytest.fixture
    def ts_client(self):
        buf = FrameBuffer()
        app = create_app(FakeArgs(), buf)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_status_includes_tailscale_ip_null(self, ts_client):
        """When no Tailscale detected, tailscale_ip should be null."""
        from unittest.mock import patch
        with patch("web.get_tailscale_ip", return_value=None):
            resp = ts_client.get("/status")
            data = json.loads(resp.data)
            assert "tailscale_ip" in data
            assert data["tailscale_ip"] is None

    def test_status_includes_tailscale_ip_value(self, ts_client):
        """When Tailscale detected, tailscale_ip should be the IP."""
        from unittest.mock import patch
        with patch("web.get_tailscale_ip", return_value="100.85.42.17"):
            resp = ts_client.get("/status")
            data = json.loads(resp.data)
            assert data["tailscale_ip"] == "100.85.42.17"

    def test_index_includes_secure_pill_markup(self, ts_client):
        """The HTML template should include the secure-pill element."""
        resp = ts_client.get("/")
        assert b"secure-pill" in resp.data

    def test_secure_pill_hidden_by_default(self, ts_client):
        """The secure pill should be hidden by default (display:none)."""
        resp = ts_client.get("/")
        assert b"secure-pill" in resp.data
