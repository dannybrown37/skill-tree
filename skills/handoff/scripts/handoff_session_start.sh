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

_handoff_dir() {
	if [[ -n "${HANDOFF_DIR:-}" ]]; then
		echo "${HANDOFF_DIR}"
		return 0
	fi

	local dir="${PWD}"
	while [[ "${dir}" != / ]]; do
		if [[ -e "${dir}/.git" ]]; then
			echo "${dir}/docs/handoffs"
			return 0
		fi
		dir="$(dirname "${dir}")"
	done
	return 1
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

_dir="$(_handoff_dir)" || exit 0
_current="${_dir}/CURRENT.md"
_backlog="${_dir}/BACKLOG.md"

if [[ -s "${_current}" ]]; then
	cat "${_current}"
	case "$(_current_status "${_current}")" in
	between-tasks)
		# The last task landed and nothing is half-written, so the useful
		# thing to put in front of the agent is what's queued -- not a
		# reminder to maintain a handoff that has nothing in flight.
		echo
		echo '---'
		echo 'The last task landed; nothing is in flight.'
		[[ -s "${_backlog}" ]] && _offer_next "${_backlog}"
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
