"""
Rolling in-memory cache for scraped article text.

Design (Option B from the plan): a fixed-size FIFO cache. When a new URL is
scraped and the cache is full, the oldest entry is evicted automatically.

- Never touches disk.
- Never persisted to the database.
- Naturally resets on every process restart/redeploy -- that's treated as a
  feature here, not a bug, since scraped full-text is intentionally temporary.
"""

import threading
from collections import OrderedDict
from typing import Optional

from app.config import settings


class RollingScrapeCache:
    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self._store: "OrderedDict[str, str]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, url: str) -> Optional[str]:
        with self._lock:
            if url in self._store:
                # move to the end -> mark as most-recently-used
                self._store.move_to_end(url)
                return self._store[url]
            return None

    def set(self, url: str, text: str) -> None:
        with self._lock:
            if url in self._store:
                self._store.move_to_end(url)
            self._store[url] = text
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)  # evict oldest (FIFO)

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Single shared instance used by SearchAgent
scrape_cache = RollingScrapeCache(max_size=settings.scrape_cache_size)
