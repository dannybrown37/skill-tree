# LLM Instructions

## What this repo is

A shared home for the *implementation* behind Claude Code skills — the CLI, tests, and
mechanism a skill's `SKILL.md` playbook calls into. This repo is itself an installable Claude
Code plugin and marketplace (`.claude-plugin/`); each skill lives at `skills/<name>/`, with its
own `SKILL.md`, `scripts/`, and `references/` colocated rather than split into a shared
top-level directory. Consumers either install it via `/plugin marketplace add` or symlink
`skills/<name>` directly (e.g. `dotfiles`, historically) and invoke the CLI via an absolute
path (`$SKILL_TREE_DIR`-qualified), so nothing here should assume it's being run from inside
another repo, or that another repo is even cloned.

## General Approach

- Prefer a TDD approach, with tests written before code.
- Human-in-the-loop: implement in discrete, testable steps and wait for feedback before
  continuing, unless asked to build end to end.
- Never `git add`/commit/push — the user does that manually.

## Code Style

- Python: type hints on all parameters/returns, `pytest.mark.parametrize` for DRY tests, ruff
  (`.ruff.toml`) for lint/format.
- Bash (any shell glue a skill ships): shellcheck + shfmt clean, `set -euo pipefail`, quote all
  expansions.

## Security

- `queue_cli.py` reads/writes a work-item file that can contain anything a user pastes in, and
  is synced by another repo's password-store mechanism — treat changes to it with the same
  care as auth/secrets code. For anything touching parsing, merging, or file writes, a red-team
  pass (construct a real failing case, not checklist review) is worth it before shipping —
  spawn an `adversarial-review`-style subagent if one is available in this environment.

## Documentation

- When a skill's implementation changes shape (new CLI surface, new file layout), update that
  skill's own `SKILL.md` in the same change — this repo has no separate "docs" pass.
