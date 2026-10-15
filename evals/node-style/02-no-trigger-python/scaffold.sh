#!/usr/bin/env bash
set -euo pipefail

cat >pyproject.toml <<'TOML'
[project]
name = "relay"
version = "0.1.0"
requires-python = ">=3.13"
TOML

cat >relay.py <<'PY'
def relay(message: str) -> str:
    return message
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
