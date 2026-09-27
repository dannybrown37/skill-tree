# The `skill-tree` CLI

One entry point for everything in here, from an ordinary shell (no Claude session needed).
It exists for two reasons: the skills otherwise only document themselves *inside* Claude, and
the commands behind them are scattered across `scripts/` and `skills/*/scripts/`.

A bare `skill-tree` prints the whole surface — every command *and* every skill — because
keeping track of it all is the point:

```bash
skill-tree                    # commands + skills (the default; `help` does the same)
skill-tree list               # just the skills, one line each
skill-tree list --json        # the same, machine-readable
skill-tree show <skill-name>  # print a skill's full playbook (--raw keeps frontmatter)
skill-tree doctor             # this checkout, dev-link state, which CLIs are wired up
skill-tree install            # re-run scripts/install.sh
skill-tree dev --on           # dev mode (see below)
skill-tree check              # validate every skill's frontmatter and bundled scripts
skill-tree test               # the test suite
```

Skills that ship their own CLI are reachable by name, with arguments passed straight through:

```bash
skill-tree screenshot latest
skill-tree handoff backlog    # this repo's backlog; --pick to choose another repo
```

`handoff` also gets a bare name on `PATH` (`~/.local/bin/handoff`) -- capturing a backlog
item is a mid-thought action, and the longer form is enough friction to lose the thought.

Not every skill has one — `verify` and `ui-designer` are pure playbook. Those tell you so and
point at `skill-tree show <name>`.

It's a dispatcher, not a reimplementation — each sub-command delegates to the script that
already does the job, and propagates its exit code. `install.sh` puts it on `PATH` at
`~/.local/bin/skill-tree`.

Bash tab completion comes with it: `install.sh` links
`scripts/completions/skill-tree.bash` into
`~/.local/share/bash-completion/completions/skill-tree`, which bash-completion loads on its
own -- no shell rc is edited. It completes commands, skill CLIs, `show <skill>`, and each
sub-CLI's own sub-commands and flags -- those are scraped from that CLI's `--help` at
completion time, so they can't drift; where there's nothing to offer it falls back to
filename completion. The candidates come from `skill-tree __complete` rather than
a hard-coded list, so a new skill is completable the moment it exists. If your shell doesn't
pick it up, `source` that file from your `~/.bashrc`.
