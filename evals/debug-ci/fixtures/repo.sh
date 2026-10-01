#!/usr/bin/env bash
# Builds the repo every debug-ci case starts from, in the eval workspace
# (cwd). The bug is the missing .lower(); the unused `import os` is what
# the lint run in the two-failures fixture complains about.
set -euo pipefail

mkdir -p .github/workflows

cat >slug.py <<'EOF'
import os
import re


def slugify(title: str) -> str:
    words = re.findall(r'[A-Za-z0-9]+', title)
    return '-'.join(words)
EOF

cat >test_slug.py <<'EOF'
import unittest

from slug import slugify


class SlugifyTest(unittest.TestCase):
    def test_joins_words_with_hyphens(self) -> None:
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_drops_punctuation(self) -> None:
        self.assertEqual(slugify('Ship it!'), 'ship-it')


if __name__ == '__main__':
    unittest.main()
EOF

cat >.github/workflows/tests.yml <<'EOF'
name: tests
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v6
        with:
          python-version: '3.13'
      - name: Run tests
        run: python -m unittest -v
EOF

cat >.github/workflows/lint.yml <<'EOF'
name: lint
on: [push]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run ruff
        run: pipx run ruff check .
EOF

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'feat: slugify'
git checkout -qb feature/slugify

# Inside .git so the fixture is readable by the stand-in gh but never shows
# up in `git status`. No argument means gh reports "not logged in".
if [[ -n "${1:-}" ]]; then
	mkdir -p .git/eval-gh
	cp "$(dirname -- "${BASH_SOURCE[0]}")/${1}/"* .git/eval-gh/
fi
