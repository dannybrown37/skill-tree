#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/open-in-editor.sh"

prompt() {
    if ! [ -t 0 ]; then
        echo "Error: no TTY — pass the skill name as an argument: $0 <skill-name>" >&2
        exit 1
    fi
    read -rp "$1" "$2"
}

SKILL="${1:-}"

if [ -z "$SKILL" ]; then
    prompt "Skill name (kebab-case): " SKILL
fi

if [ -z "$SKILL" ]; then
    echo "Error: skill name required." >&2
    exit 1
fi

SKILL_DIR="$REPO_ROOT/skills/$SKILL"

if [ -d "$SKILL_DIR" ]; then
    echo "Error: skills/$SKILL already exists." >&2
    exit 1
fi

TITLE=$(echo "$SKILL" | sed 's/-/ /g' | sed 's/\b\(.\)/\u\1/g')

mkdir -p "$SKILL_DIR"
cat > "$SKILL_DIR/SKILL.md" <<EOF
---
name: $SKILL
description: "TODO: Add a one-line description of when to invoke this skill."
user-invocable: true
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, AskUserQuestion, WebFetch, WebSearch
---

# $TITLE

TODO: Write the skill content.
EOF

echo "Created skills/$SKILL/SKILL.md"
open_in_editor "$SKILL_DIR/SKILL.md"
