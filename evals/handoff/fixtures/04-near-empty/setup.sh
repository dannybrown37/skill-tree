#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../_lib.sh
source "$(dirname "$0")/../_lib.sh"

repo="$1/weatherbot"
init_repo "${repo}" "main"
mkdir -p "${repo}/tests"
cat >"${repo}/.pre-commit-config.yaml" <<'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: uv run pytest -q
        language: system
        pass_filenames: false
EOF
cat >"${repo}/tests/test_smoke.py" <<'EOF'
def test_smoke() -> None:
    assert True
EOF
commit "${repo}" "2026-09-26T08:00:00Z" "chore: pre-commit with ruff and pytest"
