#!/usr/bin/env bash
# One-liner entry point for a machine that has never cloned this repo:
#
#   curl -fsSL https://raw.githubusercontent.com/dannybrown37/skill-tree/main/scripts/bootstrap.sh | bash
#
# Clones (or reuses) the checkout, then hands off to install.sh -- this
# script owns nothing beyond "get the code onto disk", so install.sh stays
# the one place that knows how to link things.
set -euo pipefail

_repo_url='https://github.com/dannybrown37/skill-tree.git'
_dest="${SKILL_TREE_DIR:-${HOME}/projects/skill-tree}"

command -v git >/dev/null 2>&1 || {
	echo "bootstrap.sh: git is required" >&2
	exit 1
}

if [[ -d "${_dest}/.git" ]]; then
	echo "Found existing checkout at ${_dest}, pulling..."
	git -C "${_dest}" pull --ff-only
else
	echo "Cloning skill-tree into ${_dest}..."
	mkdir -p "$(dirname "${_dest}")"
	git clone "${_repo_url}" "${_dest}"
fi

exec "${_dest}/scripts/install.sh" "$@"
