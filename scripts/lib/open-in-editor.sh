#!/usr/bin/env bash
# Opens a file in the current VS Code session, falling back to $EDITOR.
# Usage: source this file, then call open_in_editor <path>

open_in_editor() {
    local file="$1"
    if command -v code >/dev/null 2>&1 && [ -n "${TERM_PROGRAM:-}" ] && [ "$TERM_PROGRAM" = "vscode" ]; then
        code "$file"
    elif [ -n "${EDITOR:-}" ]; then
        "$EDITOR" "$file"
    else
        echo "Open: $file"
    fi
}
