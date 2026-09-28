*(This session began by resuming from `docs/handoffs/feat-rate-limit/CURRENT.md`, handoff #1.)*

**Assistant:** Resuming. Goal: per-API-key rate limiting in gatekeeper. The next action from the handoff is to wire `Limiter.allow()` into `app.py` as middleware. The anchor is `feat/rate-limit`, and the tree is clean.

**User:** Yep, go.

**Assistant:**

> Edited `gatekeeper/app.py`: `@app.middleware("http")` keyed on `X-Api-Key`, returns 429 + `Retry-After: 1`
>
> `$ RATE_LIMIT_REDIS_URL=redis://localhost:6380/0 uv run pytest -q`
> ```
> 3 passed in 0.41s
> ```

Middleware works against the dev Redis.

**User:** Commit it.

> `$ git commit -am "feat: rate-limit middleware"`

**Assistant:** Committed. Next I'm checking the fail-open behavior from the narrative's constraints: if Redis is down, `allow()` should return True. Right now the exception propagates and the request 500s. Adding a `try/except redis.exceptions.ConnectionError: return True`.

> Edited `gatekeeper/limiter.py`
>
> `$ docker stop gk-redis && RATE_LIMIT_REDIS_URL=redis://localhost:6380/0 uv run python -c "from gatekeeper.limiter import Limiter; print(Limiter('redis://localhost:6380/0', 5, 1).allow('k'))"`
> ```
> True
> ```

Redis stopped: it returns True immediately. Now the nastier case: Redis is up but *unresponsive* (a network partition rather than a refused connection).

> `$ docker pause gk-redis && time uv run python -c "..."`
> ```
> ^C  (hung for 60s+)
> ```

It hangs. redis-py's default `socket_timeout` is `None`, so a paused server blocks forever and never raises `ConnectionError`. Fail-open is useless if every request hangs first. The fix is to set `socket_timeout` (and `socket_connect_timeout`) on the client and also catch `redis.exceptions.TimeoutError`.

I tried `socket_timeout=0.05` inline and it works: the call returns True after about 50ms.

**User:** Don't hardcode that. Make it configurable, env var `RATE_LIMIT_REDIS_TIMEOUT_MS`, default 50.

**Assistant:** Done in `gatekeeper/config.py` (`REDIS_TIMEOUT_S`, read from the env var, default 50ms). I haven't wired it into `Limiter` yet. `limiter.py` still constructs the client without any timeout (`redis.Redis.from_url(url)` in `__init__`), and the `except` only catches `ConnectionError`, not `TimeoutError`. I reverted the inline 0.05 experiment.

I also need a regression test for the hang, `test_fail_open_on_timeout`. It can use a socket that accepts but never replies, so it doesn't need docker.

**User:** Sounds right. Oh, and eventually we'll want per-tenant limits, not just per-key. Not in this branch though.

**Assistant:** Noted as later work.

**User:** OK I need to stop. Update the handoff.
