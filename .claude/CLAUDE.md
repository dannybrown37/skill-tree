# LLM Instructions

## What this repo is

A shared home for the *implementation* behind agent skills — the CLI, tests, and mechanism a
skill's `SKILL.md` playbook calls into. This repo is itself an installable Claude Code plugin
and marketplace (`.claude-plugin/`); each skill lives at `skills/<name>/`, with its own
`SKILL.md`, `scripts/`, and `references/` colocated rather than split into a shared top-level
directory. Consumers either install it via `/plugin marketplace add` or symlink `skills/<name>`
directly (e.g. `dotfiles`, historically) and invoke the CLI via an absolute path
(`$SKILL_TREE_DIR`-qualified), so nothing here should assume it's being run from inside another
repo, or that another repo is even cloned.

### Two hosts

Skills here target **Claude Code and GitHub Copilot CLI**. Both read the same `SKILL.md` spec
(`name` + `description` frontmatter required), so skill *content* is portable by default —
keep it that way. Concretely, when writing or editing a `SKILL.md`:

- Name a Claude-only tool (`AskUserQuestion`, `Task`) only alongside what to do where it
  doesn't exist. The playbook should still be followable without it.
- Prefer `$SKILL_TREE_DIR`-qualified absolute paths over `${CLAUDE_PLUGIN_ROOT}`; where
  `CLAUDE_PLUGIN_ROOT` is used, keep the `${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-...}}`
  fallback chain so the same line works under both.
- Slash commands (`/code-review`) and subagents are Claude-side; mention them as an option,
  not as a required step.

The two hosts diverge on install and hooks, not content, and `scripts/install.sh` owns both
sides — see the README's Installing section.

### Invocation aliases

**Claude:** every skill is always reachable as `skill-tree:<name>` once the plugin is
installed — that's the canonical, complete way to browse "what's in this repo." Don't
symlink `skills/<name>` into `~/.claude/skills/` just to make a skill exist; that's
redundant with the plugin install, and the harness collapses a same-named bare symlink into
just the unscoped alias, hiding that skill from `skill-tree:`-prefixed lookups entirely.

`skill-tree:<name>` is the *only* Claude invocation path. Do not add bare
`~/.claude/skills/<name>` symlinks as shortcuts — the shorter alias isn't worth a second,
version-pinned copy of the same skill and the ambiguity about which one is live.

**Copilot:** none of that applies. There's no namespace and no plugin install, so every skill
is symlinked bare into `~/.copilot/skills/<name>` and invoked by its plain name. The rule above
is about Claude's alias collapsing, not a general preference — don't carry it across.

## Repo-specific conventions

Global defaults (TDD, human-in-the-loop, no git writes, type hints, parametrize) apply; only
what's specific to this repo is here.

- Python: ruff (`.ruff.toml`), mypy (`mypy.ini`). mypy checks sources only — tests are
  excluded; run it bare (`uv run --with mypy mypy`), never with targets, so the hook and the
  terminal agree.
- Bash (any shell glue a skill ships): shellcheck + shfmt clean, `set -euo pipefail`, quote all
  expansions.
- A skill CLI that parses or writes user-pasteable file content deserves an adversarial review
  before shipping — suggest the user run one; never spawn it yourself (expensive).

## Documentation

- When a skill's implementation changes shape (new CLI surface, new file layout), update that
  skill's own `SKILL.md` in the same change — this repo has no separate "docs" pass.
