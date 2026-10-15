#!/usr/bin/env bash
set -euo pipefail

cat >notes.md <<'MD'
# Notes

Nothing here yet.
MD

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
