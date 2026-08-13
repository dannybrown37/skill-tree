# skill-tree

A shared home for reusable agent skills — the actual implementation behind each skill, not just
its playbook. Skills here are meant to be genuinely portable: usable from any repo, on any
machine, under either Claude Code or GitHub Copilot CLI, independent of any one project's own
conventions. A `SKILL.md` alone is a few lines anyone can write; what makes a skill worth
keeping around system-wide is the tooling behind it, and that's what lives here.

Both hosts read the same `SKILL.md` spec, so portability is an install-and-hooks problem rather
than a content one — see [Installing](#installing).

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
| `screenshot` | Resolves the newest screenshot's path, so one the user took but didn't attach can be read directly. Detects the standard location on WSL, macOS or Linux, with `screenshot set <path>` to override it. |
| `cli-ergonomics` | What a human-facing command-line entrypoint owes its user — a mandatory `--version`, plus the argument ladder from "print help, not an error" through TTY-guarded prompts, fzf selection, and echoing the replayable command. |
| `debug-ci` | Diagnoses a failed GitHub Actions run from its real `gh` logs and fixes it locally. Never commits or pushes. |
| `site-launch` | The pre-ship checklist for a website — canonical URL, per-page titles, share cards, feed, analytics, robots/sitemap, favicon and 404. Stack-agnostic; each item states the requirement and how to falsify it against the deployed origin. |
| `handoff` | Carries work across a compaction, a session boundary, or another agent. Splits it two ways — a persistent narrative (decisions, dead ends, verified state) and an ephemeral re-entry prompt — anchored to a SHA so staleness is detectable, with the write-back rule that keeps it from rotting. |
| `verify` | Forces a falsifiable check (real command, real output) behind any "it works now" / "it's gone" claim, instead of an inference from the diff. |

`scripts/` at the repo root (outside any skill) is separate: the `skill-tree` CLI plus
repo-level dev tooling like `check_skill_structure.py`, not part of any skill's own bundle.

## The `skill-tree` CLI

One entry point for everything in here, from an ordinary shell — no Claude session needed.
It exists for two reasons: the skills otherwise only document themselves *inside* Claude, and
the commands behind them are scattered across `scripts/` and `skills/*/scripts/`.

A bare `skill-tree` prints the whole surface — every command *and* every skill — because
keeping track of it all is the point:

```bash
skill-tree                 # commands + skills (the default; `help` does the same)
skill-tree list            # just the skills, one line each
skill-tree list --json     # the same, machine-readable
skill-tree show verify     # print a skill's full playbook (--raw keeps frontmatter)
skill-tree doctor          # this checkout, dev-link state, which CLIs are wired up
skill-tree install         # re-run scripts/install.sh
skill-tree dev --on        # dev mode (see below)
skill-tree check           # validate every skill's frontmatter and bundled scripts
skill-tree test            # the test suite
```

Skills that ship their own CLI are reachable by name, with arguments passed straight through
(`skill-tree backlog --help` is the backlog CLI's help, not the dispatcher's):

```bash
skill-tree backlog claim
skill-tree screenshot latest
```

Not every skill has one — `verify` and `ui-designer` are pure playbook. Those tell you so and
point at `skill-tree show <name>`.

It's a dispatcher, not a reimplementation — each sub-command delegates to the script that
already does the job, and propagates its exit code. `install.sh` puts it on `PATH` at
`~/.local/bin/skill-tree`.

## Installing

### Claude Code

**From the marketplace (recommended):**

```
/plugin marketplace add dannybrown37/skill-tree
/plugin install skill-tree@skill-tree
```

The plugin install is what makes every skill available, always as `skill-tree:<name>`. It also
registers a `SessionStart` hook that runs `scripts/install.sh` the next time a session starts,
which adds the shortcuts the namespace can't give you: `~/.claude/skills/backlog` (so it's
invoked bare, `/backlog`), and the `skill-tree` entry point plus the interactive `backlog`
CLI — under that name and the short `bl` — on `PATH` (`~/.local/bin/`).

**Manual clone**, or to (re-)run setup yourself:

```bash
git clone <this repo> ~/projects/skill-tree
~/projects/skill-tree/scripts/install.sh
```

### GitHub Copilot CLI

Copilot reads the same `SKILL.md` spec, so the skills themselves need no translation — but it
has no plugin or marketplace concept, so symlinking the skills into place *is* the install:

```bash
git clone <this repo> ~/projects/skill-tree
~/projects/skill-tree/scripts/install.sh --copilot
```

That links **every** skill into `~/.copilot/skills/<name>` and generates
`~/.copilot/hooks/skill-tree.json`. Two differences from the Claude side worth knowing:

- **Every skill lands bare.** Copilot has no `skill-tree:` namespace to keep the less-used ones
  behind, so there's no shortcut/namespace tradeoff to make — unlinked would just mean
  unreachable.
- **The hook config is generated, not symlinked.** Copilot's hook schema has no
  `${CLAUDE_PLUGIN_ROOT}` equivalent, so the checkout path is baked in at install time. Re-run
  `install.sh --copilot` after moving the checkout. The file is only ever overwritten while it
  still carries its `"_source": "skill-tree"` marker — delete that line to take ownership of it.

The generated `sessionStart` hook re-runs the install (so new skills link themselves) and checks
whether the checkout is behind its remote. Unlike the Claude side it **reports** rather than
pulls: this clone is one you might have uncommitted work in.

With no flags, `install.sh` runs the Claude side and adds the Copilot side only if Copilot is
present (`~/.copilot` exists, or `copilot` is on `PATH`). `--claude` and `--copilot` force one
side each; pass both for both.

Two skills shell out to `uv run python` (`backlog`, `audit-skills`) and need `uv` on the
machine. The other seven are pure playbook and work anywhere.

### What installing grants: your screenshots folder

Installing also registers a `PreToolUse` hook that auto-approves two things, so
`/screenshot` doesn't cost two permission prompts before it can do the one thing it's for:

- running `skills/screenshot/scripts/screenshot` in its read-only modes (`latest`, `list`,
  `dir`, `help`) — and only that script, alone on the line, with nothing chained onto it;
- `Read` of an **image file inside whichever directory `screenshot dir` resolves to**.

Be clear-eyed about the second one: that's standing permission to read *any* image in your
screenshots folder, in any session with this plugin enabled — not just the one you're talking
about, and not just when you invoked the skill. Screenshots are an unusually candid folder;
mine tends to accumulate whatever was on screen at the time.

If that's more than you want to hand over, either keep the folder tidy — clear it out so only
the shots relevant to what you're working on are sitting there — or point the skill at a
scratch directory you feed deliberately:

```bash
skill-tree screenshot set ~/screenshots-for-claude
```

To opt out entirely, remove the `PreToolUse` block from `hooks/hooks.json` (Claude) or the
`preToolUse` block from `~/.copilot/hooks/skill-tree.json` (Copilot — also delete that file's
`"_source"` line, or the next install will regenerate it). The skill still works either way, it
just asks first.

One thing to know if you use both: Copilot's `preToolUse` hooks are **fail-closed**, where
Claude's treat silence as "no opinion". So on Copilot the hook always returns an explicit
decision — `allow` for the two cases above, `ask` (the normal permission flow) for everything
else. It has no deny path on either host; it only ever widens.

`install.sh` is idempotent and safe to re-run — it never overwrites a file or symlink it
didn't create itself, and prints a note instead of silently editing your shell rc if
`~/.local/bin` isn't on `PATH` or the repo isn't at the default `~/projects/skill-tree`
location (set `$SKILL_TREE_DIR` in that case).

## Dev mode

The plugin manager installs a *tagged* release into a version-pinned directory under
`~/.claude/plugins/cache/`, so a commit that's on `main` but not tagged is invisible to
`/plugin marketplace update` — it correctly reports the installed version as the latest. That's
right for consumers and painful while authoring a skill. Dev mode points the installed plugin
at this checkout instead, so local edits are live with no bump/tag/push/update round trip:

```bash
skill-tree dev --on      # symlink the install path at this checkout
skill-tree dev           # --status, the default with no arguments
skill-tree dev --off     # restore the real install
```

Restart Claude after `--on` or `--off` for it to take effect. A bare `skill-tree` tags the
`dev` line with `[dev mode ON]`/`[dev mode OFF]`, so a forgotten link is visible without
asking; `skill-tree doctor` shows the full link target.

`--on` never deletes anything: the real install is moved aside to `<install-path>.real` and
restored by `--off`. If a `/plugin install` re-downloads the plugin while the link is in place,
a second `--on` discards the re-download and keeps the original backup. It refuses to touch a
symlink pointing at some other checkout. Both directions are idempotent.

Turn dev mode off before cutting a release — while it's on, the "installed" plugin is your
working tree, uncommitted changes and all.

## Testing

```bash
skill-tree test            # or, equivalently:
uv run --with pytest pytest scripts/ skills/ -q
```

Pre-commit runs ruff (`.ruff.toml`) + the same test suite + `scripts/check_skill_structure.py`
(validates every skill's frontmatter and any bundled scripts).

## License

MIT — see [LICENSE](LICENSE).
