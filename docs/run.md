# `skill-tree run`: run a flow of skills

Drives a list of skills one step at a time through the Copilot or Claude Code CLI. Each step reads earlier
steps' output files and writes its own. Some steps pause for approval, and some run as
interactive sessions.

```
skill-tree run "add dark mode"
   │
   ├─ grill      interactive  copilot -i      → decisions.md
   ├─ spec       headless     copilot -p      → spec.md        ⏸ approve / edit / rerun / quit
   ├─ tickets    headless                     → tickets.md     ⏸
   ├─ implement  interactive                  → implementation.md
   └─ review     headless                     → review.md
```

```bash
skill-tree run "add dark mode"          # new run with the default flow
skill-tree run --flow work --dry-run    # resolve flow + skills, run nothing (free)
skill-tree run --host claude "idea"     # same flow, Claude Code instead of Copilot
skill-tree run --resume [RUN_ID]        # continue the latest (or a given) run
skill-tree run --from spec              # re-run spec and everything after it
skill-tree run --list                   # which flows exist and where
```

Exit codes: `0` done, `1` error or step failed, `2` usage, `3` paused (gate, no TTY,
`max_steps`).

## Where flows come from

The first match wins:

```
--flow NAME given                         no --flow
<repo>/.skill-tree/flows/NAME.toml        <repo>/.skill-tree/flow.toml
~/.config/skill-tree/flows/NAME.toml      else "default", searched like NAME
<skill-tree>/flows/NAME.toml (built-in)
```

`$XDG_CONFIG_HOME` replaces `~/.config` when set.

## Hosts

The host is set by the flow's `host` key (default `copilot`). `--host` overrides it, and the
choice is saved with the run, so `--resume` keeps using it.

| | Copilot | Claude Code |
| --- | --- | --- |
| Headless step | `copilot -p … --output-format json` | `claude -p --output-format stream-json --verbose -- …` |
| Interactive step | `copilot -i …` | `claude -- …` |
| `allow_tools` | `--allow-tool` each | `--allowedTools` (names mapped, below) |
| `allow_all` | `--allow-all-tools` | `--permission-mode bypassPermissions` |

Flows name tools the way Copilot does. For Claude, the runner maps `write` → `Write`,
`read` → `Read` and `shell(...)` → `Bash(...)`, and passes any other name through unchanged.

## Where skills come from

The prompt points at each skill's `SKILL.md` by absolute path, so the model reads exactly the
file the runner found.

**Copilot:** the runner asks Copilot (`copilot skill list --json`, run from the repo root), so
a skill resolves exactly as Copilot would resolve it: from the repo's `.github/skills/`,
`.agents/skills/` or `.claude/skills/`, then `~/.copilot/skills/`, plugins, and built-ins.

**Claude:** Claude has no `skill list` command, so the runner searches the same places Claude
does, closest first:

```
<repo>/.claude/skills/<name>
~/.claude/skills/<name>
<plugin>/skills/<name>     (from `claude plugin list --json`, enabled plugins only)
```

Plugin skills answer to both `<plugin>:<name>` and the plain `<name>`. That's why the default
flow's plain `to-spec` resolves to `skill-tree:to-spec` under Claude, and one flow file works
on both hosts.

## Flow file format

```toml
name = "default"            # optional; defaults to the file name
host = "copilot"            # copilot | claude
context = ["glossary"]      # skills loaded as background into every step
allow_tools = ["write"]     # passed as --allow-tool to every step
allow_all = false           # --allow-all-tools; opt-in only
model = "..."               # default --model for every step
max_steps = 20              # cap on step executions (incl. reruns) per invocation

[[steps]]
id = "spec"                 # unique; patches refer to steps by id
skill = "to-spec"
in = ["decisions.md"]       # files from earlier steps' `out`
out = "spec.md"             # must exist and be non-empty for the step to pass
gate = "approve"            # none | approve | interactive
model = "..."               # per-step override
allow_tools = ["shell(git:*)"]
allow_all = false
timeout = 600               # seconds; headless steps only
```

Gates:
- `none` runs headless and continues.
- `approve` runs headless, then asks you to approve, edit (`$EDITOR`), rerun or quit. With no
  TTY it pauses.
- `interactive` runs `copilot -i` so you drive the session. It needs a TTY.

## Extending a flow

```toml
# ~/.config/skill-tree/flows/work.toml
extends = "default"
context = ["company-glossary", "team-conventions"]

[patch.replace.tickets]           # merge fields into a step; position and id stay
skill = "to-sync-point"

[patch]
remove = ["review"]

[[patch.insert_after.spec]]       # also: insert_before, append
id = "arch"
skill = "arch-review"
in = ["spec.md"]
gate = "approve"
```

- Top-level keys in the child override the parent's. `name` is never inherited.
- A file can extend a flow with the same name. The search skips the file itself, so a user
  `default.toml` with `extends = "default"` patches the built-in one.
- A file can't have both `extends` and `steps`. Use `[patch]` instead.
- If you change a step's `out`, later steps whose `in` uses the old name break. `--dry-run`
  reports this.

## Run state

```
<repo>/.skill-tree/runs/<UTC timestamp>/
  state.json       idea, flow, per-step status
  spec.md …        one file per step `out`
  logs/<step>.jsonl  copilot --output-format json
```

The runner adds `.skill-tree/runs/` to `.git/info/exclude` (local only, nothing committed).
Resuming reloads the flow file, so you can edit a flow between steps.

## Work-machine setup (no tokens)

1. Update skill-tree (plugin update or `git pull`).
2. Write `~/.config/skill-tree/flows/work.toml` as above. Work skills stay in
   `~/.copilot/skills/` or in the work repo's `.github/skills/`, never in this repo.
3. `skill-tree run --flow work --dry-run`: every row should show a path, not `MISSING`.
4. Optionally check `.skill-tree/flow.toml` into a work repo so `skill-tree run` uses that flow
   there without `--flow`.

## Testing

```bash
just test   # unit tests, fake host, no model calls
just e2e    # real copilot and claude, two fixture skills each (spends tokens)
```
