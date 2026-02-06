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

    def test_index_snapshots_disabled(self, client):
        resp = client.get("/")
        assert b"false" in resp.data  # SNAPSHOTS_ENABLED = false


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

    def test_index_snapshots_enabled(self, snap_client):
        resp = snap_client.get("/")
        assert b"true" in resp.data  # SNAPSHOTS_ENABLED = true


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
