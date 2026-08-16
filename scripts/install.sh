#!/usr/bin/env bash
# One-time setup: make this repo's skills and CLIs available outside it.
#
# Runs standalone after a manual clone, or automatically via a SessionStart
# hook (Claude's plugin hooks.json, Copilot's generated hook config). Safe to
# re-run -- every step is idempotent and never overwrites a file or symlink it
# didn't create itself.
#
# Two hosts, installed independently:
#
#   Claude Code -- the plugin install already provides every skill as
#     `skill-tree:<name>`, so the only symlinks here are the deliberately
#     short list of extra shortcuts worth a second alias.
#   Copilot CLI -- no plugin or marketplace concept and no namespace, so
#     symlinking each skill into ~/.copilot/skills is the whole install, and
#     every skill lands bare.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "${_script_dir}/.." && pwd)"

_usage() {
    cat <<EOF
Usage: install.sh [--claude] [--copilot]

Link this repo's skills and CLIs into your home directory. Idempotent.

  --claude    Install the Claude Code side (shortcut symlinks, CLIs on PATH).
  --copilot   Install the Copilot CLI side (~/.copilot/skills + hook config).
  -h, --help  Show this message.

With no flags: the Claude side always runs, and the Copilot side runs only if
Copilot is present (~/.copilot exists, or \`copilot\` is on PATH).
EOF
}

_want_claude=''
_want_copilot=''
_explicit=''

while (($#)); do
    case "$1" in
    --claude)
        _want_claude=1
        _explicit=1
        ;;
    --copilot)
        _want_copilot=1
        _explicit=1
        ;;
    -h | --help)
        _usage
        exit 0
        ;;
    *)
        echo "install.sh: unknown option '$1'" >&2
        _usage >&2
        exit 2
        ;;
    esac
    shift
done

if [[ -z "${_explicit}" ]]; then
    _want_claude=1
    # Detected rather than assumed: a Claude-only machine shouldn't grow a
    # ~/.copilot directory as a side effect of installing this.
    if [[ -d "${HOME}/.copilot" ]] || command -v copilot >/dev/null 2>&1; then
        _want_copilot=1
    fi
fi

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
_install_claude() {
    _link "${_repo_root}/skills/backlog" "${HOME}/.claude/skills/backlog"

    # Retire shortcuts earlier versions created, so a machine that ran those
    # installs heals itself. Only ever removes a symlink pointing back into a
    # skill-tree checkout -- never a real directory or someone else's link.
    local _skill _stale
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

    # The screenshot resolver stays off PATH deliberately: it's for the skill
    # to call, `screenshot` is a plausible name for something else on a given
    # machine, and `skill-tree screenshot` already reaches it.

    # Output styles: symlink each .md into ~/.claude/output-styles/
    local style name
    for style in "${_repo_root}"/output-styles/*.md; do
        [[ -f "${style}" ]] || continue
        name="$(basename "${style}")"
        _link "${style}" "${HOME}/.claude/output-styles/${name}"
    done

    case ":${PATH}:" in
    *":${HOME}/.local/bin:"*) ;;
    *)
        echo "Note: ~/.local/bin isn't on PATH -- add it to use 'backlog' directly." >&2
        ;;
    esac
}

# Marks the hook config below as ours to overwrite. A file without it is
# something the user wrote by hand, and reinstalling must not eat it.
_HOOK_MARKER='"_source": "skill-tree"'

# Copilot's hook schema has no ${CLAUDE_PLUGIN_ROOT} equivalent and no
# guarantee that a var exported in a shell rc reaches the hook process, so
# the checkout path is baked in at install time rather than deferred.
_write_copilot_hooks() {
    local config="${HOME}/.copilot/hooks/skill-tree.json"

    if [[ -e "${config}" ]] && ! grep -qF "${_HOOK_MARKER}" "${config}"; then
        echo "Skipping ${config}: already exists and isn't a config we generated" >&2
        return 0
    fi

    mkdir -p "$(dirname "${config}")"
    cat >"${config}" <<EOF
{
  ${_HOOK_MARKER},
  "_comment": "Generated by skill-tree's install.sh. Edits are overwritten on reinstall; remove the _source line to take ownership.",
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "matcher": "(?i)(bash|shell|read|view)",
        "bash": "${_repo_root}/skills/screenshot/scripts/screenshot_hook.py",
        "timeoutSec": 15
      }
    ],
    "sessionStart": [
      {
        "type": "command",
        "bash": "${_repo_root}/scripts/install.sh --copilot",
        "timeoutSec": 30
      },
      {
        "type": "command",
        "bash": "${_repo_root}/scripts/check_repo_update.sh",
        "timeoutSec": 30
      }
    ]
  }
}
EOF
    echo "Wrote ${config}"
}

# Every skill, bare. Copilot has no namespace to hide the less-used ones
# behind, so the Claude side's "only shortcuts worth a second alias" rule has
# nothing to trade off against here -- unlinked means unreachable.
_install_copilot() {
    local skill name
    for skill in "${_repo_root}"/skills/*/; do
        [[ -f "${skill}/SKILL.md" ]] || continue
        name="$(basename "${skill}")"
        _link "${_repo_root}/skills/${name}" "${HOME}/.copilot/skills/${name}"
    done

    _write_copilot_hooks
}

[[ -n "${_want_claude}" ]] && _install_claude
[[ -n "${_want_copilot}" ]] && _install_copilot

if [[ "${_repo_root}" != "${HOME}/projects/skill-tree" && "${SKILL_TREE_DIR:-}" != "${_repo_root}" ]]; then
    cat >&2 <<EOF
Note: skill-tree is running from ${_repo_root}, not the default
~/projects/skill-tree. Export SKILL_TREE_DIR=${_repo_root} in your shell rc
so the backlog skill's agent-driven flow can find backlog_cli.py.
EOF
fi

exit 0
