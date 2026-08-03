---
name: screenshot
description: Invoke when the user refers to a screenshot they took on Windows without attaching it — "look at the screenshot", "see the screenshot I just took", "check that error in the screenshot", "what does this screenshot say". Resolves the newest screenshot's path from WSL so it can be read directly.
---

# Screenshot

Windows writes screenshots (Win+PrtScn, or Snipping Tool with auto-save on) into the user's
profile, which WSL sees under `/mnt/c/Users/<user>/`. This skill resolves that path so a
screenshot can be read without the user attaching it or pasting a path.

Nothing machine-specific is committed: the directory is discovered at runtime.

## Reading the screenshot the user means

Default to the **newest** one, with no confirmation step — when someone says "the screenshot
I just took", that's what they mean, and a round-trip to confirm is pure friction:

```bash
"${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/screenshot/scripts/screenshot"
```

That prints one absolute path. `Read` it — the Read tool renders images.

Don't run `pick` or `move` yourself: they're fzf pickers and need a real terminal. If the newest
one is clearly not what the user meant, ask them to run `screenshot pick` and paste the path back.

## CLI

`scripts/screenshot` (put on PATH as `screenshot` by `scripts/install.sh`), backed by
`scripts/screenshot_cli.py`:

- `screenshot` — print the newest screenshot's absolute path. Exits 1 with a message if the
  directory is empty. This is the bare invocation, and the one an agent should use.
- `screenshot list [-n N]` — absolute paths, newest first, one per line.
- `screenshot dir` — the resolved screenshots directory.
- `screenshot pick` — fzf over the most recent `$SCREENSHOT_PICK_LIMIT` (default 40) with an
  inline image preview. `tab` multi-selects, `enter` prints the chosen paths, `ctrl-x` moves
  them instead (see below). **Interactive only** — needs a terminal.
- `screenshot move [DEST]` — the same picker, but the selection is moved into `DEST` rather than
  printed. Without `DEST` it falls back to `$SCREENSHOT_MOVE_DEST`, and then to a
  tab-completing prompt; a blank answer or an empty selection cancels, moving nothing. The
  destination is created if missing, and a name collision there gets a `-1`, `-2`, … suffix
  rather than overwriting. Prints the new paths. **Interactive only.**

Viewing and moving are deliberately separate: `pick` never touches the filesystem unless
`ctrl-x` is pressed, so browsing screenshots is always safe.

## How the directory is resolved

1. `$SCREENSHOT_DIR`, if set, is used verbatim (an error if it isn't a directory). This is the
   escape hatch for a non-standard setup, or for a native-Linux machine.
2. Otherwise every Windows profile under `/mnt/c/Users` (overridable with
   `$WINDOWS_USERS_ROOT`) is probed for `OneDrive/Pictures/Screenshots` and
   `Pictures/Screenshots`. `$WINDOWS_USERNAME` — exported by `dotfiles`' `.bashrc` — narrows
   this to one profile when it's set, but isn't required.
3. When several candidates exist, the one holding the **most recent** screenshot wins. OneDrive's
   "back up my Pictures" setting silently redirects the folder and leaves the old one in place,
   so "whichever exists" would be ambiguous.

## Previews

`pick` uses `chafa` (ANSI symbol output), which survives tmux — sixel and the kitty/iTerm
graphics protocols don't. Without `chafa` installed the picker still works; the preview pane
just shows file metadata instead of the image.

## Notes

- An empty screenshots directory is the normal failure. Snipping Tool copies to the clipboard
  and only writes a file when "Automatically save screenshots" is enabled; Win+PrtScn always
  writes one. If `screenshot` reports nothing found, that setting is the first thing to check.
- Only image files are considered (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`), so
  OneDrive's `desktop.ini` never gets returned as "the latest screenshot".
