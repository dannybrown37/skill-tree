#!/usr/bin/env bash
set -euo pipefail

cat >.pre-commit-config.yaml <<'YAML'
repos:
  - repo: local
    hooks:
      - id: no-todo
        name: no TODO markers
        entry: '\bTODO\b'
        language: pygrep
        types: [python]
YAML

cat >app.py <<'PY'
def greet(name: str) -> str:
    return f"hello {name}"
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
