#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib/open-in-editor.sh"

STYLES_DIR="$REPO_ROOT/output-styles"

prompt() {
    if ! [ -t 0 ]; then
        echo "Error: no TTY — pass the style name as an argument: $0 <style-name>" >&2
        exit 1
    fi
    read -rp "$1" "$2"
}

STYLE="${1:-}"

if [ -z "$STYLE" ]; then
    prompt "Style name (kebab-case): " STYLE
fi

if [ -z "$STYLE" ]; then
    echo "Error: style name required." >&2
    exit 1
fi

STYLE_FILE="$STYLES_DIR/$STYLE.md"

if [ -f "$STYLE_FILE" ]; then
    echo "Style already exists: $STYLE_FILE"
    open_in_editor "$STYLE_FILE"
    exit 0
fi

TITLE=$(echo "$STYLE" | sed 's/-/ /g' | sed 's/\b\(.\)/\u\1/g')

cat > "$STYLE_FILE" <<EOF
---
name: $TITLE
description: "TODO: Describe this output style."
keep-coding-instructions: true
---

TODO: Write the style instructions.
EOF

echo "Created output-styles/$STYLE.md"
echo "Run 'make install' to symlink into ~/.claude/output-styles/"
open_in_editor "$STYLE_FILE"
