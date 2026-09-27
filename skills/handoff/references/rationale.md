# Why the handoff is shaped this way

Loaded on demand — `SKILL.md` has the rules; this has the reasons and the diagnostics.

## Why three files

One file is always either too long to load or too compressed to be useful, because it's
being asked to do jobs that pull in opposite directions:

| | Narrative | Re-entry prompt | Backlog |
| --- | --- | --- | --- |
| **Answers** | What was done and decided, and why | How to rebuild working context, right now | What to do after this |
| **Lifespan** | Accumulates with the project | Consumed by the next session | Drains as items are claimed |
| **Optimized for** | Completeness, an audit trail | Brevity — loaded before any work | Capture — writing an item must be cheap |

Whether the split is worth it scales with the work. A single session picking up tomorrow is
fine with the re-entry prompt alone. Multi-agent, multi-day, or anything where you'll later
need to know *which* agent worked from a summary rather than firsthand context: split it.

## Why write-back per task

A handoff written once and never updated is yesterday's snapshot presented as current state —
the most common way this pattern fails. Updating per task means the handoff is never more than
one task stale, so an abrupt end (compaction, crash, the user walking away) loses one task, not
the session. The session-end write becomes a review, not a reconstruction — which matters
because session end is when there's least context to reconstruct from.

Automating it (a `PreCompact` hook that writes, a `SessionStart` hook that reads) turns this
from discipline into mechanism — see `hooks.md`.

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
