"""Wrappers must not adopt the Python project they are run from.

`uv run` with no project flag treats the nearest pyproject.toml above $PWD
as *the* project: it creates a .venv there and resolves that project's
dependencies before running anything. These CLIs run inside other people's
repos (repo-audit audits them, handoff lives in them), so a bare `uv run`
turned a read-only command into one that writes a .venv into the user's
repo, and fails outright when those dependencies can't be resolved.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = [
    ROOT / 'scripts' / 'skill-tree',
    ROOT / 'skills' / 'handoff' / 'scripts' / 'handoff',
    ROOT
    / 'skills'
    / 'dynamodb-cost-audit'
    / 'scripts'
    / 'dynamodb-cost-audit',
]

UNRESOLVABLE = """\
[project]
name = "someone-elses-app"
version = "0.1.0"
dependencies = ["package-that-does-not-exist-anywhere==9.9.9"]
"""


@pytest.mark.parametrize('wrapper', WRAPPERS, ids=lambda p: p.name)
def test_runs_from_inside_an_unrelated_project(
    wrapper: Path,
    tmp_path: Path,
) -> None:
    (tmp_path / 'pyproject.toml').write_text(UNRESOLVABLE)
    result = subprocess.run(
        [str(wrapper), '--version'],
        cwd=tmp_path,
        env={**os.environ, 'UV_OFFLINE': '1'},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / '.venv').exists()
