import json
import os
import threading
import time


VALID_EVENT_TYPES = ("motion", "sound")


class EventLog:
    """Thread-safe event logger backed by a JSONL file."""

    def __init__(self, path="~/.babyping/events.jsonl"):
        self._path = os.path.expanduser(path)
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def log_event(self, event_type, **kwargs):
        """Append an event to the log file.

        Args:
            event_type: "motion" or "sound"
            **kwargs: Optional keys — timestamp, area, audio_level, snapshot
        """
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type} (must be one of {VALID_EVENT_TYPES})")

        event = {
            "type": event_type,
            "timestamp": kwargs.get("timestamp", time.time()),
            "area": kwargs.get("area"),
            "audio_level": kwargs.get("audio_level"),
            "snapshot": kwargs.get("snapshot"),
        }

        with self._lock:
            try:
                with open(self._path, "a") as f:
                    f.write(json.dumps(event) + "\n")
            except OSError:
                pass

    def get_events(self, limit=50, offset=0, event_type=None):
        """Read events from the log, newest first.

        Args:
            limit: Max events to return.
            offset: Number of events to skip (from newest).
            event_type: Filter by "motion" or "sound", or None for all.

        Returns:
            List of event dicts, newest first.
        """
        with self._lock:
            if not os.path.exists(self._path):
                return []
            with open(self._path, "r") as f:
                lines = f.readlines()

        events = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type and event.get("type") != event_type:
                continue
            events.append(event)

        # Newest first
        events.reverse()
        return events[offset:offset + limit]

    def prune(self, max_events=1000):
        """Keep only the newest max_events entries."""
        with self._lock:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r") as f:
                lines = f.readlines()

            if len(lines) <= max_events:
                return

            # Keep the last max_events lines (newest)
            keep = lines[-max_events:]
            with open(self._path, "w") as f:
                f.writelines(keep)
