---
name: screenshot
description: "Invoke when the user refers to something on their screen — \"look at the screenshot\", \"see the screenshot I just took\", \"what does this dialog say\", \"look at my screen\" — whether or not they attached an image."
user-invocable: true
disable-model-invocation: true
---

# Screenshot

Get an image of what the user is talking about and `Read` it.

## Which command

- **They already took one** → `screenshot latest`, then `Read` the printed path.
- **They didn't** ("look at my screen", no image arrived) → `screenshot take`, then `Read`.
- **Ambiguous** → prefer `take` — finding an unrelated old shot is worse than a fresh capture.

```bash
"${SKILL_TREE_DIR:-$HOME/projects/skill-tree}/skills/screenshot/scripts/screenshot" latest
"${SKILL_TREE_DIR:-$HOME/projects/skill-tree}/skills/screenshot/scripts/screenshot" take
```

`take` is WSL-only (needs `powershell.exe`) and prompts for permission deliberately. If the
user needs to bring a window to the front first, say so before capturing.

If `latest` is clearly wrong, `screenshot list 10` shows the ten most recent — pick or ask.

## Hooks

A `PreToolUse` hook pre-approves `latest`/`list`/`dir`/`help` and `Read` of images inside the
screenshots directory. Everything else (`take`, `set`, chained commands, non-images, paths
outside the directory) prompts normally. If read-only commands prompt unexpectedly, the hook
isn't loaded — say so rather than working around it.

## When it can't find anything

- **`no screenshots in <dir>`** — directory exists but is empty. On Windows, Snipping Tool
  only saves when "Automatically save screenshots" is on; offer `take` instead.
- **`no screenshots directory found`** — ask the user to run `screenshot set <path>`.

## CLI

Also reachable as `skill-tree screenshot <command>`:

| Command | What it does |
|---|---|
| `take` | Capture desktop, print path (WSL only) |
| `latest` | Newest screenshot's path (exit 1 if empty) |
| `list [N]` | N newest, newest first (default 10) |
| `dir` | Resolved screenshots directory |
| `set <path>` | Override auto-detection with a fixed directory |
| `--version` | Plugin version (no config needed) |

Paths often contain spaces — quote them when passing to another command.
