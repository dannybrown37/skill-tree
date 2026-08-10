"""Regression tests for scripts/install.sh."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / 'install.sh'
REPO_ROOT = SCRIPT.parent.parent


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway $HOME, so the real one is never touched."""
    path = tmp_path / 'home'
    (path / '.local' / 'bin').mkdir(parents=True)
    return path


def run(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ['bash', str(SCRIPT)],  # noqa: S607
        capture_output=True,
        text=True,
        env={
            'HOME': str(home),
            'PATH': '/usr/bin:/bin',
            'SKILL_TREE_DIR': str(REPO_ROOT),
        },
        check=False,
    )


@pytest.mark.parametrize(
    ('link', 'target'),
    [
        ('.claude/skills/backlog', 'skills/backlog'),
        ('.local/bin/skill-tree', 'scripts/skill-tree'),
        ('.local/bin/backlog', 'skills/backlog/scripts/backlog'),
        # `bl` is the short form the backlog flow is habitually reached by --
        # it points at the same wrapper, not at a second copy of the logic.
        ('.local/bin/bl', 'skills/backlog/scripts/backlog'),
    ],
)
def test_install_links_are_created(home: Path, link: str, target: str) -> None:
    result = run(home)

    assert result.returncode == 0, result.stderr
    assert (home / link).resolve() == (REPO_ROOT / target).resolve()


def test_install_is_idempotent(home: Path) -> None:
    assert run(home).returncode == 0
    second = run(home)

    assert second.returncode == 0, second.stderr
    assert (home / '.local' / 'bin' / 'bl').is_symlink()


def test_install_does_not_clobber_a_real_file(home: Path) -> None:
    """Someone else's `bl` on PATH is left alone, not silently replaced."""
    theirs = home / '.local' / 'bin' / 'bl'
    theirs.write_text('#!/bin/sh\necho not ours\n')

    result = run(home)

    assert result.returncode == 0, result.stderr
    assert theirs.read_text() == '#!/bin/sh\necho not ours\n'
    assert 'Skipping' in result.stderr
