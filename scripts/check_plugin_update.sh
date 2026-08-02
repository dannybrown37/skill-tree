#!/usr/bin/env bash
# SessionStart: pull a newly pushed skill-tree version down with no extra work.
#
# The installed plugin is a snapshot -- `~/.claude/plugins/marketplaces/skill-tree`
# is a git clone that only moves on an explicit `marketplace update`, and the
# install itself lives in a version-keyed cache dir. Neither follows a push.
# This compares the remote HEAD against the sha actually installed and only
# then pays for the two update calls. Applies from the next session onward.
set -euo pipefail

_repo="https://github.com/dannybrown37/skill-tree.git"
_state="${HOME}/.claude/plugins/installed_plugins.json"
_stamp="${HOME}/.cache/skill-tree/last_update_check"

command -v git >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0
[[ -r "${_state}" ]] || exit 0

# One network round-trip per hour at most, so opening a dozen sessions in a
# row doesn't mean a dozen ls-remotes.
mkdir -p "$(dirname "${_stamp}")"
if [[ -f "${_stamp}" ]]; then
    _age=$(($(date +%s) - $(stat -c %Y "${_stamp}" 2>/dev/null || echo 0)))
    ((_age < 3600)) && exit 0
fi
touch "${_stamp}"

_installed="$(jq -r '.plugins["skill-tree@skill-tree"][0].gitCommitSha // empty' "${_state}")"
[[ -n "${_installed}" ]] || exit 0

_remote="$(git ls-remote "${_repo}" main 2>/dev/null | cut -f1)"
[[ -n "${_remote}" ]] || exit 0
[[ "${_remote}" == "${_installed}" ]] && exit 0

echo "skill-tree: ${_installed:0:7} -> ${_remote:0:7} available, updating..."
claude plugin marketplace update skill-tree >/dev/null 2>&1 || exit 0
claude plugin update skill-tree@skill-tree >/dev/null 2>&1 || exit 0
echo "skill-tree: updated. Restart Claude Code to pick it up."
