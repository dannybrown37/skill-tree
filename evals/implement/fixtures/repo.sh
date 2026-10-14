#!/usr/bin/env bash
# A small Python package with a spec and two tickets; 02 is blocked by 01.
set -euo pipefail

mkdir -p docs/tickets

cat >CLAUDE.md <<'EOF2'
# textstats

- Tests: `python3 -m unittest -v`
- Typecheck: `python3 -m compileall -q textstats.py` (no mypy on this machine)
- Every function has type hints on its parameters and return value.
EOF2

cat >docs/spec.md <<'EOF2'
# textstats spec

Word statistics for plain text.

- A **word** is a run of letters, digits, apostrophes, or hyphens between
  other characters. `don't` and `well-known` are one word each.
- Case-insensitive: `The` and `the` are the same word.
- `word_count(text)` returns the number of words.
- `top_words(text, n)` returns the n most frequent words as
  `(word, count)` pairs, most frequent first, ties broken alphabetically.
EOF2

cat >docs/tickets/01-word-count.md <<'EOF2'
# 01 — word_count

Add `word_count(text: str) -> int` to `textstats.py`, per docs/spec.md.

## Acceptance

- `word_count("")` is 0
- `word_count("Hello, world!")` is 2
- `word_count("don't stop the well-known music")` is 5
- Tests in `test_textstats.py`
EOF2

cat >docs/tickets/02-top-words.md <<'EOF2'
# 02 — top_words

**Blocked by:** 01

Add `top_words(text: str, n: int) -> list[tuple[str, int]]` to
`textstats.py`, per docs/spec.md. Reuse 01's word definition.
EOF2

cat >textstats.py <<'EOF2'
def char_count(text: str) -> int:
    return len(text)
EOF2

cat >test_textstats.py <<'EOF2'
import unittest

from textstats import char_count


class CharCountTest(unittest.TestCase):
    def test_counts_characters(self) -> None:
        self.assertEqual(char_count("abc"), 3)


if __name__ == "__main__":
    unittest.main()
EOF2

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
