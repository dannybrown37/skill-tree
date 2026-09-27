#!/usr/bin/env bash
# PreToolUse fires on every Bash/Read call; answer unrelated ones without
# paying Python's startup. Anything that could match goes to the real hook.
set -euo pipefail

payload="$(</dev/stdin)"
shopt -s nocasematch

case "${payload}" in
*screenshot* | *.png* | *.jpg* | *.jpeg* | *.gif* | *.webp* | *.bmp*)
	exec python3 "$(dirname "${BASH_SOURCE[0]}")/screenshot_hook.py" <<<"${payload}"
	;;
esac

# Copilot's preToolUse is fail-closed, so it needs an explicit abstain.
case "${payload}" in
*'"toolName"'* | *'"toolArgs"'*) printf '{"permissionDecision": "ask"}' ;;
esac
