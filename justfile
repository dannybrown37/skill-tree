default:
    @echo "Usage:"
    @echo "  just skill <name>            Scaffold a new skill in skills/<name>/"
    @echo "  just output-style <name>     Create an output style in output-styles/<name>.md"
    @echo "  just install                 Symlink skills, CLIs, and output styles into ~/"
    @echo "  just eval <skill> [flags]    Run evals/<skill>/ (flags pass to claude plugin eval)"
    @echo ""
    @echo "skill and output-style open the new file in VS Code or \$EDITOR."

skill name:
    @./scripts/new-skill.sh {{name}}

output-style name:
    @./scripts/new-output-style.sh {{name}}

install:
    @./scripts/install.sh

# Bash is granted only when a case asks for it: on a machine where the eval
# sandbox refuses Bash, Bash-free suites still run.
[no-exit-message]
[positional-arguments]
eval skill="" *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    mapfile -t suites < <(find evals -mindepth 3 -maxdepth 3 -name case.yaml | cut -d/ -f2 | sort -u)
    usage() {
        echo "usage: just eval <skill> [claude plugin eval flags...]" >&2
        echo "suites: ${suites[*]}" >&2
        exit 2
    }
    skill="${1:-}"
    shift || true
    if [[ -z "${skill}" ]]; then
        if [[ -t 0 && -t 2 ]] && command -v fzf >/dev/null; then
            skill="$(printf '%s\n' "${suites[@]}" | fzf --prompt='eval suite> ')" || exit 130
        else
            usage
        fi
    fi
    if [[ ! " ${suites[*]} " == *" ${skill} "* ]]; then
        echo "no eval suite named '${skill}'" >&2
        usage
    fi
    tools=(Edit Write)
    if grep -rqs --include=case.yaml -E 'allowed_tools:.*\bBash\b' "evals/${skill}"; then
        tools+=(Bash)
    fi
    # The eval sandbox refuses to grant Bash while ~/.docker holds symlinks
    # (Docker Desktop's WSL integration makes them), so it is moved aside for
    # the run only.
    docker_dir="${HOME}/.docker"
    docker_bak="${HOME}/.docker.eval-bak"
    # shellcheck disable=SC2317  # invoked via trap
    restore_docker() {
        if [[ -e "${docker_dir}" || -L "${docker_dir}" ]]; then
            echo "${docker_dir} reappeared during the run; yours is still at ${docker_bak}." >&2
            echo "Compare the two, then: rm -rf ${docker_dir} && mv ${docker_bak} ${docker_dir}" >&2
            return 1
        fi
        mv "${docker_bak}" "${docker_dir}"
        echo "restored ${docker_dir}" >&2
    }
    if [[ " ${tools[*]} " == *" Bash "* ]] && [[ -n "$(find -H "${docker_dir}" -mindepth 1 -type l -print -quit 2>/dev/null)" ]]; then
        if [[ -e "${docker_bak}" || -L "${docker_bak}" ]]; then
            echo "${docker_bak} exists: an earlier eval run didn't restore it." >&2
            echo "Check ~/.docker, then: mv ${docker_bak} ${docker_dir}" >&2
            exit 1
        fi
        mv "${docker_dir}" "${docker_bak}"
        trap restore_docker EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        echo "moved ${docker_dir} aside (the eval sandbox refuses its symlinks); restoring on exit" >&2
    fi
    status=0
    PATH="${PWD}/scripts/eval-bin:${PATH}" claude plugin eval . --tag "${skill}" --scaffold \
        --ablation none --no-publish --allow-tools "${tools[@]}" "$@" || status=$?
    echo "Run again with:"
    printf '  just eval'
    printf ' %q' "${skill}" "$@"
    echo
    case "${status}" in
    0) ;;
    1) echo "exit 1: a case scored below --threshold (default 1.0), or the run could not start; see above" >&2 ;;
    2) echo "exit 2: stopped early at the --max-cost-usd ceiling; results above are partial" >&2 ;;
    *) echo "exit ${status}: claude plugin eval failed" >&2 ;;
    esac
    exit "${status}"
