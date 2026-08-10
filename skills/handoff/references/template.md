# Handoff templates

Two files. The re-entry prompt is consumed and replaced each session; the narrative is
appended to and kept.

---

## `CURRENT.md` — the ephemeral re-entry prompt

Keep it short. This is loaded before any work happens.

```markdown
# Continue here: <short title>

You are continuing a session that ended with a handoff. Reconstruct context from the files
below, then do the next action.

**Written:** <YYYY-MM-DD HH:MM> · **Branch:** `<branch>` · **HEAD:** `<short-sha>` ·
**Tree:** clean | dirty · **Handoff:** #<n> of this thread

## Goal

<One or two sentences: what is being built, and why.>

## Read in this order

1. `docs/handoffs/NARRATIVE.md` — <which sections; grep for X rather than reading whole>
2. `<path>` — <why>
3. `<path>` — <why>

## In flight

- `<path>:<line>` — <what state it's in, what it still needs>

## Next action

<Exactly one concrete step, specific enough to begin without making a decision.>

## Acceptance check

```bash
<the command that says whether the next action worked>
```

## Open questions — blocked on the user

- [ ] <ask, don't guess>
```

---

## `NARRATIVE.md` — the persistent record

Append a section per handoff. Newest first, so the top of the file is the live state.

```markdown
# Project narrative

## <YYYY-MM-DD> — handoff #<n> — `<short-sha>`

### Tried and failed

<The section that cannot be recovered from the repo. Be specific.>

- <approach> → <what went wrong> → <why it was dropped>

### Decisions and constraints

- <decision> — <the reason it's locked>
- <user instruction or explicit rejection to honor>

### Done — with evidence

- <claim> — `<command>` → <result>, at `<sha>`

### Lessons and surprises

- <the non-obvious thing about this codebase or environment that cost real time>
```
