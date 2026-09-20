---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
I have a Python project with the following structure and files. Audit it for quality issues.

**pyproject.toml:**
```toml
[project]
name = "myapp"
version = "0.1.0"
dependencies = ["requests", "flask"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**src/myapp/__init__.py:** (empty)

**src/myapp/app.py:**
```python
from flask import Flask, jsonify
import requests

app = Flask(__name__)

def get_users():
    resp = requests.get("https://api.example.com/users")
    return resp.json()

@app.route("/users")
def users():
    return jsonify(get_users())

@app.route("/health")
def health():
    return jsonify({"status": "ok"})
```

**.gitignore:**
```
__pycache__/
*.pyc
```

**README.md:**
```
# myapp
A simple Flask app.
```

That's the entire project — no other files exist. Audit it for all quality issues.
