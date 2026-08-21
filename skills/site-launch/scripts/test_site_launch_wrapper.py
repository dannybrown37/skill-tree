"""The wrapper is a real executable the dispatcher can find and run."""

import subprocess
from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent / 'site-launch'

EXIT_FAILED_CHECK = 1
EXIT_UNUSABLE = 2

PAGE = """\
<html lang="en"><head><title>Home</title>
<meta name="description" content="Hi.">
</head><body></body></html>
"""


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(WRAPPER), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_wrapper_is_executable() -> None:
    assert WRAPPER.stat().st_mode & 0o111


def test_version_exits_zero_with_no_config() -> None:
    result = run('--version')
    assert result.returncode == 0
    assert result.stdout.startswith('site-launch ')


def test_no_arguments_prints_usage_and_fails() -> None:
    result = run()
    assert result.returncode != 0
    assert 'usage' in result.stderr.lower()


def test_check_reports_failures_and_exits_1(tmp_path: Path) -> None:
    (tmp_path / 'index.html').write_text(PAGE)
    result = run('check', str(tmp_path))
    assert result.returncode == EXIT_FAILED_CHECK
    assert 'FAIL' in result.stdout


@pytest.mark.parametrize('flag', ['--json'])
def test_json_flag_is_accepted(tmp_path: Path, flag: str) -> None:
    (tmp_path / 'index.html').write_text(PAGE)
    result = run('check', str(tmp_path), flag)
    assert result.stdout.lstrip().startswith('{')


def test_bad_directory_exits_2(tmp_path: Path) -> None:
    result = run('check', str(tmp_path / 'nope'))
    assert result.returncode == EXIT_UNUSABLE
    assert 'site-launch:' in result.stderr
