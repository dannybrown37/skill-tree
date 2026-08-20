"""Tests for the `handoff` wrapper and the session-start hook.

Both are shell, so these drive them as subprocesses in throwaway repos --
non-interactive, which is also the mode the hooks and tool calls run in.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
WRAPPER = SCRIPTS / 'handoff'
SESSION_START = SCRIPTS / 'handoff_session_start.sh'

SAMPLE = """\
# Backlog

## Wire the flag

Thread `--dry-run` through `cli.py:88`.

## Drop the shim

It has no callers left.
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / '.git').mkdir()
    handoffs = tmp_path / 'docs' / 'handoffs'
    handoffs.mkdir(parents=True)
    (handoffs / 'BACKLOG.md').write_text(SAMPLE)
    return tmp_path


def run(
    script: Path,
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, **(env or {})}
    environment.pop('HANDOFF_DIR', None)
    if env:
        environment.update(env)
    return subprocess.run(  # noqa: S603
        [str(script), *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class TestWrapper:
    def test_bare_invocation_prints_usage(self, repo: Path) -> None:
        result = run(WRAPPER, cwd=repo)
        assert result.returncode == 0
        assert 'Usage: handoff' in result.stdout

    @pytest.mark.parametrize('flag', ['-h', '--help'])
    def test_help_flags(self, repo: Path, flag: str) -> None:
        assert 'Usage: handoff' in run(WRAPPER, flag, cwd=repo).stdout

    def test_version(self, repo: Path) -> None:
        result = run(WRAPPER, '--version', cwd=repo)
        assert result.returncode == 0
        assert result.stdout.startswith('handoff ')

    def test_list_uses_the_repo_containing_cwd(self, repo: Path) -> None:
        nested = repo / 'src'
        nested.mkdir()
        result = run(WRAPPER, 'list', cwd=nested)
        assert result.returncode == 0
        assert 'Wire the flag' in result.stdout

    def test_add_without_a_title_fails_without_a_terminal(
        self,
        repo: Path,
    ) -> None:
        result = run(WRAPPER, 'add', cwd=repo)
        assert result.returncode != 0
        assert '--title is required' in result.stderr

    def test_add_with_flags_needs_no_terminal(self, repo: Path) -> None:
        result = run(
            WRAPPER,
            'add',
            '--title',
            'From the wrapper',
            '--body',
            'details',
            cwd=repo,
        )
        assert result.returncode == 0
        backlog = (repo / 'docs' / 'handoffs' / 'BACKLOG.md').read_text()
        assert 'From the wrapper' in backlog

    def test_pop_moves_the_item(self, repo: Path) -> None:
        result = run(WRAPPER, 'pop', cwd=repo)
        assert result.returncode == 0
        assert 'Wire the flag' in result.stdout
        handoffs = repo / 'docs' / 'handoffs'
        assert 'Wire the flag' not in (handoffs / 'BACKLOG.md').read_text()
        assert 'Wire the flag' in (handoffs / 'CURRENT.md').read_text()

    def test_outside_a_repo_without_a_terminal_is_an_error(
        self,
        tmp_path: Path,
    ) -> None:
        result = run(WRAPPER, 'list', cwd=tmp_path)
        assert result.returncode != 0
        assert 'not inside a git repo' in result.stderr

    def test_explicit_repo_flag_wins(self, repo: Path, tmp_path: Path) -> None:
        outside = tmp_path / 'outside'
        outside.mkdir()
        result = run(WRAPPER, 'list', '--repo', str(repo), cwd=outside)
        assert result.returncode == 0
        assert 'Wire the flag' in result.stdout


class TestSessionStart:
    def test_prints_current_when_one_exists(self, repo: Path) -> None:
        current = repo / 'docs' / 'handoffs' / 'CURRENT.md'
        current.write_text('# Continue here\n\nDo the thing.\n')
        result = run(SESSION_START, cwd=repo)
        assert result.returncode == 0
        assert 'Do the thing.' in result.stdout
        assert 'Keep CURRENT.md' in result.stdout

    def test_offers_the_next_item_when_no_current(self, repo: Path) -> None:
        result = run(SESSION_START, cwd=repo)
        assert result.returncode == 0
        assert 'Wire the flag' in result.stdout
        assert 'Confirm with the user' in result.stdout

    def test_does_not_pop(self, repo: Path) -> None:
        """Offering is not claiming -- the backlog must be untouched."""
        before = (repo / 'docs' / 'handoffs' / 'BACKLOG.md').read_text()
        run(SESSION_START, cwd=repo)
        after = (repo / 'docs' / 'handoffs' / 'BACKLOG.md').read_text()
        assert before == after
        assert not (repo / 'docs' / 'handoffs' / 'CURRENT.md').exists()

    def test_silent_with_no_handoff_files(self, tmp_path: Path) -> None:
        (tmp_path / '.git').mkdir()
        result = run(SESSION_START, cwd=tmp_path)
        assert result.returncode == 0
        assert result.stdout == ''

    def test_silent_outside_a_repo(self, tmp_path: Path) -> None:
        """Every session in every directory runs this -- it can't be noisy."""
        result = run(SESSION_START, cwd=tmp_path)
        assert result.returncode == 0
        assert result.stdout == ''
        assert result.stderr == ''

    def test_silent_on_an_empty_backlog(self, repo: Path) -> None:
        (repo / 'docs' / 'handoffs' / 'BACKLOG.md').write_text('# Backlog\n')
        result = run(SESSION_START, cwd=repo)
        assert result.returncode == 0
        assert result.stdout == ''

    def test_ignores_a_fenced_heading(self, repo: Path) -> None:
        (repo / 'docs' / 'handoffs' / 'BACKLOG.md').write_text(
            '# Backlog\n\n## Real item\n\n```\n## Fake item\n```\n',
        )
        result = run(SESSION_START, cwd=repo)
        assert 'Real item' in result.stdout
        assert 'Fake item' not in result.stdout

    def test_honors_handoff_dir(self, repo: Path, tmp_path: Path) -> None:
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()
        (elsewhere / 'CURRENT.md').write_text(
            '# Continue here\n\nOver here.\n',
        )
        result = run(
            SESSION_START,
            cwd=repo,
            env={'HANDOFF_DIR': str(elsewhere)},
        )
        assert 'Over here.' in result.stdout
