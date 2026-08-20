"""Regression tests for scripts/check_repo_update.sh.

The script auto-pulls only when the checkout is provably safe to move
(clean, on the remote's default branch, strictly behind). Every other
shape falls back to telling the user what to run themselves.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / 'check_repo_update.sh'


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            'git',
            '-c',
            'user.email=test@example.com',
            '-c',
            'user.name=Test',
            '-C',
            str(cwd),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / 'home'
    path.mkdir()
    return path


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A clone of a local `origin`, with the script installed at scripts/.

    The script locates its repo root relative to its own path, so it has
    to live inside the fixture repo rather than be pointed at it.
    """
    origin = tmp_path / 'origin'
    (origin / 'scripts').mkdir(parents=True)
    git(origin, 'init', '--quiet', '--initial-branch=main')
    (origin / 'README.md').write_text('one\n')
    shutil.copy(SCRIPT, origin / 'scripts' / SCRIPT.name)
    git(origin, 'add', '-A')
    git(origin, 'commit', '--quiet', '-m', 'one')

    clone_path = tmp_path / 'clone'
    subprocess.run(  # noqa: S603
        ['git', 'clone', '--quiet', str(origin), str(clone_path)],  # noqa: S607
        check=True,
        capture_output=True,
    )
    return clone_path


def advance_origin(clone: Path) -> str:
    """Add a commit to the clone's origin; returns its sha."""
    origin = clone.parent / 'origin'
    (origin / 'README.md').write_text('two\n')
    git(origin, 'add', '-A')
    git(origin, 'commit', '--quiet', '-m', 'two')
    return git(origin, 'rev-parse', 'HEAD')


def run(clone: Path, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ['bash', str(clone / 'scripts' / SCRIPT.name)],  # noqa: S607
        capture_output=True,
        text=True,
        env={'HOME': str(home), 'PATH': '/usr/bin:/bin'},
        check=False,
    )


def test_clean_and_behind_pulls(clone: Path, home: Path) -> None:
    before = git(clone, 'rev-parse', 'HEAD')
    after = advance_origin(clone)

    result = run(clone, home)

    assert result.returncode == 0, result.stderr
    assert git(clone, 'rev-parse', 'HEAD') == after
    assert f'{before[:7]} -> {after[:7]}' in result.stderr


def test_clean_and_behind_prints_the_update_line(
    clone: Path,
    home: Path,
) -> None:
    advance_origin(clone)

    result = run(clone, home)

    assert 'skill-tree: updated' in result.stderr


def test_up_to_date_is_silent(clone: Path, home: Path) -> None:
    result = run(clone, home)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ''


def test_dirty_worktree_notifies_without_pulling(
    clone: Path,
    home: Path,
) -> None:
    (clone / 'README.md').write_text('local edit\n')
    before = git(clone, 'rev-parse', 'HEAD')
    advance_origin(clone)

    result = run(clone, home)

    assert result.returncode == 0, result.stderr
    assert git(clone, 'rev-parse', 'HEAD') == before
    assert 'Run: git -C' in result.stderr


def test_untracked_file_counts_as_dirty(clone: Path, home: Path) -> None:
    (clone / 'scratch.txt').write_text('notes\n')
    before = git(clone, 'rev-parse', 'HEAD')
    advance_origin(clone)

    result = run(clone, home)

    assert git(clone, 'rev-parse', 'HEAD') == before
    assert 'Run: git -C' in result.stderr


def test_feature_branch_notifies_without_pulling(
    clone: Path,
    home: Path,
) -> None:
    """Authoring happens on a branch; never move it under the user."""
    git(clone, 'checkout', '--quiet', '-b', 'feature')
    git(clone, 'push', '--quiet', '-u', 'origin', 'feature')
    before = git(clone, 'rev-parse', 'HEAD')

    origin = clone.parent / 'origin'
    git(origin, 'checkout', '--quiet', 'feature')
    (origin / 'README.md').write_text('feature work\n')
    git(origin, 'add', '-A')
    git(origin, 'commit', '--quiet', '-m', 'feature work')
    git(origin, 'checkout', '--quiet', 'main')

    result = run(clone, home)

    assert result.returncode == 0, result.stderr
    assert git(clone, 'rev-parse', 'HEAD') == before
    assert 'Run: git -C' in result.stderr


def test_diverged_notifies_without_pulling(clone: Path, home: Path) -> None:
    (clone / 'local.txt').write_text('mine\n')
    git(clone, 'add', '-A')
    git(clone, 'commit', '--quiet', '-m', 'local only')
    before = git(clone, 'rev-parse', 'HEAD')
    advance_origin(clone)

    result = run(clone, home)

    assert result.returncode == 0, result.stderr
    assert git(clone, 'rev-parse', 'HEAD') == before
    assert 'Run: git -C' in result.stderr


def test_throttled_to_one_check_per_hour(clone: Path, home: Path) -> None:
    assert run(clone, home).returncode == 0
    advance_origin(clone)
    before = git(clone, 'rev-parse', 'HEAD')

    result = run(clone, home)

    assert result.stderr == ''
    assert git(clone, 'rev-parse', 'HEAD') == before


def test_detached_head_is_left_alone(clone: Path, home: Path) -> None:
    before = git(clone, 'rev-parse', 'HEAD')
    git(clone, 'checkout', '--quiet', '--detach')
    advance_origin(clone)

    result = run(clone, home)

    assert result.returncode == 0, result.stderr
    assert git(clone, 'rev-parse', 'HEAD') == before
    assert result.stderr == ''
