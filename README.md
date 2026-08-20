# skill-tree

This is my LLM agent skill repo. There are many like it, but this one is mine.

Includes the actual implementation behind each skill,
not just its playbook. Skills here are meant to be portable:
usable on any repo, machine, or project.

Both hosts read the same `SKILL.md` spec, so portability is an install-and-hooks problem rather
than a content one. See [Installing](#installing).

## Layout

Each skill gets its own `skills/<name>/SKILL.md` (the playbook) plus whatever implementation
it needs under its own `scripts/` and `references/`, following the same three-layer model
(metadata / playbook / resources) any Claude Code skill uses, colocated with the skill itself,
not in a shared top-level directory.

<!-- skills:start -->
| Skill | What it does |
| --- | --- |
| `adversarial-review` | Manually-triggered red-team review of the current branch's diff against its remote tracking branch. Actively tries to break the change (construct a real failing input, race, or state) rather than checklist-verifying it — complements /code-review and /security-review, doesn't replace them. Never spawn this proactively/automatically; only when explicitly asked, since constructing real repros costs meaningful time and tokens. |
| `audit-skills` | Invoke when reviewing a repo's skills or references for structural drift — e.g. \"review my skills\", \"audit skills/references\", \"is this a skill or a reference\", \"are my skills bloated/stale\", or after adding/renaming a skill. Works against either the `.claude/skills/` (dotfiles-style) or top-level `skills/` (skill-tree-style) layout. |
| `bash-style` | Read before writing Bash or shell scripts. Covers shebang, quoting, error handling, sourced-script gotchas, and linting (shellcheck/shfmt). |
| `bro` | Restate the last message in a more grokable way |
| `cli-ergonomics` | Invoke when writing, reviewing, or extending any command-line entrypoint a human will run — a new CLI, a new subcommand, a script promoted out of one-off use. Covers the argument-handling ladder (help over error, TTY-guarded prompts, fzf selection, echoing the replayable command) and the hard `--version` requirement. Not for pure-library or single-purpose CI-only scripts. |
| `debug-ci` | Invoke when a GitHub Actions run has failed and you want it diagnosed and fixed locally — e.g. \"why did CI fail\", \"the build is red\", \"check the Actions run\", \"/debug-ci\". Fetches the failure logs via `gh`, diagnoses the root cause, and fixes it locally — never commits or pushes, the user reviews and pushes manually. |
| `dynamodb-cost-audit` | Invoke when a DynamoDB bill needs to come down or an existing table needs an efficiency review: \"our Dynamo costs are too high\", \"why is this table so expensive\", \"can we cut RCUs/WCUs\", \"should we be on-demand or provisioned\", \"do we still need this GSI\". Ordered audit from biggest lever to smallest, with the thresholds that decide each call. |
| `dynamodb-migrations` | Invoke when changing a DynamoDB table that is already live: \"add a GSI\", \"backfill this attribute\", \"change the projection on an index\", \"migrate to a new key design\", \"how do I do this without downtime\", \"do we need to backfill or can we let it drift\". Ordered playbooks per evolution type, plus stream and backfill hazards. |
| `dynamodb-modeling` | Invoke when designing a DynamoDB table or reviewing one before it ships: \"what should my partition key be\", \"do I need a GSI here\", \"is this single-table design right\", \"review my access patterns\", or any new table/entity in a Dynamo-backed service. Access-pattern-first modeling, key strategies, index choice, and the anti-patterns that show up in review. |
| `handoff` | Invoke when a session needs to end or continue elsewhere and the next session must pick the work up — \"write a handoff\", \"I'm running low on context\", \"we're about to compact\", \"let's switch to a new session\", \"continue where we left off\", \"resume the handoff\", handing work to another agent, model, or machine. Writes and resumes a handoff that survives compaction. |
| `node-style` | Read before writing Node, TypeScript, or JavaScript code. Covers type safety, ESLint, error handling, testing (Jest/Vitest), and package management. |
| `python-style` | Read before writing Python code. Covers type hints, naming, error handling, tooling (uv, pytest, ruff), and testing conventions. |
| `repo-audit` | Invoke to sanity-check a repo against the owner's quality preferences — pre-commit hooks, type checking, linting, test coverage, CLI ergonomics, secrets hygiene, dependency pinning, CLAUDE.md freshness. Reports what's missing or drifted, doesn't fix it. |
| `screenshot` | Invoke when the user refers to something on their screen — "look at the screenshot", "see the screenshot I just took", "check that error in the screenshot", "what does this dialog say", "look at my screen" — whether or not they attached an image. Resolves the newest screenshot's path, or captures the screen, so it can be read directly. |
| `site-launch` | Invoke before a website goes live, or when auditing one that already is — \"is this ready to ship\", \"why does my link look blank when I share it\", \"the site has no analytics\", \"add an RSS feed\". The checklist of things a site needs that aren't visible on the page itself. |
| `ui-designer` | Invoke when designing or restyling a web UI — landing pages, dashboards, docs sites, app chrome — or when the user asks why a site \"looks generic\", \"looks like a template\", or wants it to feel intentional. A running list of design lessons learned, applied as rules rather than suggestions. |
| `verify` | Invoke before answering whether something works, is gone, is used, or is correct — and whenever the user says \"can you confirm\", \"are you sure\", \"did that actually work\", or reports something is \"still\" broken. Produces the answer plus the evidence that would have falsified it. |
| `wait-what` | Stop. That last message did not land. Re-pitch it. |
<!-- skills:end -->

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

Skills that ship their own CLI are reachable by name, with arguments passed straight through:

```bash
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
which puts the `skill-tree` entry point on `PATH` (`~/.local/bin/`).

**Manual clone**, or to (re-)run setup yourself:

```bash
git clone <this repo> ~/projects/skill-tree
~/projects/skill-tree/scripts/install.sh
```

### GitHub Copilot CLI

Copilot reads the same `SKILL.md` spec, so the skills themselves need no translation — but it
has no plugin or marketplace concept, so symlinking the skills into place *is* the install.
One-liner for a machine that's never cloned this repo:

```bash
curl -fsSL https://raw.githubusercontent.com/dannybrown37/skill-tree/main/scripts/bootstrap.sh | bash -s -- --copilot
```

That clones (or pulls, if it already exists) `~/projects/skill-tree` and runs `install.sh
--copilot` for you. Equivalent manual steps:

```bash
git clone <this repo> ~/projects/skill-tree
~/projects/skill-tree/scripts/install.sh --copilot
```

That links **every** skill into `~/.copilot/skills/<name>`, generates
`~/.copilot/hooks/skill-tree.json`, symlinks `~/.copilot/copilot-instructions.md` to your
`~/.claude/CLAUDE.md` (so global instructions apply to both hosts from one file), and points
`~/.copilot/settings.json`'s `statusLine` at a Copilot-flavored version of the Claude status
line. Two differences from the Claude side worth knowing:

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

One skill, `audit-skills`, shells out to `uv run python` and needs `uv` on the machine. The
rest are pure playbook and work anywhere.

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
