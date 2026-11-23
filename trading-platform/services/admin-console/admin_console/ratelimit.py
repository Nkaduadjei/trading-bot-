from collections import deque


class RateLimiter:
    def __init__(self, clock):
        self.clock, self.hits = clock, {}

    def check(self, key, limit, window=60.0):
        """None if allowed, otherwise seconds to wait."""
        now = self.clock()
        q = self.hits.setdefault(key, deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return q[0] + window - now
        q.append(now)
        return None
