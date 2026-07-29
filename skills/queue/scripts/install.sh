#!/usr/bin/env bash
# One-time setup: make the queue skill and CLI available outside this repo.
#
# Runs standalone after a manual clone, or automatically via this plugin's
# SessionStart hook after `/plugin install`. Safe to re-run -- every step is
# idempotent and never overwrites a file or symlink it didn't create itself.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "${_script_dir}/../../.." && pwd)"

# Symlink `target` at `link_path`, but only if `link_path` is unoccupied or
# already a symlink this script manages -- never clobber a real file/dir a
# user put there themselves.
_link() {
    local target="$1" link_path="$2"
    mkdir -p "$(dirname "${link_path}")"

    if [[ -L "${link_path}" ]]; then
        [[ "$(readlink "${link_path}")" == "${target}" ]] && return 0
        # -n: link_path may itself be a symlink to a directory (e.g. an
        # earlier install pointed it at the plugin cache) -- plain `ln -sf`
        # would then dereference it and create the link *inside* that
        # directory instead of replacing it.
        ln -sfn "${target}" "${link_path}"
        echo "Updated ${link_path} -> ${target}"
        return 0
    fi

    if [[ -e "${link_path}" ]]; then
        echo "Skipping ${link_path}: already exists and isn't a symlink we manage" >&2
        return 0
    fi

    ln -s "${target}" "${link_path}"
    echo "Linked ${link_path} -> ${target}"
}

# Personal-scope skill dir, so `/queue` is invoked bare (a plugin-installed
# skill would otherwise always be namespaced, e.g. `/skill-tree:queue`).
_link "${_repo_root}/skills/queue" "${HOME}/.claude/skills/queue"

# Interactive CLI on PATH.
_link "${_repo_root}/skills/queue/scripts/queue" "${HOME}/.local/bin/queue"

if [[ "${_repo_root}" != "${HOME}/projects/skill-tree" && "${SKILL_TREE_DIR:-}" != "${_repo_root}" ]]; then
    cat >&2 <<EOF
Note: skill-tree is running from ${_repo_root}, not the default
~/projects/skill-tree. Export SKILL_TREE_DIR=${_repo_root} in your shell rc
so the queue skill's Claude-driven flow can find queue_cli.py.
EOF
fi

case ":${PATH}:" in
*":${HOME}/.local/bin:"*) ;;
*)
    echo "Note: ~/.local/bin isn't on PATH -- add it to use 'queue' directly." >&2
    ;;
esac
