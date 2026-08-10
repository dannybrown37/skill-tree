#!/usr/bin/env bash
# One-time setup: make this plugin's skills and CLIs available outside this repo.
#
# Runs standalone after a manual clone, or automatically via this plugin's
# SessionStart hook after `/plugin install`. Safe to re-run -- every step is
# idempotent and never overwrites a file or symlink it didn't create itself.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "${_script_dir}/.." && pwd)"

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

# Personal-scope skill dirs, so e.g. `/backlog` is invoked bare (a
# plugin-installed skill would otherwise always be namespaced, e.g.
# `/skill-tree:backlog`).
#
# Deliberately only the skills worth a shortcut. A bare symlink is not free:
# the harness collapses a same-named plugin skill into just the unscoped
# alias, so anything listed here disappears from `skill-tree:`-prefixed
# lookups -- and from subagents that browse skills by that prefix.
_link "${_repo_root}/skills/backlog" "${HOME}/.claude/skills/backlog"

# Retire shortcuts earlier versions created, so a machine that ran those
# installs heals itself. Only ever removes a symlink pointing back into a
# skill-tree checkout -- never a real directory or someone else's link.
for _skill in debug-ci verify; do
    _stale="${HOME}/.claude/skills/${_skill}"
    if [[ -L "${_stale}" && "$(readlink "${_stale}")" == *"/skills/${_skill}" ]] &&
        [[ "$(readlink "${_stale}")" == *skill-tree* ]]; then
        rm "${_stale}"
        echo "Removed redundant ${_stale} (use skill-tree:${_skill})"
    fi
done

# The top-level entry point: browse/read every skill and reach every other
# CLI in here from a shell, without starting a Claude session.
_link "${_repo_root}/scripts/skill-tree" "${HOME}/.local/bin/skill-tree"

# Interactive backlog CLI on PATH, under both its full name and the `bl`
# short form -- it's reached often enough by hand that the seven extra
# keystrokes are the difference between capturing a thought and not.
_link "${_repo_root}/skills/backlog/scripts/backlog" "${HOME}/.local/bin/backlog"
_link "${_repo_root}/skills/backlog/scripts/backlog" "${HOME}/.local/bin/bl"

# The screenshot resolver stays off PATH deliberately: it's for the skill to
# call, `screenshot` is a plausible name for something else on a given
# machine, and `skill-tree screenshot` already reaches it.

if [[ "${_repo_root}" != "${HOME}/projects/skill-tree" && "${SKILL_TREE_DIR:-}" != "${_repo_root}" ]]; then
    cat >&2 <<EOF
Note: skill-tree is running from ${_repo_root}, not the default
~/projects/skill-tree. Export SKILL_TREE_DIR=${_repo_root} in your shell rc
so the backlog skill's Claude-driven flow can find backlog_cli.py.
EOF
fi

case ":${PATH}:" in
*":${HOME}/.local/bin:"*) ;;
*)
    echo "Note: ~/.local/bin isn't on PATH -- add it to use 'backlog' directly." >&2
    ;;
esac
