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
| `backlog` | A cross-repo work-item backlog (`~/.claude/backlog/`), with an optional `[repo]` tag and an fzf-driven claim/complete/tag CLI. |
| `debug-ci` | Diagnoses a failed GitHub Actions run from its real `gh` logs and fixes it locally. Never commits or pushes. |
| `verify` | Forces a falsifiable check (real command, real output) behind any "it works now" / "it's gone" claim, instead of an inference from the diff. |

`scripts/` at the repo root (outside any skill) is separate: repo-level dev tooling like
`check_skill_structure.py`, not part of any skill's own bundle.

## Installing

**From the marketplace (recommended):**

```
/plugin marketplace add dannybrown37/skill-tree
/plugin install skill-tree@skill-tree
```

This also registers a `SessionStart` hook that runs `scripts/install.sh` automatically the next
time a session starts, which symlinks every skill in this plugin into `~/.claude/skills/<name>`
(personal scope, so each is invoked bare — `/backlog`, `/debug-ci`, `/verify` — instead of
namespaced, e.g. `/skill-tree:backlog`) and puts the interactive `backlog` CLI on `PATH`
(`~/.local/bin/backlog`).

**Manual clone**, or to (re-)run setup yourself:

```bash
git clone <this repo> ~/projects/skill-tree
~/projects/skill-tree/scripts/install.sh
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
