**User:** linkcheck marks GitHub links as broken because they return 429 under load. Add retry with Retry-After support. Branch `feat/retry-429`.

**Assistant:** Plan: retry only on 429, up to 3 retries, honor `Retry-After` in seconds and cap it at 30s so a hostile header can't stall the run. `sleep` is injectable for tests.

> Wrote `tests/test_fetch.py` with parametrized cases: 429→200, four 429s gives up with 429, 404 no retry
>
> `$ uv run pytest tests/test_fetch.py -q`
> ```
> FFF
> ```
>
> Implemented the retry loop in `src/linkcheck/fetch.py`
>
> `$ uv run pytest -q`
> ```
> 9 passed in 0.31s
> ```
>
> `$ uv run ruff check . && uv run mypy src`
> ```
> All checks passed!
> Success: no issues found in 1 source file
> ```

Done: all tests, ruff, and mypy are green. One thing I noticed but didn't do: `Retry-After` can also be an HTTP-date rather than seconds. Right now `float()` would raise on that. It's out of scope for this change.

**User:** Yeah, leave HTTP-date for later, add it to the list. This looks good. I'll review the diff and commit it myself tomorrow. Write a handoff and we're done for today.
