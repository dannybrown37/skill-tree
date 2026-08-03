---
name: screenshot
description: Invoke when the user refers to a screenshot they took without attaching it — "look at the screenshot", "see the screenshot I just took", "check that error in the screenshot", "what does this screenshot say". Resolves the newest screenshot's path so it can be read directly.
---

# Screenshot

The user took a screenshot and is talking about it without attaching it. Find its path and
read it. Taking screenshots and browsing them interactively are out of scope — this resolves
paths, nothing else.

## Reading the screenshot the user means

Default to the **newest** one, with no confirmation step — when someone says "the screenshot I
just took", that's what they mean, and a round-trip to confirm is pure friction:

```bash
"${SKILL_TREE_DIR:-$HOME/projects/skill-tree}/skills/screenshot/scripts/screenshot" latest
```

That prints one absolute path. `Read` it — the Read tool renders images.

If the newest one clearly isn't what they meant, `screenshot list 10` prints the ten most
recent, newest first; pick from those or ask.

The printed path is unquoted, so a terminal will linkify it. Paths often contain spaces —
quote them when passing one to another command.

## When it can't find anything

Two different failures, with two different answers:

- **`no screenshots in <dir>`** — the directory is right but empty. On Windows, Snipping Tool
  only writes a file when "Automatically save screenshots" is on; Win+PrtScn always does. That
  setting is the first thing to check.
- **`no screenshots directory found`** — nothing standard exists on this machine. Ask the user
  where their screenshots go and have them run `screenshot set <path>` (see below). Don't guess
  at a path, and don't go hunting the filesystem for one.

## Where it looks

In order:

1. `$SCREENSHOT_DIR`, used verbatim. An error, not a fallback, if it isn't a directory —
   silently ignoring it would hide a typo.
2. `~/.config/skill-tree/screenshot-dir` (`$XDG_CONFIG_HOME` respected), written by
   `screenshot set <path>` and undone by deleting the file.
3. Otherwise the standard locations for whatever this machine is:
   - **WSL** — every Windows profile under `/mnt/c/Users` (`$WINDOWS_USERS_ROOT`), checking
     both `OneDrive/Pictures/Screenshots` and `Pictures/Screenshots`. Shared profiles
     (`Public`, `Default`, …) are skipped.
   - **macOS** — the `com.apple.screencapture location` default, then `~/Desktop`.
   - **Linux** — `~/Pictures/Screenshots`, then `~/Pictures`.

When several of those exist, the one holding the **most recent** image wins. OneDrive's "back
up my Pictures" setting silently redirects the folder and leaves the old one populated, so
"whichever exists" would pick wrong about half the time.

## CLI

`skills/screenshot/scripts/screenshot`, also reachable as `skill-tree screenshot <command>`:

- `screenshot latest` — the newest screenshot's absolute path. **This is the one to use.**
  Exits 1 if the directory is empty.
- `screenshot list [N]` — the N newest, newest first (default 10).
- `screenshot dir` — the resolved directory, for explaining where it's looking.
- `screenshot set <path>` — remember a directory. This is the user's escape hatch when
  detection is wrong; suggest it rather than working around a bad path every session.

Only image files are considered (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, any case),
so OneDrive's `desktop.ini` never comes back as "the latest screenshot".
