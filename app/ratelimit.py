"""
app/ratelimit.py — Per-client sliding-window rate limiter (in-memory, dependency-free).

Protects the paid/external calls behind /search (Groq) and /web-enrich (DuckDuckGo) from being
drained by a scripted run. Keyed on the direct peer address only — X-Forwarded-For is spoofable, so
put a trusted reverse proxy in front for multi-instance deployments (or swap in Redis).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request


def parse_limit(spec: str) -> tuple[int, int]:
    calls, _, window = spec.partition("/")
    return max(1, int(calls)), max(1, int(window or 60))


class SlidingWindowLimiter:
    def __init__(self, calls: int, window_seconds: int):
        self.calls, self.window = calls, window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """Record a hit. Returns 0.0 if allowed, else seconds until the client may retry."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.calls:
                return self.window - (now - q[0])
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                    del self._hits[k]
            return 0.0


def rate_limit(limiter: SlidingWindowLimiter):
    """FastAPI dependency factory."""
    def dep(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        wait = limiter.check(client)
        if wait > 0:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.",
                                headers={"Retry-After": str(int(wait) + 1)})
    return dep
