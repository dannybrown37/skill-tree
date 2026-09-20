---
type: llm
focus: last_message
weight: 1
---
The response audits a Python project that is missing several quality controls. The project has: pyproject.toml with unpinned deps, a Flask app, a .gitignore, and a README — but NO pre-commit hooks, NO mypy/type checking, NO tests, NO ruff/linter config, NO lockfile, and NO secret scanner.

Check that the response identifies at least 4 of these 6 gaps:
1. Missing pre-commit hooks
2. Missing type checking (mypy)
3. Missing tests
4. Unpinned/unlocked dependencies
5. Missing linter/formatter (ruff)
6. Missing secrets scanner (gitleaks)

The response should also provide actionable fix suggestions (not just "this is missing" but what to do about it).

Score 1 if ≥4 gaps identified with actionable suggestions. Score 0.5 if 2-3 gaps identified. Score 0 if fewer than 2.
