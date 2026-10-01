#!/usr/bin/env bash
set -euo pipefail

mkdir -p src/goodapp tests .claude

cat >pyproject.toml <<'EOF'
[project]
name = "goodapp"
version = "1.2.0"
dependencies = ["httpx==0.27.0", "pydantic==2.9.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
EOF

cat >mypy.ini <<'EOF'
[mypy]
strict = true
warn_return_any = true
EOF

cat >.pre-commit-config.yaml <<'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.0
    hooks:
      - id: mypy
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
EOF

: >src/goodapp/__init__.py

cat >src/goodapp/core.py <<'EOF'
import httpx

def fetch_data(url: str) -> dict:
    response = httpx.get(url)
    response.raise_for_status()
    return response.json()
EOF

: >tests/__init__.py

cat >tests/test_core.py <<'EOF'
from goodapp.core import fetch_data

def test_fetch_data(httpx_mock):
    httpx_mock.add_response(json={"key": "value"})
    result = fetch_data("https://example.com")
    assert result == {"key": "value"}
EOF

cat >.gitignore <<'EOF'
__pycache__/
*.pyc
.env
*.pem
dist/
EOF

cat >.claude/CLAUDE.md <<'EOF'
# goodapp
Python HTTP client. Uses httpx, pydantic. Tests with pytest.
EOF

cat >README.md <<'EOF'
# goodapp
A well-structured Python HTTP client library.

## Install
pip install goodapp

## Usage
from goodapp.core import fetch_data
data = fetch_data("https://api.example.com/data")
EOF

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
