#!/usr/bin/env bash
# pre-push: turn the conventional commits since the last tag into a version.
#
# Runs `cz bump`, which rewrites .claude-plugin/plugin.json, writes CHANGELOG.md
# and creates a v* tag. That bump commit does not exist yet when git works out
# what to push, so this hook pushes the bumped ref itself and then fails the
# original push -- otherwise git would ship the pre-bump sha and the manifest
# would stay behind, which is exactly how the install got stuck on 0.1.0.
set -euo pipefail

_branch="$(git rev-parse --abbrev-ref HEAD)"
_cz() { uvx --from commitizen cz "$@"; }

if [[ "${_branch}" != "main" ]]; then
    exit 0
fi

if [[ -n "$(git status --porcelain)" ]]; then
    echo "pre-push: working tree is dirty, refusing to bump. Commit or stash first." >&2
    exit 1
fi

# No conventional commits since the last tag => nothing to release. `cz bump`
# exits 21 (NoCommitsFoundError) or 3 (NoneIncrementExit) in that case; both
# mean "push as-is", not "fail".
_out=""
_code=0
# Not `if ! _out=$(...)` -- the `!` resets $? to 0 and the real exit code,
# which is the whole signal here, would be lost.
_out="$(_cz bump --yes 2>&1)" || _code=$?
if ((_code != 0)); then
    case "${_code}" in
    3 | 21)
        echo "pre-push: no version-bumping commits since the last tag, pushing as-is."
        exit 0
        ;;
    *)
        echo "${_out}" >&2
        echo "pre-push: cz bump failed (exit ${_code})." >&2
        exit "${_code}"
        ;;
    esac
fi

_version="$(_cz version -p)"
echo "${_out}"

# --no-verify so this hook does not re-enter itself.
git push --no-verify --follow-tags origin "${_branch}"

cat >&2 <<EOF

pre-push: bumped to v${_version} and pushed it (commits + tag) already.
The original push is being cancelled because it pointed at the pre-bump commit
-- nothing is missing, your branch is fully pushed. Nothing else to do.
EOF
exit 1
