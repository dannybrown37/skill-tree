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
| `add` | Append an item — do this eventually |
| `next` | Insert at the top — do this next |
| `remove` | Delete an item |
| `edit` | Open `BACKLOG.md` in `$EDITOR` |
| `backlog` | Print `BACKLOG.md` — paged through `$PAGER` (else `less -R`) at a terminal, plain stdout otherwise. `--titles` prints bare titles, which is what the picker reads |
| `current` | Same for `CURRENT.md` |
| `narrative` | Same for `NARRATIVE.md` |
| `path` | Where the backlog is, creating an empty one if the repo has none |
| `--version` | Prints and exits 0, no config needed |

`add`/`next` take `--title` and `--body`; `remove` takes `--item-title`, matched
case- and whitespace-insensitively. Omit them at a terminal and the wrapper prompts —
title first (so the thought lands before an editor opens), `$EDITOR` for the body, fzf over
current titles for `--item-title`. Without a terminal, a missing argument is an error that
prints the available titles rather than a hang.

`backlog`/`current`/`narrative` take `--path` to print the file's path instead of its contents, and
exit 1 if the file doesn't exist.

## `handoff status`

Cross-project, unlike everything else here: it scans one level under `$PROJECTS_DIR`
(default `~/projects`) and reports, per git repo, whether `docs/handoffs/` exists, the
`**Status:**` keyword from its `CURRENT.md`, and how many backlog items it holds.

| Flag | Effect |
| --- | --- |
| `--root <dir>` | Scan this directory instead; repeatable |
| `--json` | Machine-readable array, one object per project |
| `--set <value>` | Don't scan — write the keyword into *this* repo's `CURRENT.md` |

Three values are written, by hand or by `--set`, and they differ in *who owes the next move*:
`in-progress` (a task is half-done), `awaiting-review` (done and green, the user's turn — no
agent should pick this up), and `between-tasks` (settled, next task free to start).

Two more are derived, never written: `unset` means `CURRENT.md` exists without the keyword,
and `none` means there's no `CURRENT.md` at all. `none` is ambiguous on its own — a repo that
never kept handoffs and one whose work finished look identical — so read it against
`has_handoff`: no handoff directory means never started, a handoff directory with a backlog
means queued work nobody wrote a re-entry prompt for.

`pop` sets `in-progress` as part of claiming, because an item that has been claimed is work
in flight. Nothing resets it automatically — that's write-back's job.

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
