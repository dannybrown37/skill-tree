#!/usr/bin/env bash
# SessionStart (Copilot): say when this checkout is behind its remote.
#
# The sibling check_plugin_update.sh *applies* the update, which is only safe
# because Claude's plugin install is a version-keyed cache dir nobody edits by
# hand. The Copilot install is this git clone -- the same clone the user
# develops skills in -- so pulling under them could stomp uncommitted work or
# rebase a branch they're mid-change on. Notify, don't touch.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "${_script_dir}/.." && pwd)"
_stamp="${HOME}/.cache/skill-tree/last_repo_check"

command -v git >/dev/null 2>&1 || exit 0
git -C "${_repo_root}" rev-parse --git-dir >/dev/null 2>&1 || exit 0

# One network round-trip per hour at most, so opening a dozen sessions in a
# row doesn't mean a dozen ls-remotes.
mkdir -p "$(dirname "${_stamp}")"
if [[ -f "${_stamp}" ]]; then
    _age=$(($(date +%s) - $(stat -c %Y "${_stamp}" 2>/dev/null || echo 0)))
    ((_age < 3600)) && exit 0
fi
touch "${_stamp}"

_branch="$(git -C "${_repo_root}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
[[ -n "${_branch}" && "${_branch}" != "HEAD" ]] || exit 0

_upstream="$(git -C "${_repo_root}" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || echo '')"
[[ -n "${_upstream}" ]] || exit 0
_remote="${_upstream%%/*}"

_local_sha="$(git -C "${_repo_root}" rev-parse HEAD 2>/dev/null || echo '')"
_remote_sha="$(git -C "${_repo_root}" ls-remote "${_remote}" "${_branch}" 2>/dev/null | cut -f1)"
[[ -n "${_local_sha}" && -n "${_remote_sha}" ]] || exit 0
[[ "${_local_sha}" == "${_remote_sha}" ]] && exit 0

# Behind or diverged -- ls-remote alone can't tell which, and the fix is the
# same message either way: the user decides what to run in their own clone.
cat >&2 <<EOF
skill-tree: ${_local_sha:0:7} installed, ${_remote_sha:0:7} on ${_upstream}.
Run: git -C ${_repo_root} pull && ${_repo_root}/scripts/install.sh --copilot
EOF

exit 0
