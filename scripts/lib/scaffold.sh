#!/usr/bin/env bash
# Shared argument handling for the scaffolding scripts.
# Usage: source this file, then call scaffold_name "<what>" "$@".

# The plugin manifest's version, parsed with sed rather than jq -- and
# `unknown` when there's no manifest, since --version has to answer
# without config or extra tooling.
plugin_version() {
    local manifest="$1/.claude-plugin/plugin.json" version=''
    if [ -f "$manifest" ]; then
        version="$(sed -n \
            's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
            "$manifest" | head -1)"
    fi
    echo "${version:-unknown}"
}

# A name that is safe to turn into a path: kebab-case, nothing else. This
# is what stops `new-skill.sh --version` from creating skills/--version,
# and `../escape` from writing outside the repo.
KEBAB_CASE='^[a-z0-9]+(-[a-z0-9]+)*$'

scaffold_reject_name() {
    local what="$1" name="$2"
    if [ -z "$name" ]; then
        echo "Error: $what name required." >&2
        return 1
    fi
    if ! [[ "$name" =~ $KEBAB_CASE ]]; then
        echo "Error: $what name must be kebab-case (got: $name)." >&2
        return 1
    fi
    return 0
}
