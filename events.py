import collections
import json
import os
import threading
import time


VALID_EVENT_TYPES = ("motion", "sound")


class EventLog:
    """Thread-safe event logger backed by a JSONL file with in-memory cache."""

    def __init__(self, path="~/.babyping/events.jsonl", max_events=1000):
        self._path = os.path.expanduser(path)
        self._lock = threading.Lock()
        self._max_events = max_events
        self._events = collections.deque(maxlen=max_events if max_events > 0 else None)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._load_from_disk()

    def _load_from_disk(self):
        """Load existing events from the JSONL file into the in-memory deque."""
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        self._events.append(event)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    def log_event(self, event_type, **kwargs):
        """Append an event to both in-memory cache and log file.

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
            self._events.append(event)
            try:
                with open(self._path, "a") as f:
                    f.write(json.dumps(event) + "\n")
            except OSError:
                pass

    def get_events(self, limit=50, offset=0, event_type=None):
        """Read events from in-memory cache, newest first.

        Args:
            limit: Max events to return.
            offset: Number of events to skip (from newest).
            event_type: Filter by "motion" or "sound", or None for all.

        Returns:
            List of event dicts, newest first.
        """
        with self._lock:
            if event_type:
                events = [e for e in self._events if e.get("type") == event_type]
            else:
                events = list(self._events)

        events.reverse()
        return events[offset:offset + limit]

    def prune(self, max_events=1000):
        """Keep only the newest max_events entries in the file.

        The in-memory deque auto-prunes via maxlen. This method only
        trims the on-disk file for periodic maintenance.
        """
        with self._lock:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r") as f:
                lines = f.readlines()

            if len(lines) <= max_events:
                return

            keep = lines[-max_events:]
            with open(self._path, "w") as f:
                f.writelines(keep)

    def sync_to_disk(self):
        """Rewrite the JSONL file from the in-memory deque."""
        with self._lock:
            try:
                with open(self._path, "w") as f:
                    for event in self._events:
                        f.write(json.dumps(event) + "\n")
            except OSError:
                pass
