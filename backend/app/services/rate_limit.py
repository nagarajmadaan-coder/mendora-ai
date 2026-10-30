"""
A small in-memory rate limiter (sliding window).

Used to slow down password guessing and to cap AI diagnosis calls (which cost money).
It resets when the server restarts and is per-process — fine for this prototype.
"""

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] >= self.window:
            events.popleft()
        return events

    def is_limited(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_events

    def hit(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def retry_after(self, key: str) -> int:
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, now)
            return max(1, int(self.window - (now - events[0])) + 1) if events else 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)
