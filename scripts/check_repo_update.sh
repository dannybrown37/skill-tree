#!/usr/bin/env bash
# SessionStart (Copilot): bring this checkout up to date, or say why it can't.
#
# The sibling check_plugin_update.sh can always apply the update, because
# Claude's plugin install is a version-keyed cache dir nobody edits by hand.
# The Copilot install is this git clone -- the same clone the user develops
# skills in -- so an unconditional pull could stomp uncommitted work or move a
# branch they're mid-change on. Instead of never pulling, ask git whether this
# particular state is safe: clean worktree, on the remote's default branch, and
# strictly behind. That's a fast-forward and provably can't lose work. Anything
# else means the user has something in flight, so print the command and let
# them decide.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "${_script_dir}/.." && pwd)"
_stamp="${HOME}/.cache/skill-tree/last_repo_check"

command -v git >/dev/null 2>&1 || exit 0
git -C "${_repo_root}" rev-parse --git-dir >/dev/null 2>&1 || exit 0

# One network round-trip per hour at most, so opening a dozen sessions in a
# row doesn't mean a dozen fetches.
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

# A real fetch rather than ls-remote: telling "behind" from "diverged" needs
# the remote's commits locally, and that distinction is what gates the pull.
git -C "${_repo_root}" fetch --quiet "${_remote}" "${_branch}" 2>/dev/null || exit 0

_local_sha="$(git -C "${_repo_root}" rev-parse HEAD 2>/dev/null || echo '')"
_remote_sha="$(git -C "${_repo_root}" rev-parse FETCH_HEAD 2>/dev/null || echo '')"
[[ -n "${_local_sha}" && -n "${_remote_sha}" ]] || exit 0
[[ "${_local_sha}" == "${_remote_sha}" ]] && exit 0

_notify() {
	cat >&2 <<-EOF
		skill-tree: ${_local_sha:0:7} installed, ${_remote_sha:0:7} on ${_upstream}.
		Run: git -C ${_repo_root} pull && ${_repo_root}/scripts/install.sh --copilot
	EOF
	exit 0
}

# Gate 1: nothing uncommitted, staged, or untracked to lose.
[[ -z "$(git -C "${_repo_root}" status --porcelain 2>/dev/null)" ]] || _notify

# Gate 2: the remote's default branch only. Any other branch is someone
# authoring, and moving that under them is exactly what we're avoiding.
_default="$(git -C "${_repo_root}" symbolic-ref --quiet --short "refs/remotes/${_remote}/HEAD" 2>/dev/null || echo '')"
_default="${_default#"${_remote}/"}"
[[ -n "${_default}" ]] || _default='main'
[[ "${_branch}" == "${_default}" ]] || _notify

# Gate 3: strictly behind, so the merge is a pointer move. Diverged fails here.
git -C "${_repo_root}" merge-base --is-ancestor HEAD FETCH_HEAD 2>/dev/null || _notify

git -C "${_repo_root}" merge --ff-only --quiet FETCH_HEAD 2>/dev/null || _notify

# Silent updates are worse than the one line of noise: the skills the session
# is about to load just changed.
echo "skill-tree: updated ${_local_sha:0:7} -> ${_remote_sha:0:7} (${_upstream})" >&2

exit 0
