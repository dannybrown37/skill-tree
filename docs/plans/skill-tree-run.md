# Plan: `skill-tree run`

Drive a skill flow (idea → spec → tickets → …) headlessly, step by step, pausing at gates.
The runner is generic and lives here. Flows and work skills live elsewhere.

## Goals / non-goals

- Goal: run an ordered list of skills via `copilot -p`, passing artifacts between steps.
- Goal: flows are data files, layered (built-in < user < repo), patchable via `extends`.
- Goal: work flow (`to-sync-point`, company-context skills) written by hand on the work
  machine; zero work content in this repo, zero tokens needed to set it up.
- Goal: `--dry-run` validates a flow for free.
- Non-goal (v1): parallel steps, worktree swarm, auto-merge, git writes.
- Added after v1: `ClaudeHost` (`host = "claude"` / `--host claude`). See docs/run.md#hosts.

## Where things live

```
skill-tree (this repo, built + tested here)      work machine (hand-written)
───────────────────────────────────────────      ────────────────────────────────
scripts/flow_run.py      runner                  ~/.config/skill-tree/flows/work.toml
flows/default.toml                               ~/.copilot/skills/to-sync-point/
scripts/test_flow_run.py fake host + e2e fixtures ~/.copilot/skills/<context skills>/
docs/run.md              user docs               <repo>/.github/skills/…
                                                 <repo>/.skill-tree/flow.toml (optional)
```

## Program flow

```
skill-tree run [--flow NAME] [--dry-run] [--from STEP] [--resume RUN_ID] "idea text"
        │
        ▼
 load flow ── search: <repo>/.skill-tree/flow.toml
        │            ~/.config/skill-tree/flows/NAME.toml
        │            built-in flows/NAME.toml
        ▼
 apply extends + patches ──▶ resolved step list
        ▼
 resolve skills ── `copilot skill list --json` (run in repo cwd)
        │          missing skill → error listing where Copilot looked
        ▼
 --dry-run? ──yes──▶ print table (step, skill, source, gate, model) ; exit 0/1
        │no
        ▼
 for each step (from --from / resume point):
     build prompt  = context skills + step skill + input artifacts + output path
     run           = copilot -p PROMPT -s --model M [--allow-tool …]   (headless)
                     or copilot -i PROMPT                               (gate=interactive)
     check output artifact exists, non-empty
     save state.json
     gate=approve? ──▶ [a]pprove / [e]dit in $EDITOR / [r]erun / [q]uit
        ▼
 done: print artifact paths
```

## Flow file format (TOML: stdlib `tomllib`, no new dependency)

Built-in `default.toml`:

```toml
name = "default"
host = "copilot"

[[steps]]
id = "grill"
skill = "grill-for-planning"
gate = "interactive"
out = "decisions.md"

[[steps]]
id = "spec"
skill = "to-spec"
in = ["decisions.md"]
out = "spec.md"
gate = "approve"

[[steps]]
id = "tickets"
skill = "to-tickets"
in = ["spec.md"]
out = "tickets.md"
gate = "approve"
# … implement, two-axis-review
```

Work flow, written by hand at work:

```toml
extends = "default"
context = ["company-glossary", "team-conventions"]   # loaded into every step

[patch]
replace = { tickets = { skill = "to-sync-point", out = "sync-point.md" } }
remove = ["prototype"]

[[patch.insert_after.spec]]
id = "arch"
skill = "arch-review"
in = ["spec.md"]
gate = "approve"
```

Patches target steps by `id`, not by skill name, so swapping a step's skill keeps its
position stable. Patch ops: `replace`, `remove`, `insert_after`, `insert_before`, `append`.
Unknown keys cause an error, so typos fail loudly.

## Run state

```
<repo>/.skill-tree/runs/<UTC-timestamp>/
  state.json        flow snapshot, per-step status, Copilot session ids
  decisions.md      artifacts, one per step `out`
  spec.md
  logs/<step>.jsonl `--output-format json` capture
```

`--resume <id>` picks up the first step that isn't done. `--from <step>` re-runs from that step.
The runner adds `.skill-tree/runs/` to the repo's `.git/info/exclude` (local only, not a git write).

## Host adapter seam

```python
class Host(Protocol):
    def list_skills(self, cwd: Path) -> dict[str, SkillSource]: ...
    def run_headless(self, prompt: str, *, cwd: Path, model: str | None, log: Path) -> int: ...
    def run_interactive(self, prompt: str, *, cwd: Path) -> int: ...
```

v1 has only `CopilotHost`. Tests use `FakeHost`, so no model calls.

## Security / safety

- Headless runs get explicit `--allow-tool` lists from the step, plus `allow_all = true`
  as an opt-in per flow. The default is no `--allow-all-tools`.
- Prompt text is passed as one argv element, never through a shell.
- Flow files are validated (schema + unknown-key rejection) before any subprocess runs.
- Per-run turn/cost cap: `max_steps`, plus an optional per-step `timeout` (seconds).

## Slices (each one testable, HITL pause after each)

1. **Flow loading + patching** (pure logic, TDD)
   - parse TOML, layered search, `extends` chain (cycle detection), patch ops, validation.
   - tests (parametrized): each patch op, unknown key, missing target id, extends cycle,
     repo overrides user overrides built-in.
2. **Skill resolution + `--dry-run`**
   - `CopilotHost.list_skills` parses `copilot skill list --json` (recorded fixture JSON).
   - dry-run table; exit 1 on unresolved skill or context skill.
   - tests: fixture JSON with project/personal/plugin sources, a missing skill, name collision.
3. **Prompt builder**
   - context + skill + inputs + output contract. Snapshot-style tests.
4. **Runner loop + state + resume** with `FakeHost`
   - tests: happy path, missing artifact → step fails, resume skips done steps, `--from`.
5. **Gates** (TTY-guarded; non-TTY + approve gate → stop with a clear message)
   - tests: approve / rerun / quit via injected input; non-TTY behaviour.
6. **CopilotHost real calls + CLI wiring**
   - `skill-tree run` subcommand in `skill_tree_cli.py`, completions, `--help`, `--version`
     (inherited); apply `cli-ergonomics`.
   - opt-in e2e test (`pytest -m e2e`) against real `copilot -p` with fixture skills
     (written into a temp repo's `.github/skills`). Costs personal tokens only.
7. **Docs**: `docs/run.md` (flow format, work-machine setup recipe), README workflow
   section, `skill-tree help` map, CHANGELOG.

## Work-machine setup (end state, no tokens)

```
git pull / plugin update            # get the runner
$EDITOR ~/.config/skill-tree/flows/work.toml
skill-tree run --flow work --dry-run "x"    # validates skills resolve: free
skill-tree run --flow work "real idea"
```

## Risks / unknowns

- **`copilot skill list --json` shape:** check the real output in slice 2 and record it as a fixture.
  If it doesn't include source paths, fall back to scanning the documented dirs
  (`.github/skills`, `.agents/skills`, `.claude/skills`, `~/.copilot/skills`, `~/.agents/skills`).
- **Whether headless Copilot invokes a skill by name in the prompt:** prove it in the slice 6 e2e.
  Fallback: inline the SKILL.md body into the prompt.
- **Context-skill cost:** each one is loaded into every step. Flows should keep the
  `context` list short, and `--dry-run` shows its size.
- **Copilot CLI flag changes** (it's on 1.0.x): pin the flags the adapter uses in one place and
  check `copilot --version` in `doctor`.

## Alternatives considered

- YAML flows: nicer to hand-write, but adds a PyYAML dependency on the work machine. TOML wins.
- A markdown "orchestrator skill" (the agent runs the flow itself): editable, but
  nondeterministic, and gates leak. Rejected for the runner.
- Reimplementing skill discovery: duplicates Copilot's own rules. Delegate to `copilot skill list`.
