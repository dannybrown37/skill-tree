---
name: site-launch
description: "Quality checks a website goes live, or for auditing one that already is — \"is this ready to ship\", \"why does my link look blank when I share it\", \"the site has no analytics\", \"add an RSS feed\". The checklist of things a site needs that aren't visible on the page itself."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
---

# Site Launch

Everything a site needs that you can't see by looking at it: what happens when someone shares
it, subscribes to it, or searches for it. `ui-designer` owns how it looks. None of these break
the build, so none get noticed until someone links the site somewhere.

Stack-agnostic: implement each item with whatever the project already uses before reaching for
a new dependency.

## Run the checker

```bash
skill-tree site-launch ./dist          # the built output, not src/; `check` is implied
skill-tree site-launch ./dist --json   # same verdicts, machine-readable
```

If `skill-tree` isn't on `PATH`:
`"${CLAUDE_PLUGIN_ROOT:-${SKILL_TREE_DIR:-$HOME/projects/skill-tree}}/skills/site-launch/scripts/site-launch"`.

**Claude:** delegate the run to the `checker-summarizer` subagent. **No subagents:** run it
yourself.

Exit `0` = nothing failed, `1` = a FAIL, `2` = nothing to check. Each item is `PASS`, `FAIL`,
`NA`, or `MANUAL` (5, 8, 9 need the deployed origin; it prints the command to run). Every FAIL
and MANUAL item carries a `fix:` block (`guidance` in JSON) — the requirement, the why, and how
to confirm it. That is the checklist; act on it.

The checker proves absence, not adequacy: it can say `og:image` is missing, not that the image
is any good. Every confirmation runs against the **deployed** origin — the dev server hides
broken absolute URLs, missing build-time assets, and redirect misconfiguration.

## The items

1. Absolute base URL · 2. Titles and descriptions · 3. Share card · 4. Feed · 5. Analytics ·
6. robots.txt and sitemap · 7. Favicon and 404 · 8. Security headers · 9. Works before
announcing

## Applying this to an existing site

Report what's missing before changing anything, in order — 1 and 2 are upstream of most of the
rest, and fixing 3 before 1 produces share cards pointing at relative paths. When an item is
already satisfied, say so and move on; don't swap a working implementation for one you'd
prefer.
