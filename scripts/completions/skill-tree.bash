# Bash completion for the top-level `skill-tree` CLI.
#
# Deliberately thin: the candidate list is dynamic (skills are discovered
# at runtime), so this asks the CLI rather than keeping a second copy of
# the command list that would drift.

_skill_tree_complete() {
	COMPREPLY=()
	local _line
	# read loop rather than mapfile: bash 3.2 still ships as /bin/bash on
	# macOS, and this file is sourced by whatever bash the user has.
	while IFS= read -r _line; do
		COMPREPLY+=("${_line}")
	done < <(command skill-tree __complete "${COMP_WORDS[@]:1:COMP_CWORD}" 2>/dev/null)

	# Most sub-CLIs take a path as their argument, so when the CLI has
	# nothing to offer, fall back to what bash would have done anyway
	# rather than completing to nothing.
	if [[ ${#COMPREPLY[@]} -eq 0 ]]; then
		while IFS= read -r _line; do
			COMPREPLY+=("${_line}")
		done < <(compgen -f -- "${COMP_WORDS[COMP_CWORD]}")
	fi
}

complete -F _skill_tree_complete skill-tree
