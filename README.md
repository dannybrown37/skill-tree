# skill-tree

A shared home for reusable Claude Code skills — the actual implementation behind each skill,
not just its playbook. Skills here are meant to be genuinely portable: usable from any repo, on
any machine, independent of any one project's own conventions. A `SKILL.md` alone is a few
lines anyone can write; what makes a skill worth keeping around system-wide is the tooling
behind it, and that's what lives here.

## Layout

Each skill gets a `.claude/skills/<name>/SKILL.md` (the playbook) plus whatever implementation
it needs under `scripts/`, following the same three-layer model (metadata / playbook /
resources) any Claude Code skill uses.

| Skill | What it does |
| --- | --- |
| `queue` | A cross-repo work-item queue (`~/.claude/queue/`), with an optional `[repo]` tag and an fzf-driven claim/complete/tag CLI. |

## Installing a skill

A consuming repo (or a bare machine) makes a skill available to Claude Code by symlinking it
into `~/.claude/skills/<name>`:

```bash
mkdir -p ~/.claude/skills
ln -s ~/projects/skill-tree/.claude/skills/queue ~/.claude/skills/queue
```

`dotfiles`' `install/bash.sh` does this automatically as part of `make bash`.

A skill's own shell/CLI plumbing lives wherever the consuming environment needs it — e.g.
`dotfiles`' `bin/queue.sh` provides the interactive `queue` shell function and fzf pickers, but
calls this repo's `scripts/queue_cli.py` via `$SKILL_TREE_DIR` (default `~/projects/skill-tree`)
rather than owning the logic itself.

## Testing

```bash
uv run --with pytest pytest scripts/ -q
```

Pre-commit runs ruff (`.ruff.toml`) + the same test suite + `scripts/check_skill_structure.py`
(validates every skill's frontmatter and any bundled scripts).
