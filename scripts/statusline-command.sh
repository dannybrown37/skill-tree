#!/usr/bin/env bash
set -euo pipefail

input=$(cat)

model=$(echo "$input" | jq -r '.model.display_name // "unknown"')
effort=$(echo "$input" | jq -r '.effort.level // empty')
style=$(echo "$input" | jq -r '.output_style.name // empty')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // empty')
project=$(basename "$cwd" 2>/dev/null || true)
remaining=$(echo "$input" | jq -r '.context_window.remaining_percentage // empty')

branch=""
if [ -n "$cwd" ] && git -C "$cwd" --no-optional-locks rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  branch=$(git -C "$cwd" --no-optional-locks branch --show-current 2>/dev/null || true)
fi

dim="\033[2m"
reset="\033[0m"
cyan="\033[2;36m"
magenta="\033[2;35m"
yellow="\033[2;33m"
green="\033[2;32m"
blue="\033[2;34m"

parts=()
parts+=("$(printf "${cyan}%s${reset}" "$model")")

if [ -n "$effort" ]; then
  parts+=("$(printf "${magenta}effort:%s${reset}" "$effort")")
fi

if [ -n "$style" ]; then
  parts+=("$(printf "${yellow}style:%s${reset}" "$style")")
fi

if [ -n "$project" ]; then
  parts+=("$(printf "${dim}%s${reset}" "$project")")
fi

if [ -n "$branch" ]; then
  parts+=("$(printf "${green}%s${reset}" "$branch")")
fi

if [ -n "$remaining" ]; then
  parts+=("$(printf "${blue}ctx:%.0f%%${reset}" "$remaining")")
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
