#!/usr/bin/env bash
# Point the installed plugin at this checkout, so local edits are live
# without a bump/tag/push/`/plugin update` round trip.
#
# The plugin manager installs a *tag*, into a version-pinned directory under
# ~/.claude/plugins/cache. A commit pushed to main but never tagged is
# invisible to `/plugin marketplace update` -- it correctly sees the
# installed version as the latest one. That's fine for consumers and
# maddening while authoring, which is what this exists for.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "${_script_dir}/.." && pwd)"

# Overridable so the tests can drive a fake plugin install.
INSTALLED_PLUGINS="${INSTALLED_PLUGINS:-${HOME}/.claude/plugins/installed_plugins.json}"
PLUGIN_ID="${PLUGIN_ID:-skill-tree@skill-tree}"

# Suffix for the stashed real install. Restoring beats re-downloading, so
# --on never deletes anything.
readonly BACKUP_SUFFIX='.real'

_die() {
    echo "Error: $*" >&2
    exit 1
}

# Where the plugin manager thinks this plugin lives. Parsed with python3
# rather than jq, which isn't guaranteed present.
_install_path() {
    [[ -f "${INSTALLED_PLUGINS}" ]] ||
        _die "No plugin install record at ${INSTALLED_PLUGINS} -- is the plugin installed?"

    python3 -c '
import json, sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text())
installs = record.get("plugins", {}).get(sys.argv[2], [])
if not installs:
    sys.exit(f"{sys.argv[2]} is not installed")
print(installs[0]["installPath"])
' "${INSTALLED_PLUGINS}" "${PLUGIN_ID}"
}

_status() {
    local install_path="$1"

    if [[ -L "${install_path}" ]]; then
        echo "Dev mode ON  (${install_path} -> $(readlink "${install_path}"))"
    elif [[ -d "${install_path}" ]]; then
        echo "Dev mode OFF (real install at ${install_path})"
    else
        echo "Dev mode OFF (nothing at ${install_path})"
    fi
}

_on() {
    local install_path="$1" backup="$1${BACKUP_SUFFIX}"

    if [[ -L "${install_path}" ]]; then
        [[ "$(readlink "${install_path}")" == "${_repo_root}" ]] ||
            _die "${install_path} already links elsewhere: $(readlink "${install_path}")"
        echo "Already on."
        return 0
    fi

    if [[ -d "${install_path}" ]]; then
        # A leftover backup means a previous --on ran without --off. The
        # older backup is the only pristine copy, so keep it.
        if [[ -e "${backup}" ]]; then
            rm -rf "${install_path}"
            echo "Discarded a re-downloaded install (kept existing ${backup})"
        else
            mv "${install_path}" "${backup}"
            echo "Backed up real install -> ${backup}"
        fi
    fi

    mkdir -p "$(dirname "${install_path}")"
    ln -s "${_repo_root}" "${install_path}"
    echo "Linked ${install_path} -> ${_repo_root}"
    echo
    echo "Dev mode ON. Restart Claude to pick it up."
    echo "Don't release from here -- run '$0 --off' first."
}

_off() {
    local install_path="$1" backup="$1${BACKUP_SUFFIX}"

    if [[ ! -L "${install_path}" ]]; then
        echo "Already off."
        return 0
    fi

    rm "${install_path}"

    if [[ -d "${backup}" ]]; then
        mv "${backup}" "${install_path}"
        echo "Restored the real install at ${install_path}"
    else
        echo "Removed the dev link. No backup to restore -- reinstall with:" >&2
        echo "  /plugin install ${PLUGIN_ID}" >&2
    fi

    echo "Restart Claude to pick it up."
}

main() {
    local action="${1:---status}" install_path
    install_path="$(_install_path)"

    case "${action}" in
    --on) _on "${install_path}" ;;
    --off) _off "${install_path}" ;;
    --status) _status "${install_path}" ;;
    -h | --help)
        sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
        echo
        echo "Usage: $0 [--on|--off|--status]"
        ;;
    *) _die "Unknown option: ${action} (try --help)" ;;
    esac
}

main "$@"
