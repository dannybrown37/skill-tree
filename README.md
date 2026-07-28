# skill-tree

A shared home for reusable Claude Code skills — the actual implementation behind each skill,
not just its playbook. Skills here are meant to be genuinely portable: usable from any repo, on
any machine, independent of any one project's own conventions. A `SKILL.md` alone is a few
lines anyone can write; what makes a skill worth keeping around system-wide is the tooling
behind it, and that's what lives here.

## Layout

This repo is itself a single installable Claude Code plugin (`.claude-plugin/`), and also its
own marketplace, so it can be added directly via `/plugin marketplace add`. Each skill gets a
`skills/<name>/SKILL.md` (the playbook) plus whatever implementation it needs under its own
`scripts/` and `references/`, following the same three-layer model (metadata / playbook /
resources) any Claude Code skill uses — colocated with the skill itself, not in a shared
top-level directory.

| Skill | What it does |
| --- | --- |
| `queue` | A cross-repo work-item queue (`~/.claude/queue/`), with an optional `[repo]` tag and an fzf-driven claim/complete/tag CLI. |

`scripts/` at the repo root (outside any skill) is separate: repo-level dev tooling like
`check_skill_structure.py`, not part of any skill's own bundle.

## Installing

**From the marketplace (recommended):**

```
/plugin marketplace add dannybrown37/skill-tree
/plugin install skill-tree@skill-tree
```

This also registers a `SessionStart` hook that runs `skills/queue/scripts/install.sh`
automatically the next time a session starts, which symlinks the skill into
`~/.claude/skills/queue` (personal scope, so it's invoked as bare `/queue` — a
plugin-installed skill is otherwise always namespaced, e.g. `/skill-tree:queue`) and puts the
interactive `queue` CLI on `PATH` (`~/.local/bin/queue`).

**Manual clone**, or to (re-)run setup yourself:

```bash
git clone <this repo> ~/projects/skill-tree
~/projects/skill-tree/skills/queue/scripts/install.sh
```

`install.sh` is idempotent and safe to re-run — it never overwrites a file or symlink it
didn't create itself, and prints a note instead of silently editing your shell rc if
`~/.local/bin` isn't on `PATH` or the repo isn't at the default `~/projects/skill-tree`
location (set `$SKILL_TREE_DIR` in that case).

## Testing

```bash
uv run --with pytest pytest scripts/ skills/ -q
```

Pre-commit runs ruff (`.ruff.toml`) + the same test suite + `scripts/check_skill_structure.py`
(validates every skill's frontmatter and any bundled scripts).
