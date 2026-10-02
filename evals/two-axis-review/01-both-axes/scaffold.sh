#!/usr/bin/env bash
set -euo pipefail

commit() {
	git -c user.name=eval -c user.email=eval@example.invalid add -A
	git -c user.name=eval -c user.email=eval@example.invalid commit -qm "$1"
}

mkdir -p docs

cat >CLAUDE.md <<'EOF'
# Conventions

- Every Python function has type hints on all parameters and on its return value.
- Invalid input raises `ValueError`; never return `None` to signal failure.
EOF

cat >docs/spec.md <<'EOF'
# parse_duration

`durations.parse_duration(text)` turns a human duration into whole seconds.

- Accept a single unit: `90s`, `5m`, `2h`.
- Accept compound durations, units in descending order: `1h30m`, `2m15s`.
- Ignore surrounding whitespace.
- Raise `ValueError` for anything else, including negative amounts and unknown units.
EOF

cat >README.md <<'EOF'
# durations
Parse human-readable durations.
EOF

git init -q -b main
commit 'chore: init'

cat >durations.py <<'EOF'
import re

UNITS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(text):
    match = re.fullmatch(r"(\d+)([smh])", text.strip())
    if not match:
        raise ValueError(f"bad duration: {text!r}")
    amount, unit = match.groups()
    return int(amount) * UNITS[unit]
EOF

cat >test_durations.py <<'EOF'
import unittest

from durations import parse_duration


class ParseDurationTest(unittest.TestCase):
    def test_single_units(self) -> None:
        self.assertEqual(parse_duration("90s"), 90)
        self.assertEqual(parse_duration(" 5m "), 300)
        self.assertEqual(parse_duration("2h"), 7200)

    def test_rejects_unknown_unit(self) -> None:
        with self.assertRaises(ValueError):
            parse_duration("3d")


if __name__ == "__main__":
    unittest.main()
EOF

commit 'feat: add parse_duration'
