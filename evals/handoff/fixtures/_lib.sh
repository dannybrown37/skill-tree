# shellcheck shell=bash
# Sourced by each fixture's setup.sh. Pinned identity and dates keep every
# fixture's SHAs identical across runs, so anchor checks compare like with like.

export GIT_AUTHOR_NAME="Eval Fixture"
export GIT_AUTHOR_EMAIL="fixture@example.invalid"
export GIT_COMMITTER_NAME="${GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_AUTHOR_EMAIL}"

init_repo() {
	local dir="$1" branch="$2"
	mkdir -p "${dir}"
	git -C "${dir}" init -q -b main
	git -C "${dir}" config commit.gpgsign false
	git -C "${dir}" config core.hooksPath /dev/null
	if [[ "${branch}" != "main" ]]; then
		git -C "${dir}" commit -q --allow-empty -m "chore: initial commit" \
			--date "2026-09-01T09:00:00Z"
		git -C "${dir}" checkout -q -b "${branch}"
	fi
}

commit() {
	local dir="$1" when="$2" msg="$3"
	git -C "${dir}" add -A
	GIT_COMMITTER_DATE="${when}" git -C "${dir}" commit -q -m "${msg}" \
		--date "${when}"
}
