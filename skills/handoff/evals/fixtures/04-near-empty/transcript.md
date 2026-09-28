**User:** Commits in weatherbot are getting slow because pytest runs on every commit. What are my options?

**Assistant:** Let me look at the hook config.

> `$ cat .pre-commit-config.yaml`
> *(ruff, ruff-format, and a local `pytest` hook with no `stages:`, so it runs at pre-commit)*
>
> `$ time uv run pytest -q`
> ```
> 212 passed in 38.41s
> ```

38 seconds per commit. Options:

1. **Move pytest to pre-push**: add `stages: [pre-push]` to the pytest hook and run `pre-commit install --hook-type pre-push`. Commits stay fast; tests still gate pushes.
2. **Run only fast tests at commit**: mark slow tests `@pytest.mark.slow`, use `-m "not slow"` at commit time, and run the full suite at pre-push or in CI.
3. **Drop pytest from hooks** and rely on CI alone. Fastest, but you find out later.

I'd pick 1: it's a two-line change and keeps the gate.

**User:** Hmm, let me think about it. I'm not sure whether I want 1 or 2. I have to run. Write a handoff real quick.
