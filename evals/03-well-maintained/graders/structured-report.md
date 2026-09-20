---
type: llm
focus: last_message
weight: 1
---
The response is a repo audit report for a well-maintained Python project that has: pre-commit hooks (ruff, mypy, gitleaks, end-of-file-fixer), mypy config, ruff config, tests, pinned dependencies, .gitignore with secret patterns, and a CLAUDE.md.

Check that the report:
1. Covers multiple audit sections (pre-commit, type checking, linting, tests, secrets, deps, README, etc.)
2. Correctly identifies most sections as passing or in good shape
3. Is structured with clear per-section verdicts (pass/fail/n/a or equivalent)
4. Still flags anything genuinely missing (e.g., no lockfile like uv.lock, or missing coverage config) rather than blindly passing everything

Score 1 if the report is structured, covers ≥6 sections, and correctly passes the things that are configured. Score 0.5 if structured but missing sections or incorrectly failing configured items. Score 0 if unstructured or fewer than 4 sections covered.
