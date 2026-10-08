"""
Lightweight in-memory rate limiter. Guests are limited by IP (tight limit,
e.g. 3/hour); logged-in users are limited by user id (looser limit, e.g.
15/minute). In-memory is fine for a single-process free-tier deploy; swap
for Redis if you ever scale to multiple workers.
"""

import re
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, status

_LIMIT_RE = re.compile(r"^(\d+)/(second|minute|hour|day)$")
_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def _parse_limit(limit_str: str):
    match = _LIMIT_RE.match(limit_str.strip())
    if not match:
        raise ValueError(f"Invalid rate limit format: {limit_str}")
    count, unit = match.groups()
    return int(count), _UNIT_SECONDS[unit]


class RateLimiter:
    def __init__(self):
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit_str: str) -> None:
        max_count, window_seconds = _parse_limit(limit_str)
        now = time.time()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= max_count:
                retry_after = int(window_seconds - (now - bucket[0]))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded ({limit_str}). Try again in ~{retry_after}s, "
                    f"or log in for a higher limit.",
                )
            bucket.append(now)


rate_limiter = RateLimiter()
