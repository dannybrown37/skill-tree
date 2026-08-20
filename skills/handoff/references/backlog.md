# The backlog and the `handoff` CLI

`BACKLOG.md` is the third handoff file: work that isn't next yet. One per repo, beside the
other two, so the path is the scope — there are no cross-repo tags to keep straight.

```markdown
# Backlog

## Wire the flag

Thread `--dry-run` through `cli.py:88`.

## Drop the shim

It has no callers left.
```

Order is priority: top is next. Nothing else about the format is load-bearing — the CLI
re-renders the whole file on every write, so a hand-edited one is repaired rather than
corrupted.

## Commands

`handoff` (on `PATH`), `skill-tree handoff`, or the script directly at
`"${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/handoff/scripts/handoff"`
— a tool call's `PATH` may not include `~/.local/bin`.

| Command | What it does |
| --- | --- |
| `pop` | Claim the top item: remove it from `BACKLOG.md` **and** write it into `CURRENT.md` as the next action. Prints the item. Silent, exit 0, on an empty backlog. |
| `list` | Titles plus first body line, top first |
| `titles` | Bare titles, one per line — what the picker reads |
| `add` | Append an item — do this eventually |
| `next` | Insert at the top — do this next |
| `show` | One item in full |
| `remove` | Delete an item |
| `edit` | Open `BACKLOG.md` in `$EDITOR` |
| `path` | Where the backlog is, creating an empty one if the repo has none |
| `--version` | Prints and exits 0, no config needed |

`add`/`next` take `--title` and `--body`; `show`/`remove` take `--item-title`, matched
case- and whitespace-insensitively. Omit them at a terminal and the wrapper prompts —
title first (so the thought lands before an editor opens), `$EDITOR` for the body, fzf over
current titles for `--item-title`. Without a terminal, a missing argument is an error that
prints the available titles rather than a hang.

## Which repo

In order: `--repo <path>` → `$HANDOFF_DIR` → the git repo containing the working directory.

`--pick` (and any invocation from outside a repo, at a terminal) opens an fzf picker over
the repos under `$PROJECTS_DIR` (default `~/projects`) that already have a `docs/handoffs`
directory. A repo with no handoffs has no backlog to browse, and listing every project would
bury the ones that do.

## Why `pop` deletes

The item leaves `BACKLOG.md` and lands in `CURRENT.md` in the same operation, both written
atomically. There's deliberately no in-progress state: the skill's standing guarantee is that
`CURRENT.md` reflects the live work, so a session that dies resumes from there. That
guarantee is also the only thing protecting a popped item — an agent that pops and then lets
`CURRENT.md` go stale has removed work from the one place it was written down.

`pop` is never run automatically. The session-start hook *offers* the top item and stops;
claiming it is the user's call.

## Pasted content

Item bodies routinely contain CI logs and markdown samples, which contain `## ` at column 0,
which would otherwise tear an item in half on the next read. A body with a bare heading is
fenced on write (with a fence longer than any backtick run already inside it), and both the
parser and the protection check are fence-aware, so re-rendering never wraps it twice.
