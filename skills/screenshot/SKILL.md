---
name: screenshot
description: Invoke when the user refers to something on their screen — "look at the screenshot", "see the screenshot I just took", "check that error in the screenshot", "what does this dialog say", "look at my screen" — whether or not they attached an image. Resolves the newest screenshot's path, or captures the screen, so it can be read directly.
---

# Screenshot

The user is talking about something on their screen that isn't in the conversation. Get an
image of it and read it. Browsing screenshots interactively is out of scope.

Two cases, and picking the wrong one wastes a round trip:

- **They took a screenshot** ("the screenshot I just took", "see that error I grabbed") —
  resolve the newest one.
- **They didn't** ("look at my screen", "what does this dialog say", or they described
  something visual and no image ever arrived) — take one yourself.

When it's genuinely ambiguous, taking one is the cheaper mistake: it costs a capture, whereas
resolving finds some unrelated shot from last Tuesday and confidently describes it.

## Taking one

```bash
"${SKILL_TREE_DIR:-$HOME/projects/skill-tree}/skills/screenshot/scripts/screenshot" take
```

Captures the whole desktop — every monitor, not just the primary — into the screenshots
directory and prints the new file's absolute path. `Read` that path.

Two things to know before reaching for it:

- **It captures whatever is there, right now.** No window picker, no region select. If the
  user has to bring something to the front first, say so and let them tell you when — don't
  capture blind and then describe the wrong window.
- **This one prompts for permission**, deliberately: the hook below pre-approves the read-only
  lookups, and photographing the screen isn't in that class. Reading the result is still free,
  so a capture costs one prompt, not two.

WSL only — it needs `powershell.exe`. Elsewhere it exits 1 saying so; ask the user to take
one and fall back to `latest`.

## Reading the screenshot the user means

Default to the **newest** one, with no confirmation step — when someone says "the screenshot I
just took", that's what they mean, and a round-trip to confirm is pure friction:

```bash
"${SKILL_TREE_DIR:-$HOME/projects/skill-tree}/skills/screenshot/scripts/screenshot" latest
```

That prints one absolute path. `Read` it — the Read tool renders images.

If the newest one clearly isn't what they meant, `screenshot list 10` prints the ten most
recent, newest first; pick from those or ask.

Neither step should prompt for permission: this skill ships a `PreToolUse` hook
(`scripts/screenshot_hook.py`, registered in the plugin's `hooks/hooks.json`) that
pre-approves the resolver's read-only commands and `Read` of an image inside the resolved
directory. If a prompt does appear, the hook isn't loaded — the plugin is installed from a
release that predates it, or `hooks/hooks.json` was edited. Don't work around it by asking the
user to approve twice every session; say which of those it is.

The grant is deliberately narrow, so don't expect it to cover more than the above: a chained
command (`screenshot latest && …`), `screenshot set`, `screenshot take`, a non-image, or a
path outside the screenshots directory all fall back to the normal prompt.

The printed path is unquoted, so a terminal will linkify it. Paths often contain spaces —
quote them when passing one to another command.

## When it can't find anything

Two different failures, with two different answers:

- **`no screenshots in <dir>`** — the directory is right but empty. Usually this means they
  thought they saved one and didn't: on Windows, Snipping Tool only writes a file when
  "Automatically save screenshots" is on, while Win+PrtScn always does. Offer `take` rather
  than sending them back to re-capture it, and mention the setting once.
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

- `screenshot take` — capture the desktop, print the new file's path. WSL only.
- `screenshot latest` — the newest screenshot's absolute path. **This is the one to use** when
  the user took the shot. Exits 1 if the directory is empty.
- `screenshot list [N]` — the N newest, newest first (default 10).
- `screenshot dir` — the resolved directory, for explaining where it's looking.
- `screenshot set <path>` — remember a directory. This is the user's escape hatch when
  detection is wrong; suggest it rather than working around a bad path every session.
- `screenshot --version` — the plugin version. Answers with no config and outside WSL.

Only image files are considered (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, any case),
so OneDrive's `desktop.ini` never comes back as "the latest screenshot".
