# What installing grants: your screenshots folder

Installing also registers a `PreToolUse` hook that auto-approves two things, so
`/screenshot` doesn't cost two permission prompts before it can do the one thing it's for:

- running `skills/screenshot/scripts/screenshot` in its read-only modes (`latest`, `list`,
  `dir`, `help`) — and only that script, alone on the line, with nothing chained onto it;
- `Read` of an **image file inside whichever directory `screenshot dir` resolves to**.

Be clear-eyed about the second one: that's standing permission to read *any* image in your
screenshots folder, in any session with this plugin enabled — not just the one you're talking
about, and not just when you invoked the skill. Screenshots are an unusually candid folder;
mine tends to accumulate whatever was on screen at the time.

If that's more than you want to hand over, either keep the folder tidy — clear it out so only
the shots relevant to what you're working on are sitting there — or point the skill at a
scratch directory you feed deliberately:

```bash
skill-tree screenshot set ~/screenshots-for-claude
```

To opt out entirely, remove the `PreToolUse` block from `hooks/hooks.json` (Claude) or the
`preToolUse` block from `~/.copilot/hooks/skill-tree.json` (Copilot — also delete that file's
`"_source"` line, or the next install will regenerate it). The skill still works either way, it
just asks first.

One thing to know if you use both: Copilot's `preToolUse` hooks are **fail-closed**, where
Claude's treat silence as "no opinion". So on Copilot the hook always returns an explicit
decision — `allow` for the two cases above, `ask` (the normal permission flow) for everything
else. It has no deny path on either host; it only ever widens.

`install.sh` is idempotent and safe to re-run — it never overwrites a file or symlink it
didn't create itself, and prints a note instead of silently editing your shell rc if
`~/.local/bin` isn't on `PATH` or the repo isn't at the default `~/projects/skill-tree`
location (set `$SKILL_TREE_DIR` in that case).
