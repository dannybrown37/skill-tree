# Dev mode

The plugin manager installs a *tagged* release into a version-pinned directory under
`~/.claude/plugins/cache/`, so a commit that's on `main` but not tagged is invisible to
`/plugin marketplace update` — it correctly reports the installed version as the latest. That's
right for consumers and painful while authoring a skill. Dev mode points the installed plugin
at this checkout instead, so local edits are live with no bump/tag/push/update round trip:

```bash
skill-tree dev --on      # symlink the install path at this checkout
skill-tree dev           # --status, the default with no arguments
skill-tree dev --off     # restore the real install
```

Restart Claude after `--on` or `--off` for it to take effect. A bare `skill-tree` tags the
`dev` line with `[dev mode ON]`/`[dev mode OFF]`, so a forgotten link is visible without
asking; `skill-tree doctor` shows the full link target.

`--on` never deletes anything: the real install is moved aside to `<install-path>.real` and
restored by `--off`. If a `/plugin install` re-downloads the plugin while the link is in place,
a second `--on` discards the re-download and keeps the original backup. It refuses to touch a
symlink pointing at some other checkout. Both directions are idempotent.

Turn dev mode off before cutting a release — while it's on, the "installed" plugin is your
working tree, uncommitted changes and all.
