---
name: queue
description: "Invoke when the user wants to pull work from the shared queue — list queued items, pick one, implement it, and mark it complete."
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
---

# Queue

`~/.claude/queue/queue` (or `$QUEUE_HOME` if set) holds work items the user has dropped in for
later. It's **shared across every repo**, not repo-local — dropped in from any project, synced
between machines via the password store (mechanism lives in `dotfiles`' `scripts/secrets.sh`,
not here). Format:

```markdown
# Queue

## [dotfiles] Item Title
Free-form description. Can be multi-line.

## Another Item
More details. No repo tag -- that's fine, it just shows up everywhere.
```

The leading `[repo]` is an optional tag naming which repo the item is for. Untagged items are
repo-agnostic and always visible; tagged items are filtered by default (see below).

`queue` (this skill's own `scripts/queue` -- an executable fzf wrapper, put on PATH by
`scripts/install.sh` -- backed by `scripts/queue_cli.py`) is the CLI:

- `queue list` — preview the next items (title + first line), scoped to items tagged for the
  **current repo** (by cwd) plus every untagged item. Prints a `(N hidden for other repos —
  \`queue list --all\`)` note if anything was filtered out. `--all` shows everything.
- `queue next` — show the full first visible item, same scoping as `list`.
- `queue titles` — bare titles, one per line (what the picker reads), same scoping; an
  in-progress item's title carries a literal `[in-progress]` suffix. `--all` shows everything.
- `queue claim [--item-title "..."]` — mark an item in-progress by appending `[in-progress]`
  to its `##` header, so a concurrent agent reading the file (or `queue titles`/`list`/`next`)
  can see it's taken. Errors (exit 1) if the item is already marked. **Lookup is never
  repo-filtered** — you can claim an item tagged for another repo if you know its title.
- `queue complete [--item-title "..."] [--end-time "<iso>"]` — move an item to the completed
  log, stamped with the time it was completed. If the item's body is over 50 lines (e.g. a
  pasted CI log), it's capped at 50 lines with a `_[Trimmed from N to 50 lines]_` note appended
  — the active queue itself is never modified, only what lands in the completed log.
- `queue tag [--item-title "..."] [--repo "<name>"]` — set, replace, or remove an item's
  `[repo]` tag. Pass `--repo ""` to remove a tag entirely. With no `--item-title`, fzf offers
  **every** item regardless of tag (retagging a mistagged item is the point). With no
  `--repo`, fzf offers git repos found under `$PROJECTS_DIR` (default `~/projects`), falling
  back to whatever was typed if it doesn't match one — for tagging an item to a repo only
  cloned on another machine.

With no `--item-title`, `queue claim`/`complete`/`tag` all open fzf over the current titles.
`--item-title` matches regardless of whether it includes the `[in-progress]` suffix or a
`[repo]` tag. `--end-time` defaults to now if omitted.

`queue` also needs a real terminal for its fzf pickers, and a tool call's `PATH` may not
include `~/.local/bin` anyway. Call the script directly instead of assuming `queue` is on `PATH`:

```bash
uv run python "${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/queue/scripts/queue_cli.py" <action> ...
```

Paths default to `~/.claude/queue/{queue,queue-complete}` (or `$QUEUE_HOME`) — no need to pass
`--queue-path`/`--complete-path` unless pointing at something else (e.g. a sandbox for testing).

## Manual invocation flow

1. Read the queue file directly (not just `queue list`) so you have the full text of every
   in-scope item, not just previews. **Scope to the current repo**: items tagged `[repo]` for
   a different repo than the one you're in are out of scope — don't discuss or claim them
   unless the user explicitly asks to look across repos (`queue list --all` first, to confirm
   what's out there). Skip any item whose header already carries `[in-progress]` — another
   agent has it — and surface that to the user rather than silently ignoring it.
2. If there's more than one eligible item, **ask which one to work on** — use `AskUserQuestion`
   listing the item titles. Don't assume the first item is wanted; the user has explicitly said
   they might not want to start with it.
3. Once picked, immediately claim it so other concurrently-running agents don't grab the same
   item during the discussion/implementation that follows:
   ```
   queue claim --item-title "<exact title>"
   ```
   If this errors because it's already in-progress, another agent beat you to it — stop and
   tell the user instead of proceeding.
4. Discuss the approach in chat before touching code — confirm scope, check for ambiguity,
   agree on a plan. This is the same human-in-the-loop discussion most repos' `CLAUDE.md`
   requires.
5. Implement per the repo's standing conventions (see that repo's own `CLAUDE.md`, if any):
   TDD, discrete reviewable steps, invoke the relevant language skill for the code being
   touched. Never `git add`/`commit`/`push` — that stays manual.
6. When the user confirms the item is done, run:
   ```
   queue complete --item-title "<exact title>"
   ```
   Pass it from a tool call: the fzf picker needs a terminal. The title matches the `##`
   header regardless of whether it still carries `[in-progress]`, and omitting it in a
   non-interactive context just prints the available titles and exits 1.
7. Confirm the item moved to the completed log. There's no tool that lets the assistant clear
   the session directly, so the assistant MUST end its own reply with a loud, unmissable
   reminder written in markdown (big heading, bold, emoji — vary the wording each time) telling
   the user to run `/clear`. Do this every single time, immediately after confirming
   completion — never silently move on. This only matters for this LLM-driven flow; `queue_cli.py`
   itself has no banner-printing code since raw terminal output doesn't render in the chat
   transcript anyway.

## Notes

- The queue and its completed log live in `~/.claude/queue/`, outside every repo, and sync
  between machines through `dotfiles`' password store. **Complete items, don't hand-delete
  them** — completions are the tombstones that stop an item resurrecting on the other machine.
- An untagged item you pick up on behalf of a specific repo doesn't get auto-tagged — if it
  turns out to belong to one, offer `queue tag` rather than leaving it ambiguous for next time.
- Autonomous/late-night processing (no discussion step, just pick the first item and run) is a
  separate future mode — don't skip the discussion/selection step unless the user has
  explicitly asked for autonomous execution.
- Nothing trims the active queue while an item is active, so step 1's full read can be large if
  someone pasted a big log in. That's expected.

- `references/queue-sync-model.md` (alongside this file) — how the password-store merge
  works: tombstones, merge ordering, stale `[in-progress]` markers, the 50-line completion
  trim. Read it when a sync looks wrong; it is not needed for a normal queue pull.
