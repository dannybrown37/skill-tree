---
name: repo-audit
description: "Invoke to sanity-check a repo against the owner's quality preferences — pre-commit hooks, type checking, linting, test coverage, CLI ergonomics, secrets hygiene, dependency pinning, CLAUDE.md freshness. Reports what's missing or drifted, doesn't fix it."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
---

# Repo Audit

Read-only. Report findings, don't apply fixes — the user picks what to act on.

Run from the repo root. Every check either passes, fails, or is not applicable (the repo
doesn't use that thing). Report all three columns.

## Checks

Work them in order. Each section says what to look for and how to verify it.

### 1. Pre-commit hooks

The repo should have a `.pre-commit-config.yaml`. If it does:

- Run `pre-commit run --all-files` and report failures.
- Check that the hook list includes at minimum: a linter, a formatter, a secret scanner
  (gitleaks or equivalent), and end-of-file-fixer.
- If the repo has Python: ruff-check, ruff-format, mypy, and pytest hooks should be present.
- If the repo has shell scripts: shellcheck and shfmt hooks should be present.
- If the repo uses commitizen: both the early hook and the commit-msg hook should be present.

If no `.pre-commit-config.yaml` exists, flag it and skip to the next section.

### 2. Type checking

- **Python:** mypy config must exist (`mypy.ini`, `pyproject.toml [tool.mypy]`, or
  `setup.cfg`). Run `uv run --with mypy mypy` (bare, no targets) and report errors.
- **TypeScript:** `tsconfig.json` must exist with `strict: true`. Run `npx tsc --noEmit`.
- **Neither:** skip.

### 3. Linting and formatting

- **Python:** `.ruff.toml` or `[tool.ruff]` in `pyproject.toml`. Run
  `uv run --with ruff ruff check .` and `uv run --with ruff ruff format --check .`.
- **Node/TS:** eslint config must exist. Run `npx eslint .`.
- **Shell:** shellcheck and shfmt should be in pre-commit (checked above). Also spot-check:
  `find . -name '*.sh' -not -path './.git/*' | head -5 | xargs shellcheck` to confirm
  scripts pass standalone.

### 4. Tests exist and pass

- Identify the test runner (`pytest`, `jest`, `vitest`, `go test`, etc.).
- Run the suite. Report pass/fail count and coverage if a coverage config exists.
- Flag any source file with logic (not config, not `__init__.py`) that has zero corresponding
  test file.

### 5. CLI ergonomics

For every CLI entrypoint the repo exposes (check `pyproject.toml [project.scripts]`,
`package.json bin`, `Makefile` targets that look like commands, or `scripts/` executables):

- `--version` must exist, print a version, and exit 0 with no config/auth required.
- Running with no arguments must print help, not crash.
- If the CLI prompts interactively, confirm it fails cleanly when stdin is not a TTY
  (`< /dev/null`).

### 6. Secrets hygiene

- `.gitignore` must exclude `.env`, `*.pem`, `credentials*`, and common secret file patterns.
- `gitleaks` (or equivalent) must be in pre-commit hooks.
- Grep for hardcoded strings that look like secrets:
  `grep -rn --include='*.py' --include='*.ts' --include='*.js' --include='*.sh' -E '(password|secret|token|api_key)\s*=' . | grep -v test | grep -v __pycache__`
  and flag any that aren't reading from env vars or a secrets manager.

### 7. Dependency pinning

- **Python (uv/pip):** `uv.lock` or pinned versions in `pyproject.toml`. Unpinned `>=`
  without an upper bound is a flag.
- **Node:** `package-lock.json` or equivalent lockfile must exist and be committed.
- **Both:** check for dependencies added but not in the lockfile (lockfile drift).

### 8. CLAUDE.md / project config freshness

- If a `CLAUDE.md` or `.claude/CLAUDE.md` exists, grep it for file paths, function names,
  framework names, and dependency names. Verify each reference still exists in the repo.
- If the repo has a `SKILL.md` anywhere, run the same staleness check: paths and names it
  references must still exist.
- Flag any mention of a tool, framework, or file that's been removed or renamed.

### 9. README quality

The README is the front door. It must be written for humans — not frameworks, not LLMs, not
future-you-who-already-knows-everything.

- `README.md` must exist and not be a framework-generated placeholder (check for default
  strings like "Getting Started with Create React App" or "This project was bootstrapped").
- **Inverted pyramid:** the most important information comes first. The first paragraph
  should answer "what is this and why would I care" in 1–3 sentences. Install and usage
  come next. Architecture, contributing, and deep details come last. If a reader stops
  after the first screen, they should still know what the project does.
- **Tracks reality:** compare the README's feature claims, CLI examples, API surface, and
  install steps against what the repo actually exposes. Run every example command it shows
  and confirm it works. Flag anything the README promises that the code doesn't deliver,
  and anything the code delivers that the README doesn't mention.
- **Concise but thorough:** no walls of text, no five-paragraph essays explaining what a
  dependency is. Bullet points and short paragraphs. But don't skip things — every public
  entrypoint, every required env var, every non-obvious setup step should appear somewhere.
- If there's a `CHANGELOG.md`, its latest entry should reference the most recent tag
  (`git describe --tags --abbrev=0`).

### 10. Git hygiene

- No large binary files tracked (check `git ls-files` for common binary extensions:
  `.zip`, `.tar.gz`, `.jar`, `.exe`, `.dll`, `.so`, `.dylib`, images over 1MB).
- `.gitignore` exists and covers the stack's build artifacts (`__pycache__`, `node_modules`,
  `dist/`, `.next/`, `target/`, etc.).
- No merge conflict markers in tracked files:
  `grep -rn '<<<<<<< ' $(git ls-files) 2>/dev/null`.

## Report format

Group findings by section number. For each finding:

- **Status:** pass / fail / n/a
- **Detail:** what's wrong (one line)
- **Fix hint:** what to do about it (one line)

End with a summary line: X passed, Y failed, Z not applicable.
