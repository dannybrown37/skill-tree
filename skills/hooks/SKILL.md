---
name: hooks
description: "Invoke when the question is what hooks actually run in this session, from where, or whether one is even wired up — \"what hooks do I have\", \"is my hook actually firing\", \"why did that run twice\", \"what does this plugin install as a hook\", \"show me all my Claude/Copilot hooks\". Merges every hook source on disk (user/project/local settings, every installed plugin, every Copilot hooks/*.json) into one list."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
---

# Hooks

Read-only. Both Claude and Copilot merge hooks from several files at once, and neither host
shows you the merged result — only the effect of it, in a running session. This skill answers
"what hooks would fire right now, and from which file" without asking you to open five JSON
files and merge them by hand.

## Run the checker first

```bash
skill-tree hooks                # every hook, both hosts, grouped by event
skill-tree hooks --claude       # Claude only
skill-tree hooks --copilot      # Copilot only
skill-tree hooks --json         # machine-readable
skill-tree hooks <project-root> # project/local settings from a different repo (default: cwd)
```

Exit is always `0` — this reports what exists, it doesn't grade it. A `WARN:` line at the top
means a source file exists but failed to parse (bad JSON); everything else still gets read.

## Sources it reads

**Claude**, in the order Claude itself merges them:

1. `~/.claude/settings.json` — user settings
2. `<root>/.claude/settings.json` — project settings
3. `<root>/.claude/settings.local.json` — project-local, gitignored overrides
4. `/etc/claude-code/managed-settings.json` or the macOS equivalent, if present — org-managed
5. Every plugin in `~/.claude/plugins/installed_plugins.json` that ships a `hooks/hooks.json`,
   read from its recorded `installPath` — this is how a plugin's *own* hooks show up, not just
   the ones a user hand-wrote into settings.

**Copilot**: every `~/.copilot/hooks/*.json` file — Copilot has no merged settings file, one
file per plugin instead (`install.sh --copilot` writes `skill-tree.json`; another plugin writes
its own file alongside it).

Claude's schema nests hooks under a matcher (`{event: [{matcher, hooks: [{type, command}]}]}`);
Copilot's is flat (`{event: [{type, matcher?, bash, timeoutSec?}]}`). Both are parsed and
reported in one list rather than forcing a read of two different shapes.

## Reading the output

Entries are grouped by host, then by event. An event annotated `(N sources)` means N different
files register a hook for it — not necessarily a problem (e.g. this repo's own `SessionStart`
hooks and a user's `atuin`/dotfiles hooks coexist fine), but worth knowing before assuming only
one thing runs on that event. If a hook you expect isn't listed at all, it isn't wired up —
check the plugin's own `hooks/hooks.json` exists and is registered in `installed_plugins.json`
(Claude) or that `install.sh --copilot` has been run (Copilot).

This tool never executes a hook — probing whether one *works* means running it, which is a
human decision, not this skill's.
