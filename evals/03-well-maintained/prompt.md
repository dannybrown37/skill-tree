---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
I have a Python project with the following files. Run a repo audit on it.

**pyproject.toml:**
```toml
[project]
name = "goodapp"
version = "1.2.0"
dependencies = ["httpx==0.27.0", "pydantic==2.9.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
```

**mypy.ini:**
```ini
[mypy]
strict = true
warn_return_any = true
```

**.pre-commit-config.yaml:**
```yaml
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
```

**src/goodapp/__init__.py:** (empty)

**src/goodapp/core.py:**
```python
import httpx

def fetch_data(url: str) -> dict:
    response = httpx.get(url)
    response.raise_for_status()
    return response.json()
```

**tests/__init__.py:** (empty)

**tests/test_core.py:**
```python
from goodapp.core import fetch_data

def test_fetch_data(httpx_mock):
    httpx_mock.add_response(json={"key": "value"})
    result = fetch_data("https://example.com")
    assert result == {"key": "value"}
```

**.gitignore:**
```
__pycache__/
*.pyc
.env
*.pem
dist/
```

**.claude/CLAUDE.md:**
```
# goodapp
Python HTTP client. Uses httpx, pydantic. Tests with pytest.
```

**README.md:**
```
# goodapp
A well-structured Python HTTP client library.

## Install
pip install goodapp

## Usage
from goodapp.core import fetch_data
data = fetch_data("https://api.example.com/data")
```

That's the entire project. Run a repo audit on it.
