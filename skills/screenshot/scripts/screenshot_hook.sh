#!/usr/bin/env bash
# PreToolUse fires on every Bash/Read call; answer unrelated ones without
# paying Python's startup. Anything that could match goes to the real hook.
set -euo pipefail

# Not $(</dev/stdin): that reopens stdin by path, which fails on a socket.
IFS= read -r -d '' payload || true
shopt -s nocasematch

case "${payload}" in
*screenshot* | *.png* | *.jpg* | *.jpeg* | *.gif* | *.webp* | *.bmp*)
	# A missing or crashing python3 must not become an error on every image
	# read; fall through to "no opinion" instead.
	if command -v python3 >/dev/null 2>&1 &&
		decision="$(python3 "$(dirname "${BASH_SOURCE[0]}")/screenshot_hook.py" <<<"${payload}" 2>/dev/null)"; then
		printf '%s' "${decision}"
		exit 0
	fi
	;;
esac

# Copilot's preToolUse is fail-closed, so it needs an explicit abstain.
case "${payload}" in
*'"toolName"'* | *'"toolArgs"'*) printf '{"permissionDecision": "ask"}' ;;
esac
