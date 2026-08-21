---
name: audit-skills
description: "Invoke when reviewing a repo's skills or references for structural drift — e.g. \"review my skills\", \"audit skills/references\", \"is this a skill or a reference\", \"are my skills bloated/stale\", or after adding/renaming a skill. Works against either the `.claude/skills/` (dotfiles-style) or top-level `skills/` (skill-tree-style) layout."
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
---

# Audit Skills

Read-only analysis. Report findings, don't apply fixes — the user picks what to act on
(same human-in-the-loop rule as `/code-review`).

If the target repo's own CLAUDE.md documents skill/reference classification rules (e.g. a
"Skill Structure" section), read those first and don't re-derive them here. Otherwise fall
back to the default heuristic in step 3 below.

## Steps

1. **Mechanical layer first**: run the checker over the target repo.

   ```bash
   "$SKILL_TREE_DIR/skills/audit-skills/scripts/audit-skills" .
   # or, with the plugin installed:
   skill-tree audit-skills .        # `check` is implied; a bare run checks cwd
   ```

   It discovers skills under both `.claude/skills/` and `skills/`, and splits what it
   finds in two:

   - **ERROR** — the frontmatter and bundled-script contract a host enforces on load
     (missing `name`/`description`, a name that doesn't match its directory, an
     over-long description, a script with no shebang or no executable bit). These are
     non-negotiable: fix them before any judgment-call analysis below.
   - **WARN** — drift, which is where steps 3–5 should look first: a SKILL.md over
     150 lines or a reference over 500 (background that wants extracting), a file
     sitting beside SKILL.md instead of in `scripts/`/`references/`, an unknown
     frontmatter field, a description too thin to route on, and any backticked path the
     SKILL.md names that no longer exists.

   Exit codes: 0 clean, 1 an error (or, with `--strict`, any warning), 2 no skills found.
   `--json` for machine-readable output. Warnings are a place to look, not a verdict —
   a 200-line SKILL.md that is genuinely all playbook is fine, and saying so is the
   judgement this skill exists for.
2. **Inventory sync**: list the skills and references directories on disk (whichever
   layout this repo uses), compare against any "Skills"/"References" lists the repo's own
   CLAUDE.md maintains. Flag anything on disk but unlisted, or listed but missing.
3. **Skill vs. reference shape**: read each SKILL.md body, starting with the ones step 1
   flagged for length. Playbook (imperative steps, "do X then Y") belongs as a skill.
   Background/theory/exhaustive listing belongs in a references location, with the skill
   (if any) shrunk to a thin trigger + pointer. Flag misclassified ones.
4. **Bundled-file anti-patterns**: for anything under a skill dir besides SKILL.md, check
   the two named anti-patterns — step 1 flags loose files mechanically, these are the
   judgement half — (a) a file a human would plausibly read/run directly outside the skill
   context (→ belongs in `scripts/` or a references location), (b) a synthetic template
   duplicating a real file (→ point at the real file instead).
5. **Staleness**: step 1 already checked the backticked paths in each SKILL.md; this is
   the rest of it. Grep each skill/reference for function/flag names, dependency or
   framework names it references. Verify each skill matches current repo state. Flag
   anything renamed, removed, or never true.
6. **Report**: group findings by skill/reference, each tagged with one recommendation —
   keep / demote-to-reference / promote-to-skill / trim-fluff / fix-staleness /
   relocate-bundled-file. No fixes applied automatically.
