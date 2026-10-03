#!/usr/bin/env bash
set -euo pipefail

cat >durations.py <<'PY'
import re

UNITS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(text: str) -> int:
    match = re.fullmatch(r"(\d+)([smh])", text.strip())
    if not match:
        raise ValueError(f"bad duration: {text!r}")
    amount, unit = match.groups()
    return int(amount) * UNITS[unit]
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
