#!/usr/bin/env bash
set -euo pipefail

cat >README.md <<'EOF'
# placeholder
This project is under construction.
EOF

cat >.gitignore <<'EOF'
*.pyc
EOF

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
