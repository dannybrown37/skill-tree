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

1. **Mechanical layer first**: run
   `uv run python "$SKILL_TREE_DIR/skills/audit-skills/scripts/check_skill_structure.py"`
   from the target repo's root (it discovers skills relative to cwd, checking both
   `.claude/skills/` and `skills/`). Frontmatter and bundled-script errors it reports are
   non-negotiable — fix those before doing any judgment-call analysis below.
2. **Inventory sync**: list the skills and references directories on disk (whichever
   layout this repo uses), compare against any "Skills"/"References" lists the repo's own
   CLAUDE.md maintains. Flag anything on disk but unlisted, or listed but missing.
3. **Skill vs. reference shape**: read each SKILL.md body. Playbook (imperative steps,
   "do X then Y") belongs as a skill. Background/theory/exhaustive listing belongs in a
   references location, with the skill (if any) shrunk to a thin trigger + pointer. Flag
   misclassified ones.
4. **Bundled-file anti-patterns**: for anything under a skill dir besides SKILL.md, check
   the two named anti-patterns (also enforced mechanically by step 1's script) — (a) a
   file a human would plausibly read/run directly outside the skill context (→ belongs in
   `scripts/` or a references location), (b) a synthetic template duplicating a real file
   (→ point at the real file instead).
5. **Staleness**: grep each skill/reference for file paths, function/flag names,
   dependency or framework names it references. Verify each skill matches current repo
   state. Flag anything renamed, removed, or never true.
6. **Report**: group findings by skill/reference, each tagged with one recommendation —
   keep / demote-to-reference / promote-to-skill / trim-fluff / fix-staleness /
   relocate-bundled-file. No fixes applied automatically.
