#!/usr/bin/env bash
set -euo pipefail

cat >pyproject.toml <<'TOML'
[project]
name = "relay"
version = "0.1.0"
requires-python = ">=3.13"
TOML

cat >settings.toml <<'TOML'
[server]
host = "127.0.0.1"
port = 8080
TOML

cat >settings.py <<'PY'
from pathlib import Path

DEFAULT_PATH = Path("settings.toml")
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
