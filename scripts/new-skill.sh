#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${SKILL_TREE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
source "$SCRIPT_DIR/lib/open-in-editor.sh"
source "$SCRIPT_DIR/lib/scaffold.sh"

usage() {
    cat <<'USAGE'
Usage: new-skill.sh [<skill-name>]

Scaffold skills/<skill-name>/SKILL.md and open it. The name must be
kebab-case; with no argument and a terminal, you are prompted for one.

  --version   Print the version
  -h, --help  This screen
USAGE
}

case "${1:-}" in
--version | -V)
    echo "new-skill.sh $(plugin_version "$REPO_ROOT")"
    exit 0
    ;;
-h | --help)
    usage
    exit 0
    ;;
esac

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

scaffold_reject_name "skill" "$SKILL"

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
