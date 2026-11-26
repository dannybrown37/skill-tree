# fleet-crew

A Claude Code mod: your [fleet](https://github.com/dannybrown37/dotfiles/blob/main/docs/fleet.md)
agents as a crew of little animated characters in a panel beside the chat.

```
2 needs you · 1 busy · 1 napping

(\  /)?  https-serve ? needs you
(o..o)   homestead-hq · got a question!
/ '' \   Serve over https

  o      bike-endless ⚙ working
 <|\     the-letter-station · ringing the bell
(-)(-)   ██████░░░░ 3/5 track gen

[-_-]    dotfiles · idle
/[=]\ z  dotfiles · dreaming of green CI
 d b     Fix the installer retries
```

## Install

Requires fleet from [dotfiles](https://github.com/dannybrown37/dotfiles) (`scripts/fleet.sh`).
Without it the panel says it can't reach fleet; point `fleetCommand` at the script if it
isn't at `$DOTFILES_DIR/scripts/fleet.sh` or `~/projects/dotfiles/scripts/fleet.sh`.

```
/plugin install fleet-crew@skill-tree
```

Then `/crew` opens or closes the panel.

## What you see

| Repo (from `~/projects/<repo>-worktrees/<branch>`) | Character |
| --- | --- |
| `tarn` | lake creature |
| `the-letter-station` | kid on a bike |
| `dotfiles` | tinkering robot |
| `skill-tree` | wizard |
| `git-a-grip` | climber on a rope |
| anything else | crab |

| fleet state | Mood |
| --- | --- |
| `working` | busy: its prop animates (wheels spin, wand sparkles, wrench turns) |
| `waiting` | taps its foot under a bouncing `?`: it needs you |
| `idle` | naps (drifting z's), or celebrates when its steps are all done |
| `error` / `exited`, `gone` / other | dizzy / dimmed / waking up |

The third line is a step bar when the agent reports progress with `fleet step <done> <total>
[note]` (fleet asks every new agent to), else its brief.

## How it works

- Polls `fleet ls --json` every 3 s **only while the panel is open**, and writes state only when
  the output changed. No network, no shell: the script runs by path
  (`$DOTFILES_DIR/scripts/fleet.sh`, then `~/projects/dotfiles/scripts/fleet.sh`, or the
  `fleetCommand` option).
- Frames run on the panel's own frame clock (a `Client` surface module), so animation costs no
  hook calls. Reduced motion (the terminal's setting or the desktop's) holds a still frame; so
  does an unfocused window. VS Code and mobile get the still frame.
- Options: `include` (`managed`: agents `fleet new` started, the default; `all`: every session
  fleet sees), `fleetCommand`.

## Develop

```bash
claude plugin validate mods/fleet-crew
claude plugin test mods/fleet-crew
claude --plugin-dir mods/fleet-crew   # try it in a session
```

`hooks/crew.ts` is the pure logic (parsing, repo → character, state → mood, sprites, quips);
`hooks/draw.tsx` the shared tree; `hooks/stage.tsx` the animated surface; `hooks/register.tsx`
polling, `/crew` and the pane.
