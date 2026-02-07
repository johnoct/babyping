import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from events import EventLog


@pytest.fixture
def tmp_events_file(tmp_path):
    """Return a path to a temporary JSONL file for testing."""
    return str(tmp_path / "events.jsonl")


@pytest.fixture
def event_log(tmp_events_file):
    """Return an EventLog instance using a temporary file."""
    return EventLog(tmp_events_file)


class TestEventLogInit:
    def test_creates_parent_directory(self, tmp_path):
        path = str(tmp_path / "subdir" / "events.jsonl")
        log = EventLog(path)
        assert os.path.isdir(os.path.dirname(path))

    def test_works_with_existing_directory(self, tmp_events_file):
        log = EventLog(tmp_events_file)
        assert log is not None


class TestLogEvent:
    def test_log_motion_event(self, event_log, tmp_events_file):
        event_log.log_event("motion", area=1234.5)
        with open(tmp_events_file) as f:
            line = f.readline()
        data = json.loads(line)
        assert data["type"] == "motion"
        assert data["area"] == 1234.5
        assert data["audio_level"] is None
        assert data["snapshot"] is None
        assert isinstance(data["timestamp"], float)

    def test_log_sound_event(self, event_log, tmp_events_file):
        event_log.log_event("sound", audio_level=0.85)
        with open(tmp_events_file) as f:
            line = f.readline()
        data = json.loads(line)
        assert data["type"] == "sound"
        assert data["audio_level"] == 0.85
        assert data["area"] is None

    def test_log_event_with_snapshot(self, event_log, tmp_events_file):
        event_log.log_event("motion", area=500.0, snapshot="2026-02-06T12-00-00.jpg")
        with open(tmp_events_file) as f:
            data = json.loads(f.readline())
        assert data["snapshot"] == "2026-02-06T12-00-00.jpg"

    def test_log_event_with_custom_timestamp(self, event_log, tmp_events_file):
        ts = 1700000000.0
        event_log.log_event("motion", timestamp=ts, area=100.0)
        with open(tmp_events_file) as f:
            data = json.loads(f.readline())
        assert data["timestamp"] == ts

    def test_log_multiple_events(self, event_log, tmp_events_file):
        event_log.log_event("motion", area=100.0)
        event_log.log_event("sound", audio_level=0.5)
        event_log.log_event("motion", area=200.0)
        with open(tmp_events_file) as f:
            lines = f.readlines()
        assert len(lines) == 3

    def test_log_event_invalid_type_raises(self, event_log):
        with pytest.raises(ValueError):
            event_log.log_event("unknown")


class TestGetEvents:
    def test_get_events_empty(self, event_log):
        events = event_log.get_events()
        assert events == []

    def test_get_events_returns_newest_first(self, event_log):
        event_log.log_event("motion", timestamp=1.0, area=100.0)
        event_log.log_event("motion", timestamp=2.0, area=200.0)
        event_log.log_event("motion", timestamp=3.0, area=300.0)
        events = event_log.get_events()
        assert events[0]["timestamp"] == 3.0
        assert events[-1]["timestamp"] == 1.0

    def test_get_events_limit(self, event_log):
        for i in range(10):
            event_log.log_event("motion", timestamp=float(i), area=float(i))
        events = event_log.get_events(limit=3)
        assert len(events) == 3
        assert events[0]["timestamp"] == 9.0

    def test_get_events_offset(self, event_log):
        for i in range(10):
            event_log.log_event("motion", timestamp=float(i), area=float(i))
        events = event_log.get_events(limit=3, offset=2)
        assert len(events) == 3
        # Newest first: 9,8,7,6,5... offset 2 skips 9,8 -> returns 7,6,5
        assert events[0]["timestamp"] == 7.0

    def test_get_events_filter_by_type(self, event_log):
        event_log.log_event("motion", timestamp=1.0, area=100.0)
        event_log.log_event("sound", timestamp=2.0, audio_level=0.5)
        event_log.log_event("motion", timestamp=3.0, area=200.0)
        motion_events = event_log.get_events(event_type="motion")
        assert len(motion_events) == 2
        assert all(e["type"] == "motion" for e in motion_events)

        sound_events = event_log.get_events(event_type="sound")
        assert len(sound_events) == 1
        assert sound_events[0]["type"] == "sound"

    def test_get_events_no_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.jsonl")
        log = EventLog(path)
        assert log.get_events() == []

    def test_get_events_offset_beyond_end(self, event_log):
        event_log.log_event("motion", timestamp=1.0, area=100.0)
        events = event_log.get_events(offset=10)
        assert events == []


class TestPrune:
    def test_prune_removes_oldest_from_file(self, event_log, tmp_events_file):
        for i in range(10):
            event_log.log_event("motion", timestamp=float(i), area=float(i))
        event_log.prune(max_events=5)
        # Verify the file was pruned
        with open(tmp_events_file) as f:
            lines = f.readlines()
        assert len(lines) == 5
        # A new EventLog loading from disk should see only 5 events
        log2 = EventLog(tmp_events_file)
        events = log2.get_events(limit=100)
        assert len(events) == 5
        timestamps = [e["timestamp"] for e in events]
        assert min(timestamps) == 5.0
        assert max(timestamps) == 9.0

    def test_prune_no_op_when_under_limit(self, event_log, tmp_events_file):
        for i in range(3):
            event_log.log_event("motion", timestamp=float(i), area=float(i))
        event_log.prune(max_events=10)
        events = event_log.get_events(limit=100)
        assert len(events) == 3

    def test_prune_empty_file(self, event_log):
        event_log.prune(max_events=5)  # Should not raise
        assert event_log.get_events() == []


class TestThreadSafety:
    def test_concurrent_writes(self, event_log):
        """Multiple threads writing events should not corrupt the file."""
        errors = []

        def writer(event_type, count):
            try:
                for i in range(count):
                    event_log.log_event(event_type, area=float(i) if event_type == "motion" else None,
                                        audio_level=float(i) / 10 if event_type == "sound" else None)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("motion", 50)),
            threading.Thread(target=writer, args=("sound", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        events = event_log.get_events(limit=200)
        assert len(events) == 100


class TestInMemoryCache:
    def test_get_events_reads_from_memory(self, tmp_events_file):
        """get_events should work from in-memory cache without file I/O after init."""
        log = EventLog(tmp_events_file)
        log.log_event("motion", timestamp=1.0, area=100.0)
        log.log_event("motion", timestamp=2.0, area=200.0)

        # Delete the file — get_events should still work from memory
        os.remove(tmp_events_file)
        events = log.get_events()
        assert len(events) == 2
        assert events[0]["timestamp"] == 2.0

    def test_events_loaded_from_disk_on_init(self, tmp_events_file):
        """Events written to disk should be loaded into memory on init."""
        # Write events directly to file
        with open(tmp_events_file, "w") as f:
            f.write(json.dumps({"type": "motion", "timestamp": 1.0, "area": 100.0, "audio_level": None, "snapshot": None}) + "\n")
            f.write(json.dumps({"type": "sound", "timestamp": 2.0, "area": None, "audio_level": 0.5, "snapshot": None}) + "\n")

        # Create a new EventLog — should load from disk
        log = EventLog(tmp_events_file)
        events = log.get_events()
        assert len(events) == 2
        assert events[0]["timestamp"] == 2.0
        assert events[1]["timestamp"] == 1.0

    def test_deque_auto_prunes_at_maxlen(self, tmp_events_file):
        """Deque should auto-prune old events when max_events is reached."""
        log = EventLog(tmp_events_file, max_events=5)
        for i in range(10):
            log.log_event("motion", timestamp=float(i), area=float(i))

        events = log.get_events(limit=100)
        assert len(events) == 5
        # Should keep the 5 newest (timestamps 5-9)
        timestamps = [e["timestamp"] for e in events]
        assert min(timestamps) == 5.0
        assert max(timestamps) == 9.0

    def test_sync_to_disk(self, tmp_events_file):
        """sync_to_disk should rewrite the file from the in-memory deque."""
        log = EventLog(tmp_events_file, max_events=3)
        for i in range(5):
            log.log_event("motion", timestamp=float(i), area=float(i))

        # File has all 5 appended lines, but deque only has last 3
        log.sync_to_disk()

        # Verify the file now only has 3 events
        with open(tmp_events_file) as f:
            lines = f.readlines()
        assert len(lines) == 3

        # Verify a new EventLog loads the synced data correctly
        log2 = EventLog(tmp_events_file, max_events=3)
        events = log2.get_events(limit=100)
        assert len(events) == 3
        assert events[0]["timestamp"] == 4.0

    def test_disk_error_still_caches_in_memory(self, tmp_path):
        """Even if disk write fails, events should be in memory."""
        events_file = str(tmp_path / "events.jsonl")
        log = EventLog(events_file)
        log.log_event("motion", area=100.0)
        os.chmod(events_file, 0o444)
        try:
            log.log_event("motion", area=200.0)
            events = log.get_events()
            assert len(events) == 2
        finally:
            os.chmod(events_file, 0o644)


class TestDiskErrorHandling:
    def test_log_event_survives_disk_error(self, tmp_path):
        """log_event should not raise when disk write fails."""
        events_file = str(tmp_path / "events.jsonl")
        log = EventLog(events_file)
        # Make the file read-only to simulate disk error
        log.log_event("motion", area=100.0)  # First write succeeds
        os.chmod(events_file, 0o444)
        try:
            log.log_event("motion", area=200.0)  # Should not raise
        finally:
            os.chmod(events_file, 0o644)  # Restore for cleanup
