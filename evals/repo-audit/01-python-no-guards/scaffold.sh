#!/usr/bin/env bash
set -euo pipefail

mkdir -p src/myapp

cat >pyproject.toml <<'EOF'
[project]
name = "myapp"
version = "0.1.0"
dependencies = ["requests", "flask"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
EOF

: >src/myapp/__init__.py

cat >src/myapp/app.py <<'EOF'
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
EOF

cat >.gitignore <<'EOF'
__pycache__/
*.pyc
EOF

cat >README.md <<'EOF'
# myapp
A simple Flask app.
EOF

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
