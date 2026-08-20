# Automating the handoff with hooks

Discipline fails in long autonomous runs — that's exactly where drift bites. Hooks turn the
two halves of the loop into mechanism. The two halves are **not** equally automatable, so be
clear-eyed about which is which.

## This repo already ships it

`skills/handoff/scripts/handoff_session_start.sh` is wired as a `SessionStart` hook for both
hosts — Claude via `hooks/hooks.json`, Copilot via the config `scripts/install.sh` generates.
Nothing to configure; the rest of this file is why it does what it does, and what to do in a
repo that doesn't have skill-tree installed.

What it prints, in order:

1. `CURRENT.md`, if there is one, plus a single line reminding the session to keep it and
   `NARRATIVE.md` current as each task lands.
2. Otherwise the **title only** of the top `BACKLOG.md` item, plus "confirm with the user
   before starting it."
3. Otherwise nothing at all.

Two deliberate limits. It never injects the playbook itself — that's ~2k tokens on every
session for something the agent can invoke by name when it's actually writing a handoff. And
it never runs `handoff pop`: a hook claiming work nobody asked for is the human-in-the-loop
violation the skill spends a section warning about.

## Reading is fully automatable

`SessionStart` runs at the beginning of a session and **its stdout is added to the model's
context**. That's what makes the above possible; the hand-rolled minimum is:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "cat docs/handoffs/CURRENT.md 2>/dev/null"
          }
        ]
      }
    ]
  }
}
```

Matchers are `startup`, `resume`, `clear`, and `compact` — include `compact` so the re-entry
prompt is re-injected after an auto-compaction, which is the case this whole pattern exists
for. The `2>/dev/null` matters: no handoff should be silent, not an error on every session.

Check the current hook contract before wiring this up — field names and matcher values move.
The `update-config` skill owns edits to `settings.json`.

## Writing is not

A hook is a shell command, not a model turn. `PreCompact` fires before compaction, but it
cannot make the model write anything — so it cannot produce the handoff. What it *can* do is
preserve the raw material and make the gap loud:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "auto",
        "hooks": [
          {
            "type": "command",
            "command": "scripts/archive-transcript.sh"
          }
        ]
      }
    ]
  }
}
```

`PreCompact` receives JSON on stdin including `transcript_path` and `trigger` (`auto` or
`manual`), so a script can copy the transcript somewhere durable. That's an escape hatch, not
a handoff: a transcript is evidence, too noisy to be the handoff itself.

The reliable pattern is therefore:

- **Write deliberately**, at a trigger you control — the context warning, the end of a work
  block — by invoking this skill. Don't wait for auto-compaction; by then the session is
  already at its least capable.
- **Read automatically**, via `SessionStart`.

If a `Stop` hook is available in the environment, it can at least *check* — fail loudly when
`CURRENT.md` is older than the newest commit on the branch. That catches the write-back rot,
which is the dominant failure, even though it can't fix it.
