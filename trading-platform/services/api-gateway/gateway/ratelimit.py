from collections import deque
from typing import Callable, Optional


class RateLimiter:
    """Sliding window: at most `limit` hits per `window` seconds for each key."""

    def __init__(self, clock: Callable[[], float]):
        self.clock, self.hits = clock, {}

    def check(self, key, limit: int, window: float = 60.0) -> Optional[float]:
        """None if allowed (and counted). Otherwise the seconds to wait."""
        now = self.clock()
        if len(self.hits) > 10_000:  # forget keys that have gone quiet, so memory can't grow forever
            self.hits = {k: q for k, q in self.hits.items() if q and q[-1] > now - window}
        q = self.hits.setdefault(key, deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return q[0] + window - now
        q.append(now)
        return None
