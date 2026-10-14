"""In-memory sliding-window rate limit per client (one API instance on the free tier)."""

import time
from collections import deque

from fastapi import Request


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, retry_after_seconds)."""
        now = time.monotonic()
        q = self.hits.setdefault(key, deque())
        while q and q[0] <= now - 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False, 0, max(1, int(60 - (now - q[0])) + 1)
        q.append(now)
        if len(self.hits) > 20000:  # bound memory
            for k in list(self.hits)[:5000]:
                if not self.hits[k]:
                    del self.hits[k]
        return True, self.per_minute - len(q), 0


def client_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and len(auth) > 40:
        return "tok:" + auth[-32:]  # per token (≈ per user); not used for identity
    fwd = request.headers.get("x-forwarded-for", "")
    return "ip:" + (fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown"))
