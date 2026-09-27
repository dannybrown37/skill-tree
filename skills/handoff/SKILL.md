---
name: handoff
description: "A session needs to end or continue elsewhere — \"write a handoff\", \"I'm running low on context\", \"continue where we left off\". Writes and resumes a handoff that survives compaction."
user-invocable: true
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Handoff

A handoff is a controlled `/compact`: the model that did the work distills a **state packet
the next session can safely act on**, written for a competent stranger who has the repo and
nothing else. Write it while there's context left to think with, not at 3%.

## Files

Scoped per git branch at `docs/handoffs/<branch>/` (`/` → `-`; nothing on detached HEAD).
If the repo already has a convention (a `HANDOFF.md`, a path named in `CLAUDE.md`), use it.

- `CURRENT.md` — re-entry prompt. Short; exactly one next action. Consumed, then replaced.
- `NARRATIVE.md` — what was done and decided, and why. Appended across sessions.
- `BACKLOG.md` — work that isn't next. **Only touch via the CLI.**

Small single-session work can skip the narrative. Why the split:
`references/rationale.md`. Skeletons: `references/template.md`.

## CLI

If `handoff` isn't on `PATH`, use
`"${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/handoff/scripts/handoff"`.

- `handoff add --title "..." --body "..."` — capture for later (`next` for the top)
- `handoff backlog` / `current` / `narrative` — read a file
- `handoff pop` — move the top backlog item into `CURRENT.md`. **Ask the user first.**
- `handoff status [--set <keyword>]` — status of every project, or set this one's
- `handoff close` — delete this branch's handoff dir; distill keepers to `CLAUDE.md`/memory first

Flags and repo selection: `references/backlog.md`.

## Reference, don't absorb

Logs, diffs, test output, specs stay where they are — reference by path, command, or ID. Never
write what the repo already answers (file inventories, diff recaps). No `PLAN.md`: decisions go
in the narrative, the next step in `CURRENT.md`.

## CURRENT.md

1. **Goal** — one or two sentences, including why.
2. **Anchor** — timestamp, branch, `git rev-parse --short HEAD`, dirty/clean, handoff counter
   (`#3 of this thread`). Run the commands; never from memory.
3. **Read order** — which files, in what sequence, which to grep rather than read.
4. **In flight** — the half-finished edit by `file:line`, and what it needs.
5. **Next action** — one concrete step startable without a decision.
6. **Acceptance check** — the command that proves it worked.
7. **Open questions** — marked blocked, so the next session asks.

Near the top: `**Status:** <keyword>`, read by the session-start hook and `handoff status`:

- `in-progress` — mid-flight (`pop` sets this)
- `awaiting-review` — done and green, user's turn. Committing past the anchor auto-promotes it
  to between-tasks.
- `between-tasks` — settled. With an empty backlog, suggest `handoff close`.

## NARRATIVE.md

Ordered by how unrecoverable it is otherwise:

1. **Tried and failed** — what, what happened, why abandoned. The most valuable, most dropped.
2. **Decisions and constraints** with reasons, incl. the user's rejections ("no new dep").
3. **Done, with evidence** — `<claim>` — `<command>` → result, at `<sha>`. Use `verify`.
4. **Lessons and surprises.**

## Resuming

1. Read `CURRENT.md` completely; follow its read order.
2. Check the anchor against reality. HEAD moved → every claim is suspect.
3. Re-run the done-evidence. If one fails, correct the narrative first.
4. State back goal, state, and next action in a few lines; let the user correct you.

## Write-back — per task, same turn, not at session end

- Narrative: append done-claim + evidence, plus any decision, dead end, or surprise.
- `CURRENT.md`: rewrite next action + acceptance check, clear resolved in-flight, re-anchor if
  committed. Edit in place — replace, never append a second prompt.
- `handoff status --set` as state changes.
- Anything surfaced that isn't next → `handoff add`, never parked in `CURRENT.md`.

Hook automation: `references/hooks.md`. Lifecycle diagrams: `references/flow.md`. Failure
modes: `references/rationale.md`.
