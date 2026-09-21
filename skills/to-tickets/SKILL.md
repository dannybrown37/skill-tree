---
name: to-tickets
description: "Break a spec, plan, or conversation into tracer-bullet vertical-slice tickets with blocking edges — \"turn this into tickets\", \"break this down\", \"what's the work?\". Pairs with skill-tree:to-spec upstream and skill-tree:handoff downstream."
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write
---

# To Tickets

Break a plan, spec, or conversation into a set of tickets: tracer-bullet vertical slices, each
declaring the tickets that block it.

## Process

### 1. Gather context

Work from whatever is already in the conversation. If the user passes a reference (a spec path,
an issue number or URL), fetch it and read its full body and comments.

### 2. Explore the codebase

If you haven't already, explore the codebase to understand current state. Ticket titles and
descriptions should use the project's `CONTEXT.md` vocabulary and respect ADRs in the area
being touched.

Look for opportunities to prefactor — "make the change easy, then make the easy change."
Prefactoring is its own ticket, blocked by nothing, blocking the work that needs it.

### 3. Draft vertical slices

Each slice cuts a narrow but **complete** path through every layer (schema, API, UI, tests) —
vertical, not a horizontal slice of one layer.

- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Give each ticket its blocking edges: the other tickets that must complete before it can start

**Wide refactors** are the exception. A mechanical change whose blast radius fans across the
whole codebase (rename a column, retype a shared symbol) can't land as a vertical slice. Use
expand–contract:

1. **Expand**: add the new form beside the old (nothing breaks)
2. **Migrate**: move call sites over in batches sized by blast radius, each batch its own
   ticket, keeping CI green batch-to-batch because the old form still exists
3. **Contract**: delete the old form once no caller remains, blocked by every migrate batch

### 4. Quiz the user

Present the breakdown as a numbered list. For each ticket:

- **Title**: short descriptive name
- **Blocked by**: which other tickets must complete first (or "None")
- **What it delivers**: the end-to-end behaviour this ticket makes work

Ask:
- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct?
- Should any tickets be merged or split?

Iterate until the user approves.

### 5. Publish

Ask the user where tickets go. Two modes:

**Local files** — one file per ticket under `docs/tickets/<feature-slug>/`, numbered from `01`
in dependency order (blockers first). Use the template in
[references/ticket-template.md](references/ticket-template.md).

**Issue tracker** (GitHub, Linear, etc.) — publish in dependency order so blocking edges can
reference real identifiers. Use the platform's native blocking/sub-issue relationships where
available. Confirm with the user before posting — human-in-the-loop applies to anything visible
outside the local working tree.

Work the frontier: any ticket whose blockers are all done.

## What goes in a ticket

- **What to build**: end-to-end behaviour from the user's perspective, not layer-by-layer
  implementation steps
- **Acceptance criteria**: checkboxes, each verifiable
- **Blocked by**: references to blocking tickets, or "None (can start immediately)"

Avoid specific file paths or code snippets — they go stale. Exception: if a prototype produced
a snippet that encodes a decision more precisely than prose (state machine, schema, type shape),
inline the decision-rich parts and note it came from a prototype.

## Integration

- **[[to-spec]]** produces the spec this skill consumes
- **[[domain-modeling]]** provides the vocabulary tickets are written in
- **[[handoff]]** picks up where this leaves off — `handoff add` items from the approved
  ticket list to seed the backlog for a work session
