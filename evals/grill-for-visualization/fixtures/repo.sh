#!/usr/bin/env bash
# A small API gateway whose rate limiter is the thing to visualize. The
# numbers the video must show (capacity 10, refill 2/s, 429 + Retry-After)
# are all in the code, so a good grill reads them instead of asking.
set -euo pipefail

cat >ratelimit.py <<'PY'
import math
import time
from dataclasses import dataclass, field

CAPACITY = 10
REFILL_PER_SECOND = 2.0


@dataclass
class TokenBucket:
    tokens: float = CAPACITY
    updated_at: float = field(default_factory=time.monotonic)

    def take(self, now: float) -> bool:
        elapsed = now - self.updated_at
        self.tokens = min(CAPACITY, self.tokens + elapsed * REFILL_PER_SECOND)
        self.updated_at = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True

    def retry_after(self) -> int:
        return math.ceil((1 - self.tokens) / REFILL_PER_SECOND)


buckets: dict[str, TokenBucket] = {}


def allow(api_key: str, now: float) -> tuple[bool, int]:
    bucket = buckets.setdefault(api_key, TokenBucket(updated_at=now))
    if bucket.take(now):
        return True, 0
    return False, bucket.retry_after()
PY

cat >gateway.py <<'PY'
import time

from ratelimit import allow


def handle(api_key: str) -> tuple[int, dict[str, str]]:
    ok, retry_after = allow(api_key, time.monotonic())
    if not ok:
        return 429, {"Retry-After": str(retry_after)}
    return 200, {}
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
