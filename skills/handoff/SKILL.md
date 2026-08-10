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

## The two-file split

Don't put everything in one document. One file is always either too long to load or too
compressed to be useful, because it's being asked to do two jobs that pull in opposite
directions:

| | Persistent narrative | Ephemeral re-entry prompt |
| --- | --- | --- |
| **Answers** | What was done and decided, and why | How to rebuild working context, right now |
| **Lifespan** | Lives with the project, accumulates | Consumed by the next session, then dead |
| **Optimized for** | Completeness, durability, an audit trail | Brevity — it's loaded before any work starts |
| **Default path** | `docs/handoffs/NARRATIVE.md` | `docs/handoffs/CURRENT.md` |

The re-entry prompt does not restate the narrative — it *points* at it, plus the code, plus
the tests, and says in what order to read them. The incoming agent reconstructs from durable
project state, not from a compressed chat log.

Whether the split is worth it scales with the work. A single session picking up tomorrow is
fine with the re-entry prompt alone. Multi-agent, multi-day, or anything where you'll later
need to know *which* agent was working from a summary rather than firsthand context: split it.

If the repo already has a convention (a `HANDOFF.md`, `.claude/handoffs/`, an
`architecture.md`, a path named in `CLAUDE.md`), use that rather than inventing this layout.

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

## Write-back

**The step that rots.** A handoff written once and never updated is a snapshot of yesterday
being presented as the current state — the most common way this whole pattern fails.

- Update the re-entry prompt whenever the next action changes, not just at session end.
- Append to the narrative when something is decided, abandoned, or verified — at the moment,
  while the reason is still known.
- On close, **replace** the re-entry prompt. One active re-entry prompt, always. Superseding
  means overwriting, not appending a second file.
- When the work is finished, delete the re-entry prompt. The narrative stays; a dead "continue
  here" left in the repo is a trap.

Automate it if the environment allows: a `PreCompact` hook that writes the handoff and a
`SessionStart` hook that reads it turns this from discipline into mechanism, which matters most
in long autonomous loops where drift is the failure. See `references/hooks.md`.

## Chaining

A handoff is also the joint between skills and agents, not only between sessions: research →
handoff → prototype → handoff back. For a subagent, fold in what it can't cheaply ask for —
exact paths, commands verbatim, and the definition of done. Everything above still applies,
the failed attempts most of all.

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
