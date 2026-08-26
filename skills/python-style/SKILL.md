---
name: python-style
description: "Read before writing Python code. Covers type hints, naming, error handling, tooling (uv, pytest, ruff), and testing conventions."
user-invocable: true
---

# Python

## Type Safety

- Always use type hints for all function parameters and return types.
- The more business-critical the function, the stricter the typing — use Pydantic models or typed stubs (e.g., `mypy_boto3_*`) over bare `dict`/`list`.
- Use `mypy` type checking, see the `git-a-grip` repo on this system or at https://github.com/dannybrown37/git-a-grip

## Naming

- Names should be clear and descriptive erring toward long, while also avoiding needlessly breaking lines.
- No leading underscore on top-level variables or functions unless you have a strong reason (this isn't a library for external consumers).
- Single-underscore prefix is for class-private members or throwaway assignments only.

## Error Handling

- Catch specific exceptions — never bare `except` or `except Exception`.
- Keep `try` bodies minimal — only wrap the line(s) that can actually raise.
- Use the most specific built-in or library exception available (e.g., `ValueError`, `KeyError`, `httpx.HTTPStatusError`). Custom exception classes are a last resort.
- Assign error messages to a variable first: `msg = "..."` then `raise ValueError(msg)`.

## Tooling

Use the Python packager [UV](https://docs.astral.sh/uv/) for dependency management and publishing.

Use at least Python 3.13 unless there is a good reason to use an older version. Don't use 3.14 yet, there are syntax changes I don't want to reckon with at this time.

## Testing

- Use [pytest](https://docs.pytest.org/) for testing.
- When fixing a bug, always add a regression test that fails before the fix and passes after. The test name should make the bug obvious (e.g., `test_get_stored_goal_names_excludes_weekly_habits_json`). No exceptions — if you can't reproduce it in a test, document why in a comment in the test file.
- Use `pytest-xdist` if tests can get ~2x+ speedup from it without loss of reliability.

## Linting

Use [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

**Code is not shippable until it passes all linting and formatting checks.**
