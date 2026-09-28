#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../_lib.sh
source "$(dirname "$0")/../_lib.sh"

repo="$1/linkcheck"
init_repo "${repo}" "feat/retry-429"
mkdir -p "${repo}/src/linkcheck" "${repo}/tests"
cat >"${repo}/pyproject.toml" <<'EOF'
[project]
name = "linkcheck"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = ["pytest==8.3.3", "ruff==0.6.9", "mypy==1.11.2"]

[tool.pytest.ini_options]
pythonpath = ["src"]
EOF
touch "${repo}/src/linkcheck/__init__.py"
cat >"${repo}/src/linkcheck/fetch.py" <<'EOF'
import urllib.request


def status(url: str) -> int:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status
EOF
commit "${repo}" "2026-09-26T10:00:00Z" "feat: basic link status fetch"

# Finished, green, uncommitted: the user reviews and commits.
cat >"${repo}/src/linkcheck/fetch.py" <<'EOF'
import time
import urllib.error
import urllib.request
from collections.abc import Callable

MAX_RETRIES = 3


def status(url: str, sleep: Callable[[float], object] = time.sleep) -> int:
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return int(r.status)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == MAX_RETRIES:
                return e.code
            retry_after = e.headers.get("Retry-After", "1")
            sleep(min(float(retry_after), 30.0))
    raise AssertionError("unreachable")
EOF
cat >"${repo}/tests/test_fetch.py" <<'EOF'
import email.message
import urllib.error

import pytest

from linkcheck import fetch


class _Resp:
    status = 200

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _fake_urlopen(codes: list[int]):
    it = iter(codes)

    def urlopen(url: str, timeout: int) -> _Resp:
        code = next(it)
        if code == 200:
            return _Resp()
        headers = email.message.Message()
        headers["Retry-After"] = "2"
        raise urllib.error.HTTPError(url, code, "x", headers, None)

    return urlopen


@pytest.mark.parametrize(
    ("codes", "expected", "sleeps"),
    [
        ([200], 200, 0),
        ([429, 200], 200, 1),
        ([429, 429, 200], 200, 2),
        ([429, 429, 429, 200], 200, 3),
        ([429, 429, 429, 429], 429, 3),
        ([404], 404, 0),
        ([500], 500, 0),
        ([503], 503, 0),
        ([429, 404], 404, 1),
    ],
)
def test_retry(monkeypatch, codes, expected, sleeps) -> None:
    monkeypatch.setattr(fetch.urllib.request, "urlopen", _fake_urlopen(codes))
    slept: list[float] = []
    assert fetch.status("https://x", sleep=slept.append) == expected
    assert len(slept) == sleeps
EOF
