"""The bundled CLIs must run inside the eval sandbox.

The sandbox makes HOME and TMPDIR read-only, passes only PATH through from
`just eval`, and leaves the sandbox's ~/.local/bin (where the SessionStart
hook links the CLIs) off PATH. Without scripts/eval-bin/, every checker died
before printing, and each case's "checker ran" grader failed.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

EVAL_BIN = Path(__file__).resolve().parent / 'eval-bin'


def _sandbox_env(tmp_path: Path, path: str) -> dict[str, str]:
    home = tmp_path / 'home'
    tmpdir = tmp_path / 'tmp'
    for d in (home, tmpdir):
        d.mkdir()
        d.chmod(stat.S_IRUSR | stat.S_IXUSR)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(('UV_', 'XDG_'))
    }
    return {**env, 'HOME': str(home), 'TMPDIR': str(tmpdir), 'PATH': path}


@pytest.mark.parametrize('cli', ['skill-tree', 'handoff'])
def test_cli_runs_with_read_only_home_and_tmpdir(
    cli: str,
    tmp_path: Path,
) -> None:
    env = _sandbox_env(tmp_path, f'{EVAL_BIN}:{os.environ["PATH"]}')
    result = subprocess.run(
        [cli, '--version'],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert cli in result.stdout


def test_uv_stand_in_reports_missing_real_uv(tmp_path: Path) -> None:
    real_uv = shutil.which('uv')
    assert real_uv
    path_dirs = [
        d
        for d in os.environ['PATH'].split(os.pathsep)
        if d and not (Path(d) / 'uv').exists()
    ]
    env = _sandbox_env(tmp_path, os.pathsep.join([str(EVAL_BIN), *path_dirs]))
    result = subprocess.run(
        [str(EVAL_BIN / 'uv'), '--version'],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 127
    assert 'no real uv' in result.stderr


@pytest.mark.parametrize(
    ('args', 'expected'),
    [
        ('repo view', 'eval/slugger'),
        (
            'repo view --json defaultBranchRef -q .defaultBranchRef.name',
            'main',
        ),
    ],
)
def test_gh_stand_in_repo_view(
    args: str,
    expected: str,
    tmp_path: Path,
) -> None:
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    (tmp_path / '.git' / 'eval-gh').mkdir()
    result = subprocess.run(
        [str(EVAL_BIN / 'gh'), *args.split()],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
