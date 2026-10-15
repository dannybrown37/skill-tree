#!/usr/bin/env bash
set -euo pipefail

cat >retry.py <<'PY'
import time
from collections.abc import Callable


def retry[T](fn: Callable[[], T], attempts: int = 3, base_delay: float = 0.5) -> T:
    for attempt in range(attempts):
        try:
            return fn()
        except ConnectionError:
            if attempt == attempts - 1:
                raise
            time.sleep(base_delay * 2**attempt)
    msg = "attempts must be at least 1"
    raise ValueError(msg)
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
