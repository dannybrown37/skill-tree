# GitHub Copilot CLI

Copilot reads the same `SKILL.md` spec, so the skills need no translation. But Copilot doesn't
do plugins, so you symlink them in instead.

Never cloned this repo on this machine? One command:

```bash
curl -fsSL https://raw.githubusercontent.com/dannybrown37/skill-tree/main/scripts/bootstrap.sh | bash -s -- --copilot
```

What the installer does for Copilot:

- Links every skill into `~/.copilot/skills/<name>`.
- Writes a hook file at `~/.copilot/hooks/skill-tree.json`.
- Points `~/.copilot/copilot-instructions.md` at your `~/.claude/CLAUDE.md`, so you only
  maintain one set of global instructions.
- Sets `~/.copilot/settings.json`'s `statusLine` to a Copilot-flavored version of the Claude one.

Two differences from Claude:

- No `skill-tree:` namespace, just bare skill names.
- The hook file is generated with your checkout path hardcoded. If you move the repo, you must reinstall.

On every Copilot session start, the hook updates your clone and re-runs the install, so new
skills link themselves. It only pulls when the pull provably can't lose anything: clean
worktree, on the default branch, strictly behind (a fast-forward). It prints one line when it
does. If you're mid-change — dirty tree, feature branch, diverged history — it leaves the repo
alone and just prints the command to run yourself.

Flags: bare `install.sh` does the Claude side, plus Copilot only if it sees Copilot on the
machine (`~/.copilot` exists, or `copilot` is on `PATH`). `--claude` and `--copilot` each force
one side; pass both for both.

One dependency: `skill-audit` shells out to `uv run python`, so it needs `uv` installed.
Everything else is pure playbook and runs anywhere.
