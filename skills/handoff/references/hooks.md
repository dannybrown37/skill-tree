# Automating the handoff with hooks

Discipline fails in long autonomous runs — that's exactly where drift bites. Hooks turn the
two halves of the loop into mechanism. The two halves are **not** equally automatable, so be
clear-eyed about which is which.

## Reading is fully automatable

`SessionStart` runs at the beginning of a session and **its stdout is added to the model's
context**. That makes the resume half free:

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
