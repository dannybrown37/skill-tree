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

_dir="$(_handoff_dir)" || exit 0
_current="${_dir}/CURRENT.md"
_backlog="${_dir}/BACKLOG.md"

if [[ -s "${_current}" ]]; then
	cat "${_current}"
	cat <<'EOF'

---
This is an active handoff. Keep CURRENT.md and NARRATIVE.md current as each
task lands -- not at session end. Invoke the `handoff` skill for how.
EOF
	exit 0
fi

if [[ -s "${_backlog}" ]]; then
	_title="$(_first_backlog_title "${_backlog}")"
	if [[ -n "${_title}" ]]; then
		cat <<EOF
No active handoff in this repo. The next backlog item is:

  ${_title}

Confirm with the user before starting it. \`handoff pop\` claims it (removing
it from BACKLOG.md and writing it into CURRENT.md as the next action);
\`handoff list\` shows the rest.
EOF
	fi
fi

exit 0
