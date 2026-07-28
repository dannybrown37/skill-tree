# Queue Sync Model

How `queue` and `queue-complete` (in `~/.claude/queue/`, or `$QUEUE_HOME`) move
between machines. Read this when a sync looks wrong — an item reappearing, a
completion not sticking, a stale `[in-progress]` marker. The day-to-day pull
flow in `SKILL.md` doesn't need any of it.

This file describes a mechanism this repo doesn't own: `queue_cli.py` here
only implements `merge-queue`/`merge-completed` as CLI subcommands. The thing
that actually *calls* them during a sync — `scripts/secrets.sh` and the
password-store — lives in `dotfiles`, resolving this repo's `queue_cli.py` via
`$SKILL_TREE_DIR` (default `~/projects/skill-tree`), the same way `dotfiles`'
`bin/queue.sh` does.

## Transport

Both files are gitignored where they'd otherwise land inside a repo — this is
a local working queue, not tracked history. They live outside every repo
(`~/.claude/queue/`) precisely so no one repo owns them, and sync through the
password store via `dotfiles`' `make secrets-save` / `secrets-load` and the
git hooks that call them.

The manifest entry for each is a `~/`-prefixed path (`~/.claude/queue/queue`,
`~/.claude/queue/queue-complete`) — `dotfiles`' `secrets.sh` resolves that
under `$HOME` regardless of which repo's hooks triggered the sync.

Pulling `~/.password-store` by hand does **not** update the queue; it only
moves the encrypted blob. The decrypted files are rewritten solely by
`secrets.sh load`, which runs from `dotfiles`' `post-merge` hook or
`make secrets-load` (and does its own `pass git pull` first).

## Merge, not overwrite

Both directions merge. `secrets.sh` routes these two paths through this
repo's `queue_cli.py merge-queue` / `merge-completed` instead of copying, so
items added on either machine survive a sync.

`queue` ends up as the union of both sides by title, minus every title
recorded in the merged `queue-complete`. **Completions are the tombstones** —
that's why an already-completed item doesn't resurrect.

`secrets.sh` reconciles `queue-complete` before `queue` (`MERGE_PATHS`),
independent of the order the store's manifest lists them in. The queue merge
needs the tombstones already merged.

## The `[repo]` tag is part of the title

The optional `[repo]` prefix is part of an item's title string, not separate
metadata — so it's part of the merge key and the tombstone key too. Retagging
an item with `queue tag` *after* it's already been completed elsewhere won't
match the old tombstone; the differently-tagged copy would resurrect. In
practice this only bites if a completion and a retag of the same item race
across two machines before a sync — rare, but if an item reappears after being
completed, check whether its tag changed.

## Consequence: complete items, don't hand-delete them

Deleting a `##` section from `queue` without running `queue complete` leaves
no tombstone, so the other machine's copy syncs it right back.

## Stale `[in-progress]` markers

The marker lives in `queue` itself, so it syncs through the same mechanism. A
stale snapshot can make an item look claimed when the claiming session already
finished (or vice versa). If `queue claim` errors as already-in-progress but no
other agent is actually running, ask before assuming the claim is real.

## Trimming

`trim_content` in `queue_cli.py` caps a completed item's body at 50 lines,
appending `_[Trimmed from N to 50 lines]_`. This only affects what lands in
`queue-complete`; `queue` is never modified by it.

Nothing trims `queue` while an item is still active, so reading the full file
can still be large if someone pasted a huge log in. That's expected.
