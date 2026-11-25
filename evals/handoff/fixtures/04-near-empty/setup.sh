#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../_lib.sh
source "$(dirname "$0")/../_lib.sh"

repo="$1/weatherbot"
init_repo "${repo}" "main"
mkdir -p "${repo}/tests"
cat >"${repo}/.pre-commit-config.yaml" <<'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: uv run pytest -q
        language: system
        pass_filenames: false
EOF
# The transcript shows "212 passed in 38.41s". A suite that can't plausibly
# match it makes a careful resumer doubt the number, and the judge then marks
# the goal fact partial and the doubt a hallucination. So: 212 tests over
# several modules, most of them behind a slow per-test station-replay fixture.
cat >"${repo}/pyproject.toml" <<'EOF'
[project]
name = "weatherbot"
version = "0.4.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27"]

[dependency-groups]
dev = ["pytest>=8"]
EOF
cat >"${repo}/tests/conftest.py" <<'EOF'
import time

import pytest


@pytest.fixture
def station_replay() -> list[float]:
    # Replays a recorded station feed at 10x speed; ~0.2s per test.
    readings = []
    for i in range(20):
        time.sleep(0.01)
        readings.append(15.0 + i * 0.1)
    return readings
EOF
cat >"${repo}/tests/test_ingest.py" <<'EOF'
import pytest


@pytest.mark.parametrize("station", range(120))
def test_ingest_keeps_every_reading(station: int, station_replay: list[float]) -> None:
    assert len(station_replay) == 20


@pytest.mark.parametrize("station", range(60))
def test_ingest_readings_are_monotonic(station: int, station_replay: list[float]) -> None:
    assert station_replay == sorted(station_replay)
EOF
cat >"${repo}/tests/test_forecast.py" <<'EOF'
import pytest


@pytest.mark.parametrize("hour", range(24))
def test_forecast_hour_in_range(hour: int) -> None:
    assert 0 <= hour % 24 < 24


@pytest.mark.parametrize("unit", ["C", "F", "K", "c", "f", "k", "C ", " F"])
def test_unit_normalises(unit: str) -> None:
    assert unit.strip().upper() in {"C", "F", "K"}
EOF
commit "${repo}" "2026-09-26T08:00:00Z" "chore: pre-commit with ruff and pytest"
