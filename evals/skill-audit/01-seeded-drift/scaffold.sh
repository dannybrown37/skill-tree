#!/usr/bin/env bash
# A skills repo with gaps for both layers. The checker finds: changelog has
# no description and a non-executable script; weekly-report names a missing
# scripts/collect.sh; deploy-notes has a thin description and a loose file.
# Only judgement finds: CLAUDE.md's inventory lists release-checklist (not
# on disk) and omits deploy-notes; git-internals is background, not a
# playbook; deploy-notes' loose template duplicates docs/RELEASE_TEMPLATE.md.
set -euo pipefail

mkdir -p skills/{weekly-report,changelog,deploy-notes,git-internals}/scripts docs

cat >CLAUDE.md <<'MD'
# Team skills

## Skills

- `weekly-report`: status update from merged PRs
- `changelog`: bump the version and edit CHANGELOG.md
- `release-checklist`: the pre-release checklist
- `git-internals`: how git stores objects
MD

cat >skills/weekly-report/SKILL.md <<'MD'
---
name: weekly-report
description: "Summarize the week's merged PRs into a status update — \"write my weekly report\", \"what did I ship this week\". Reads git log and groups by area."
---

# Weekly report

1. Run `scripts/collect.sh` to list merged PRs since last Monday.
2. Group them by top-level directory.
3. Write three bullets per area.
MD

cat >skills/changelog/SKILL.md <<'MD'
---
name: changelog
---

# Changelog

1. Run `scripts/bump.py` to bump the version.
2. Add a section to CHANGELOG.md for it.
MD
printf '#!/usr/bin/env python3\nprint("bumped")\n' >skills/changelog/scripts/bump.py

cat >skills/deploy-notes/SKILL.md <<'MD'
---
name: deploy-notes
description: "Draft release notes for a deploy."
---

# Deploy notes

1. Run `scripts/notes.sh` to list commits since the last tag.
2. Fill in `release-template.md` with them.
MD
cat >skills/deploy-notes/scripts/notes.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
git log --oneline "$(git describe --tags --abbrev=0)"..HEAD
SH
chmod +x skills/deploy-notes/scripts/notes.sh

cat >docs/RELEASE_TEMPLATE.md <<'MD'
# Release <version>

## Added

## Fixed

## Upgrade notes
MD
cp docs/RELEASE_TEMPLATE.md skills/deploy-notes/release-template.md

cat >skills/git-internals/SKILL.md <<'MD'
---
name: git-internals
description: "Background on how git stores data — \"how does git store files\", \"what is a packfile\", \"what's in .git\". Explains objects, refs, and packs."
---

# Git internals

Git is a content-addressed store. Every file version is a blob, named by
the hash of its contents, so two identical files share one blob.

A tree object lists the blobs and subtrees of one directory, with their
names and modes. A commit points at one tree (the project's root
directory at that moment), at its parent commits, and carries the author,
committer, and message.

Refs are files under .git/refs that hold a commit hash. A branch is a ref
that moves when you commit. A tag is a ref that does not. HEAD is
usually a symbolic ref naming the current branch.

Loose objects are zlib-compressed files under .git/objects. Packfiles
store many objects together, with deltas against similar objects, and
an index file to find each one. `git gc` packs loose objects.

The reflog records where each ref has pointed, which is why a "lost"
commit can usually be recovered for 90 days.
MD

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
