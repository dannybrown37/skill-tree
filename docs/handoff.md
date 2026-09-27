# Handoffs and the backlog

`handoff` keeps three files per repo under `docs/handoffs/`: `CURRENT.md` (the re-entry
prompt — one next action, replaced each time), `NARRATIVE.md` (decisions, dead ends,
done-claims with evidence — accumulates), and `BACKLOG.md` (what isn't next yet).

`BACKLOG.md` has a CLI so an agent never reads the whole file to get one item:

```bash
handoff add --title "..." --body "..."   # capture for later; `next` puts it on top
handoff backlog                          # what's queued, in a pager
handoff pop                              # claim the top item into CURRENT.md
```

A `SessionStart` hook on both hosts prints `CURRENT.md` if there is one, else the top backlog
item's title, else nothing. It never pops — claiming work is the user's call.

Diagrams: [`skills/handoff/references/flow.md`](../skills/handoff/references/flow.md).

## `handoff status`

`handoff status` will print all of your repos' handoff info for quick reference of work TBD:

```console
$ handoff status
PROJECT                 HANDOFF  STATUS           BACKLOG
repo12                  no       none             0
project1                yes      in-progress      2
task9151                yes      awaiting-review  11
missioncritical         yes      unset            0
```
