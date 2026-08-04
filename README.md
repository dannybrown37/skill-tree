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
| `screenshot` | Resolves the newest screenshot's path, so one the user took but didn't attach can be read directly. Detects the standard location on WSL, macOS or Linux, with `screenshot set <path>` to override it. |
| `debug-ci` | Diagnoses a failed GitHub Actions run from its real `gh` logs and fixes it locally. Never commits or pushes. |
| `site-launch` | The pre-ship checklist for a website — canonical URL, per-page titles, share cards, feed, analytics, robots/sitemap, favicon and 404. Stack-agnostic; each item states the requirement and how to falsify it against the deployed origin. |
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

**From the marketplace (recommended):**

```
/plugin marketplace add dannybrown37/skill-tree
/plugin install skill-tree@skill-tree
```

This also registers a `SessionStart` hook that runs `scripts/install.sh` automatically the next
time a session starts, which symlinks every skill in this plugin into `~/.claude/skills/<name>`
(personal scope, so each is invoked bare — `/backlog`, `/debug-ci`, `/verify` — instead of
namespaced, e.g. `/skill-tree:backlog`) and puts the `skill-tree` entry point plus the
interactive `backlog` CLI on `PATH` (`~/.local/bin/`).

**Manual clone**, or to (re-)run setup yourself:

```bash
git clone <this repo> ~/projects/skill-tree
~/projects/skill-tree/scripts/install.sh
```

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
