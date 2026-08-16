---
name: bash-style
description: "Read before writing Bash or shell scripts. Covers shebang, quoting, error handling, sourced-script gotchas, and linting (shellcheck/shfmt)."
user-invocable: true
---

# Bash / Shell Scripts

Rules for Bash scripts start with _readable by humans_.

## Directory Layout

- `bin/` — **sourced** scripts (loaded into the current shell session, no shebang needed).
- `scripts/` — **non-sourced** scripts (executed as standalone commands).

## General Rules

- For scripts in `scripts/`, use `#!/usr/bin/env bash` shebang and `set -euo pipefail`.
- For scripts in `bin/`, omit the shebang — these are sourced, not executed.
- Quote all variable expansions: `"${var}"` not `$var`.
- Use `[[ ]]` over `[ ]` for conditionals.
- Use functions for any logic that repeats or exceeds ~10 lines.
- Use lowercase variable names for locals, UPPERCASE for exported/env vars.
- No commented-out code; git history exists.

## Style

- Indent with 4 spaces.
- Keep lines under 100 characters where reasonable.
- Use `readonly` for constants.
- Use `local` for function-scoped variables.

## Error Handling

- Use `trap` for cleanup on exit/error (e.g., `trap cleanup EXIT`).
- Check command success explicitly when `set -e` isn't sufficient — use `if ! command; then`.
- Validate required variables and arguments early with clear error messages to stderr.

## Linting

- All shell scripts must pass `shellcheck` and `shfmt` with no errors.

## Sourced Script Gotchas

- **Alias/function conflicts:** If a name was previously an alias, bash expands it before parsing `()`, causing `syntax error near unexpected token '('`. Add `unalias foo 2>/dev/null || true` at the top of any `bin/` file before defining functions that may shadow old aliases.
