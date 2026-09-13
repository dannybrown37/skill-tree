#!/usr/bin/env bash
# SessionStart hook: put the live handoff (or the next backlog item) in front
# of the agent, and nothing else.
#
# stdout lands in the model's context on every session, so this is priced in
# tokens: a repo with an active handoff pays for CURRENT.md plus one line, a
# repo with only a backlog pays for one title, and a repo with neither pays
# nothing. Deliberately does *not* inject the handoff playbook -- that's a
# ~2k-token file the agent can invoke by name when it actually needs it.
#
# It also never pops. Claiming work nobody asked for is exactly the
# human-in-the-loop violation the skill warns about; the item is offered, and
# the agent asks first.
set -euo pipefail

_git_root() {
	local dir="${PWD}"
	while [[ "${dir}" != / ]]; do
		if [[ -e "${dir}/.git" ]]; then
			echo "${dir}"
			return 0
		fi
		dir="$(dirname "${dir}")"
	done
	return 1
}

_handoff_dir() {
	if [[ -n "${HANDOFF_DIR:-}" ]]; then
		echo "${HANDOFF_DIR}"
		return 0
	fi

	local root
	root="$(_git_root)" || return 1

	local branch
	branch="$(git -C "${root}" branch --show-current 2>/dev/null)" || return 1
	[[ -n "${branch}" ]] || return 1

	local sanitized="${branch//\//-}"
	echo "${root}/docs/handoffs/${sanitized}"
}

# First `## <title>` in the backlog, outside any fence. Bash rather than a
# call into handoff_cli.py: this runs on every session start in every repo,
# and starting an interpreter to read one line isn't worth the latency.
_first_backlog_title() {
	local file="$1"
	awk '
		/^[[:space:]]*(```|~~~)/ { fence = !fence; next }
		!fence && /^## / {
			sub(/^## /, "")
			gsub(/^[[:space:]]+|[[:space:]]+$/, "")
			if (length($0)) { print; exit }
		}
	' "${file}"
}

# The `**Status:**` keyword, fence-aware for the same reason the title
# reader is: a template line inside a fence is not this repo's state.
#
# No `{0,2}` intervals: mawk (Debian's default awk) doesn't support them, so
# the emphasis markers get stripped before matching rather than matched.
_current_status() {
	awk '
		/^[[:space:]]*(```|~~~)/ { fence = !fence; next }
		!fence {
			line = tolower($0)
			gsub(/[*`_]/, "", line)
			sub(/^[[:space:]]*([-+][[:space:]]+)?/, "", line)
			if (line ~ /^status:/) {
				sub(/^status:/, "", line)
				gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
				gsub(/[[:space:]]+/, "-", line)
				if (length(line)) { print line; exit }
			}
		}
	' "$1"
}

# Extract the anchor commit hash (HEAD `<sha>`) from CURRENT.md.
_anchor_commit() {
	grep -oP 'HEAD\s+`\K[0-9a-f]{7,40}' "$1" 2>/dev/null | head -1 || true
}

# True when HEAD has advanced past the anchor commit.
_head_advanced() {
	local repo="$1" anchor="$2"
	local head
	head="$(git -C "${repo}" rev-parse HEAD 2>/dev/null)" || return 1
	[[ "${head}" != "${anchor}"* && "${anchor}" != "${head}"* ]] || return 1
	git -C "${repo}" merge-base --is-ancestor "${anchor}" "${head}" 2>/dev/null
}

_offer_next() {
	local title
	title="$(_first_backlog_title "$1")"
	[[ -n "${title}" ]] || return 0
	cat <<EOF

The next backlog item is:

  ${title}

Confirm with the user before starting it. \`handoff pop\` claims it (removing
it from BACKLOG.md and writing it into CURRENT.md as the next action);
\`handoff backlog\` shows the rest.
EOF
}

_backlog_is_empty() {
	local file="$1"
	[[ ! -s "${file}" ]] && return 0
	local title
	title="$(_first_backlog_title "${file}")"
	[[ -z "${title}" ]]
}

_dir="$(_handoff_dir)" || exit 0
_current="${_dir}/CURRENT.md"
_backlog="${_dir}/BACKLOG.md"
_root="$(_git_root)" || _root=""

if [[ -s "${_current}" ]]; then
	_status="$(_current_status "${_current}")"

	# Promote awaiting-review to reviewed when the user committed past the anchor.
	if [[ "${_status}" == "awaiting-review" && -n "${_root}" ]]; then
		_anchor="$(_anchor_commit "${_current}")" || true
		if [[ -n "${_anchor}" ]] && _head_advanced "${_root}" "${_anchor}"; then
			_status="reviewed"
		fi
	fi

	cat "${_current}"
	case "${_status}" in
	reviewed)
		echo
		echo '---'
		echo 'The user reviewed and committed past the anchor. Ask what they want next.'
		[[ -s "${_backlog}" ]] && _offer_next "${_backlog}"
		;;
	between-tasks)
		echo
		echo '---'
		echo 'The last task landed; nothing is in flight.'
		if _backlog_is_empty "${_backlog}"; then
			cat <<'EOF'

This arc looks complete (between-tasks, empty backlog). Run `handoff close`
to clean up, or start a new task.
EOF
		elif [[ -s "${_backlog}" ]]; then
			_offer_next "${_backlog}"
		fi
		;;
	awaiting-review)
		cat <<'EOF'

---
This work is finished and awaiting the user's review. Do not start anything
new -- ask what they want next, or wait.
EOF
		;;
	*)
		cat <<'EOF'

---
This is an active handoff. Keep CURRENT.md and NARRATIVE.md current as each
task lands -- not at session end. Invoke the `handoff` skill for how.
EOF
		;;
	esac
	exit 0
fi

if [[ -s "${_backlog}" ]]; then
	if [[ -n "$(_first_backlog_title "${_backlog}")" ]]; then
		echo 'No active handoff in this repo.'
		_offer_next "${_backlog}"
	fi
fi

exit 0
