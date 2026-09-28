#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../_lib.sh
source "$(dirname "$0")/../_lib.sh"

repo="$1/gatekeeper"
init_repo "${repo}" "feat/rate-limit"
mkdir -p "${repo}/gatekeeper" "${repo}/tests" \
	"${repo}/docs/handoffs/feat-rate-limit"

cat >"${repo}/gatekeeper/bucket.lua" <<'EOF'
-- KEYS[1] bucket key; ARGV: capacity, refill_per_sec
local now = redis.call('TIME')
local t = tonumber(now[1]) + tonumber(now[2]) / 1e6
local b = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local cap, rate = tonumber(ARGV[1]), tonumber(ARGV[2])
local tokens = tonumber(b[1]) or cap
local ts = tonumber(b[2]) or t
tokens = math.min(cap, tokens + (t - ts) * rate)
local allowed = tokens >= 1
if allowed then tokens = tokens - 1 end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', t)
redis.call('EXPIRE', KEYS[1], math.ceil(cap / rate) + 1)
return allowed and 1 or 0
EOF

cat >"${repo}/gatekeeper/limiter.py" <<'EOF'
from pathlib import Path

import redis

SCRIPT = (Path(__file__).parent / "bucket.lua").read_text()


class Limiter:
    def __init__(self, url: str, capacity: int, refill_per_sec: float) -> None:
        self.client = redis.Redis.from_url(url)
        self.script = self.client.register_script(SCRIPT)
        self.capacity = capacity
        self.refill = refill_per_sec

    def allow(self, key: str) -> bool:
        return bool(self.script(keys=[key], args=[self.capacity, self.refill]))
EOF

cat >"${repo}/gatekeeper/app.py" <<'EOF'
from fastapi import FastAPI

app = FastAPI()


@app.get("/v1/items")
def items() -> list[str]:
    return []
EOF

cat >"${repo}/tests/test_bucket.py" <<'EOF'
def test_bucket_allows_then_denies(limiter) -> None:
    assert all(limiter.allow("k") for _ in range(5))
    assert not limiter.allow("k")
EOF

cat >"${repo}/docs/handoffs/feat-rate-limit/NARRATIVE.md" <<'EOF'
# Project narrative

## 2026-09-25 — handoff #1

### Tried and failed

- Fixed-window counter with Redis `INCR` + `EXPIRE` → a client can send 2x
  the limit across a window boundary (burst at :59/:00) → dropped for a
  token bucket.
- Token bucket computed in Python with `GET`/`SET` → race between
  concurrent gateway replicas double-spends tokens → moved the whole
  read-modify-write into a Lua script so Redis runs it atomically.

### Decisions and constraints

- **Fail open**: if Redis is unavailable the gateway must allow the
  request. User: availability beats strict limiting for this service.
- Lua uses `redis.call('TIME')`, not the caller's clock, so replicas with
  clock skew agree.
- No new dependencies beyond `redis` (already in the lockfile).

### Done — with evidence

- Token bucket Lua + `Limiter` — `uv run pytest tests/test_bucket.py` →
  1 passed

### Lessons and surprises

- The dev Redis is at `redis://localhost:6380/0` — 6379 is taken by
  another project's container.
EOF

cat >"${repo}/docs/handoffs/feat-rate-limit/CURRENT.md" <<'EOF'
# Continue here: gateway rate limiting

**Status:** in-progress

**Written:** 2026-09-25 17:40 · **Branch:** `feat/rate-limit` · **HEAD:** (see git log) ·
**Tree:** clean · **Handoff:** #1 of this thread

## Goal

Per-API-key rate limiting in the gatekeeper gateway, so one noisy client can't starve others.

## Read in this order

1. `NARRATIVE.md` — all of it (short).
2. `gatekeeper/limiter.py`, `gatekeeper/bucket.lua`.

## In flight

- Nothing.

## Next action

Wire `Limiter.allow()` into `gatekeeper/app.py` as middleware keyed on the `X-Api-Key`
header; return 429 with `Retry-After` when denied.

## Acceptance check

```bash
uv run pytest -q
```

## Open questions — blocked on the user

- (none)
EOF

commit "${repo}" "2026-09-25T17:40:00Z" "feat: token bucket limiter (lua)"

cat >"${repo}/gatekeeper/app.py" <<'EOF'
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gatekeeper.limiter import Limiter

app = FastAPI()
limiter = Limiter(os.environ["RATE_LIMIT_REDIS_URL"], capacity=20, refill_per_sec=5)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    key = request.headers.get("X-Api-Key", "anonymous")
    if not limiter.allow(f"rl:{key}"):
        return JSONResponse({"error": "rate limited"}, status_code=429,
                            headers={"Retry-After": "1"})
    return await call_next(request)


@app.get("/v1/items")
def items() -> list[str]:
    return []
EOF
commit "${repo}" "2026-09-28T10:15:00Z" "feat: rate-limit middleware"

cat >"${repo}/gatekeeper/limiter.py" <<'EOF'
from pathlib import Path

import redis

SCRIPT = (Path(__file__).parent / "bucket.lua").read_text()


class Limiter:
    def __init__(self, url: str, capacity: int, refill_per_sec: float) -> None:
        self.client = redis.Redis.from_url(url)
        self.script = self.client.register_script(SCRIPT)
        self.capacity = capacity
        self.refill = refill_per_sec

    def allow(self, key: str) -> bool:
        try:
            return bool(
                self.script(keys=[key], args=[self.capacity, self.refill])
            )
        except redis.exceptions.ConnectionError:
            return True
EOF

cat >"${repo}/gatekeeper/config.py" <<'EOF'
import os

REDIS_TIMEOUT_S = int(os.environ.get("RATE_LIMIT_REDIS_TIMEOUT_MS", "50")) / 1000
EOF
