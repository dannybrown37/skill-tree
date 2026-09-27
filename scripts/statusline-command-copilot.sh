#!/usr/bin/env bash
# Copilot CLI statusLine command -- same look as the Claude side
# (scripts/statusline-command.sh), adapted to Copilot's payload shape.
# Copilot has no effort/output-style concept, so those segments are dropped.
set -euo pipefail

input=$(cat)

model=$(echo "$input" | jq -r '.model.display_name // .model.id // "unknown"')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // empty')
project=$(basename "$cwd" 2>/dev/null || true)
remaining=$(echo "$input" | jq -r 'if (.context_window.used_percentage != null) then (100 - .context_window.used_percentage) else empty end')
used_tokens=$(echo "$input" | jq -r '
  .context_window as $c
  | if $c.current_usage then ($c.current_usage.input_tokens // 0) + ($c.current_usage.cache_creation_input_tokens // 0) + ($c.current_usage.cache_read_input_tokens // 0)
    elif ($c.used_percentage != null and $c.context_window_size != null) then ($c.used_percentage * $c.context_window_size / 100 | floor)
    else empty end')

human_tokens() {
	local n=$1
	if [ "$n" -ge 1000000 ]; then
		awk -v n="$n" 'BEGIN { printf "%.1fM", n / 1000000 }'
	elif [ "$n" -ge 1000 ]; then
		printf "%dk" "$(((n + 500) / 1000))"
	else
		printf "%d" "$n"
	fi
}

branch=""
if [ -n "$cwd" ] && git -C "$cwd" --no-optional-locks rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	branch=$(git -C "$cwd" --no-optional-locks branch --show-current 2>/dev/null || true)
fi

dim="\033[2m"
reset="\033[0m"
cyan="\033[2;36m"
green="\033[2;32m"
blue="\033[2;34m"

parts=()
parts+=("$(printf "${cyan}%s${reset}" "$model")")

if [ -n "$project" ]; then
	parts+=("$(printf "${dim}%s${reset}" "$project")")
fi

if [ -n "$branch" ]; then
	parts+=("$(printf "${green}%s${reset}" "$branch")")
fi

if [ -n "$remaining" ]; then
	ctx=$(printf "ctx:%.0f%%" "$remaining")
	if [ -n "$used_tokens" ]; then
		ctx="$ctx ($(human_tokens "$used_tokens") used)"
	fi
	parts+=("$(printf "${blue}%s${reset}" "$ctx")")
fi

out=""
for p in "${parts[@]}"; do
	if [ -z "$out" ]; then
		out="$p"
	else
		out="$out $(printf '%b|%b' "${dim}" "${reset}") $p"
	fi
done

printf "%b\n" "$out"
