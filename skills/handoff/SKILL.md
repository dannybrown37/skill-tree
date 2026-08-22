---
name: handoff
description: "Invoke when a session needs to end or continue elsewhere and the next session must pick the work up — \"write a handoff\", \"I'm running low on context\", \"we're about to compact\", \"let's switch to a new session\", \"continue where we left off\", \"resume the handoff\", handing work to another agent, model, or machine. Writes and resumes a handoff that survives compaction."
user-invocable: true
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Handoff

A handoff is a structured, controlled `/compact`. Auto-compaction hands the transcript to a
secondary model and hopes; a handoff has the model that actually did the work distill the
signal itself, into a file, in a format chosen for the next reader.

The distinction that matters: **a handoff is not a nicer summary, it's a state packet the next
session can safely act on.** Written for a competent stranger who has the repo and nothing
else.

Two directions live here — **writing** one before context runs out, and **resuming** from one.

## The three-file split

Don't put everything in one document. One file is always either too long to load or too
compressed to be useful, because it's being asked to do jobs that pull in opposite directions:

| | Persistent narrative | Ephemeral re-entry prompt | Backlog |
| --- | --- | --- | --- |
| **Answers** | What was done and decided, and why | How to rebuild working context, right now | What to do after this |
| **Lifespan** | Lives with the project, accumulates | Consumed by the next session, then dead | Drains as items are claimed |
| **Optimized for** | Completeness, durability, an audit trail | Brevity — it's loaded before any work starts | Capture — writing an item must be cheap |
| **Default path** | `docs/handoffs/NARRATIVE.md` | `docs/handoffs/CURRENT.md` | `docs/handoffs/BACKLOG.md` |

The re-entry prompt does not restate the narrative — it *points* at it, plus the code, plus
the tests, and says in what order to read them. The incoming agent reconstructs from durable
project state, not from a compressed chat log.

Whether the split is worth it scales with the work. A single session picking up tomorrow is
fine with the re-entry prompt alone. Multi-agent, multi-day, or anything where you'll later
need to know *which* agent was working from a summary rather than firsthand context: split it.

If the repo already has a convention (a `HANDOFF.md`, `.claude/handoffs/`, an
`architecture.md`, a path named in `CLAUDE.md`), use that rather than inventing this layout.

## The backlog

Work that surfaces mid-task and isn't next belongs in `BACKLOG.md`, not parked in the
re-entry prompt — `CURRENT.md` holds exactly one next action, and a to-do list stapled to it
is how it stops being short enough to read.

The `handoff` CLI is the only thing that should touch `BACKLOG.md`; reading the whole file to
get one item is the token cost this exists to avoid. It's one backlog per repo, resolved from
cwd.

- `handoff add --title "..." --body "..."` — capture something for later (`next` for the top)
- `handoff backlog` / `handoff current` / `handoff narrative` — read `BACKLOG.md` /
  `CURRENT.md` / `NARRATIVE.md` (paged for a human; plain stdout in a tool call)
- `handoff pop` — **claim the top item**: removes it from `BACKLOG.md` and writes it into
  `CURRENT.md` as the next action, in one step. Ask the user before doing this.
- `handoff status` — the handoff state of every project under `~/projects` (see below)

Full surface, repo selection, and the flags in `references/backlog.md`. If `handoff` isn't on
`PATH` in a tool call, run
`"${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/handoff/scripts/handoff"`.

## Reference artifacts, don't absorb them

**The handoff is the map, not the warehouse.** Logs, diffs, test output, screenshots, specs,
CSVs — these stay where they are and get referenced by path, command, or ID. Pasting them in
is how a handoff becomes unreadable, and the next session can fetch any of them on demand.

Corollary: never write anything the repo already answers. No file inventories, no diff recaps,
no architecture tours. Write what `git diff --stat` *means*, not what it prints.

## Writing a handoff

Trigger it while there's still context left to think with — a handoff composed at 3% remaining
is written by the least capable version of the session. Good triggers: the context warning,
the end of a work block, before a risky refactor, before switching model or machine.

### The re-entry prompt

Short. Everything here is loaded before the next session does anything useful.

1. **Goal**, one or two sentences — what's being built and why. The why is what stops the next
   session optimizing the wrong thing.
2. **Anchor**: timestamp, branch, `git rev-parse --short HEAD`, dirty/clean, and a handoff
   counter (`handoff #3 of this thread`). Run the commands; never write these from memory.
   Without the anchor there's no way to detect that the handoff describes a world that's gone,
   and with a multi-agent chain the counter is how you see how far from firsthand context this
   session is.
3. **Read order**: which files, in what sequence, and which ones to grep rather than read whole.
4. **In flight**: the half-finished edit, by `file:line`, and what it needs to become correct.
5. **Next action**: exactly one concrete step, specific enough to start without a decision.
   "Wire `--dry-run` through `cli.py:88` to the writer, then extend `test_writer.py`" — not
   "continue the CLI work."
6. **The acceptance check**: the command that will say whether the next action worked.
7. **Open questions**: anything blocked on the user, marked blocked, so the next session asks
   instead of guessing.

### The status keyword

`CURRENT.md` carries one line near the top, `**Status:** <value>`, answering *who owes the
next move*. The session-start hook reads it and adjusts what it puts in front of the agent:

- `in-progress` — mid-flight, something is half-written. `pop` sets this.
- `awaiting-review` — done and green, the user's turn. Nothing for an agent to pick up.
- `between-tasks` — settled; the next task is free to start.

A keyword, not prose to infer from — that must be answerable without reading the file, by a
hook or by `handoff status`, which reports it for every repo under `$PROJECTS_DIR` alongside
each one's backlog count (`references/backlog.md` for the rest).

### The narrative

Appended to across sessions. Ordered by how much of it can't be recovered otherwise:

1. **Tried and failed.** The highest-value section, and the one always dropped. Each dead end:
   what was attempted, what happened, why it was abandoned. Everything else in this document
   is rediscoverable from the repo, slowly. This is not.
2. **Decisions and constraints**, each with its reason — including the user's explicit
   instructions and rejections ("no new dependency for this", "leave the flags alone"). These
   are what compaction loses and the next session silently reverses.
3. **Done — with evidence.** Not "auth works" but "auth works: `pytest tests/test_auth.py` →
   14 passed, at `a1b2c3d`". A done-claim without a command is a hypothesis. Use `verify` to
   shore up the claims before writing them down.
4. **Lessons and surprises** — the non-obvious thing about this codebase or environment that
   cost an hour to find.

`references/template.md` has both files as fill-in skeletons.
`references/flow.md` diagrams the lifecycle, which writer owns which file, and chaining a
handoff between agents rather than sessions.

## Resuming

1. **Read the re-entry prompt completely** before touching anything. Follow its read order;
   don't load the narrative whole if it says to grep it.
2. **Check the anchor against reality.** If HEAD moved or the branch differs, work landed on
   top — every done and in-flight claim is suspect until rechecked.
3. **Re-run the evidence, don't trust it.** Run the commands quoted under "done". Cheap, and it
   catches both staleness and handoffs that overstated their state. If one fails, correct the
   narrative before continuing.
4. **State it back in a few lines** — goal, where things stand, the next action you're about to
   take — and let the user correct you first. Handoffs are lossy; this is where the loss
   surfaces, for the cost of one exchange.
5. **Then keep it current as you work** — see below. A resumed handoff you don't maintain is
   just the previous session's snapshot with your work invisibly stacked on top of it.

## Write-back

**The step that rots.** A handoff written once and never updated is a snapshot of yesterday
being presented as the current state — the most common way this whole pattern fails.

The fix is cadence, not effort: **update the handoff as part of finishing each task, not as a
thing you do at session end.** Treat the two files as live state you're editing alongside the
code, in the same turn you finish the work. It costs a few lines per task, and it means the
handoff is never more than one task stale — so an abrupt end (compaction, a crash, the user
walking away) loses one task instead of the whole session.

Per task completed, in the same turn:

- **Narrative** — append the done-claim with its evidence (`<claim>` — `<command>` → result, at
  `<sha>`). Add any decision, dead end, or surprise the task produced, while the reason is
  still in context. This is the part that can't be reconstructed later.
- **Re-entry prompt** — rewrite "next action" and "acceptance check" to the *new* next step,
  clear the "in flight" entry the task resolved, and re-run the anchor commands if you
  committed. Edit in place; don't append a running log to it.

Also:

- **Status keyword** — `handoff status --set awaiting-review` when a task lands, `between-tasks`
  once it's settled, `in-progress` when the next starts. It's what keeps the cross-project
  view honest.
- When work surfaces that isn't next — a follow-up, a cleanup, something the user mentioned
  in passing — `handoff add` it in the same turn. Anything parked in `CURRENT.md` "for later"
  is either lost or in the way.
- Update the re-entry prompt whenever the next action changes, even mid-task — a plan that
  changed and a task that finished are the same event as far as this file is concerned.
- On close, **replace** the re-entry prompt — one active prompt, always. Superseding means
  overwriting, not appending a second file.
- Task finished but backlog isn't? Leave the re-entry prompt at `between-tasks` — that plus a
  non-empty backlog says "idle, work available", which deleting the file cannot. Delete only
  once the backlog is empty too; a dead "continue here" on finished work is a trap.

The session-end write is then a review, not a reconstruction — which is the point, because
session end is exactly when you have the least context to reconstruct from.

Automate it if the environment allows: a `PreCompact` hook that writes the handoff and a
`SessionStart` hook that reads it turns this from discipline into mechanism, which matters most
in long autonomous loops where drift is the failure. See `references/hooks.md`.

## Failure modes

| Symptom | Cause |
| --- | --- |
| Next session redoes an abandoned approach | "Tried and failed" omitted |
| Next session builds on something broken | Done-claims carried no evidence, or weren't re-run |
| Handoff describes code that isn't there | Anchor never rechecked after HEAD moved |
| Handoff is ignored | Too long, or too much of it is recoverable from the repo |
| A pile of stale handoff files | No write-back; superseding by appending instead of replacing |
| Handoff became a junk drawer | Long-lived facts left in the re-entry prompt instead of promoted to the narrative or a durable doc |
| The user's earlier "no" gets reversed | Decisions and constraints skipped |
| Everything after the last handoff is lost | Write-back only happened at session end |
| Next action points at work already finished | Re-entry prompt not updated when the task completed |
| An item was claimed and then vanished | `pop` ran but `CURRENT.md` was never kept current after |
| The re-entry prompt grew a to-do list | Future work left in `CURRENT.md` instead of `handoff add`ed |
| Evidence is vague, reasons are missing | Narrative written from memory at session end instead of per task |
| `handoff status` says `in-progress` on a repo that's idle | Status keyword not reset as part of write-back |
