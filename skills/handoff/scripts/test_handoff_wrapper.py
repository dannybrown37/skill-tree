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

    def test_backlog_uses_the_repo_containing_cwd(self, repo: Path) -> None:
        nested = repo / 'src'
        nested.mkdir()
        result = run(WRAPPER, 'backlog', cwd=nested)
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
        result = run(WRAPPER, 'backlog', cwd=tmp_path)
        assert result.returncode != 0
        assert 'not inside a git repo' in result.stderr

    def test_explicit_repo_flag_wins(self, repo: Path, tmp_path: Path) -> None:
        outside = tmp_path / 'outside'
        outside.mkdir()
        result = run(WRAPPER, 'backlog', '--repo', str(repo), cwd=outside)
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


class TestDocCommands:
    @pytest.mark.parametrize(
        ('command', 'name'),
        [
            ('current', 'CURRENT.md'),
            ('narrative', 'NARRATIVE.md'),
        ],
    )
    def test_prints_without_a_terminal(
        self,
        repo: Path,
        command: str,
        name: str,
    ) -> None:
        (repo / 'docs' / 'handoffs' / name).write_text('body text\n')
        result = run(WRAPPER, command, cwd=repo)
        assert result.returncode == 0
        assert 'body text' in result.stdout

    @pytest.mark.parametrize('command', ['current', 'narrative'])
    def test_missing_file_is_an_error(self, repo: Path, command: str) -> None:
        result = run(WRAPPER, command, cwd=repo)
        assert result.returncode != 0
        assert 'no ' in result.stderr

    @pytest.mark.parametrize('command', ['current', 'narrative', 'backlog'])
    def test_listed_in_usage(self, repo: Path, command: str) -> None:
        assert command in run(WRAPPER, '--help', cwd=repo).stdout


class TestRetiredCommands:
    @pytest.mark.parametrize('command', ['list', 'titles', 'show'])
    def test_gone_from_usage(self, repo: Path, command: str) -> None:
        usage = run(WRAPPER, '--help', cwd=repo).stdout
        assert f'  {command}' not in usage


class TestStatusIsCrossProject:
    """`status` must not ask which repo -- it scans all of them.

    The wrapper resolves a repo before dispatching every other subcommand,
    which for a cross-project command means prompting for an answer the
    output doesn't depend on. Outside a repo with no TTY that was a hard
    failure, which is exactly how it shipped broken the first time.
    """

    def test_runs_outside_any_repo(self, tmp_path: Path) -> None:
        projects = tmp_path / 'projects'
        (projects / 'alpha' / '.git').mkdir(parents=True)
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()

        result = run(
            WRAPPER,
            'status',
            cwd=elsewhere,
            env={'PROJECTS_DIR': str(projects)},
        )
        assert result.returncode == 0, result.stderr
        assert 'alpha' in result.stdout
        assert 'repo' not in result.stderr

    def test_set_still_needs_a_repo(self, repo: Path) -> None:
        (repo / 'docs' / 'handoffs' / 'CURRENT.md').write_text(
            '# Continue here\n',
        )
        result = run(WRAPPER, 'status', '--set', 'awaiting-review', cwd=repo)
        assert result.returncode == 0, result.stderr
        current = (repo / 'docs' / 'handoffs' / 'CURRENT.md').read_text()
        assert '**Status:** awaiting-review' in current

    def test_set_equals_form_still_needs_a_repo(self, repo: Path) -> None:
        (repo / 'docs' / 'handoffs' / 'CURRENT.md').write_text(
            '# Continue here\n',
        )
        result = run(WRAPPER, 'status', '--set=between-tasks', cwd=repo)
        assert result.returncode == 0, result.stderr
        current = (repo / 'docs' / 'handoffs' / 'CURRENT.md').read_text()
        assert '**Status:** between-tasks' in current


class TestSessionStartReadsStatus:
    """`between-tasks` must still surface the waiting backlog item.

    The hook used to offer the next item only when CURRENT.md was absent.
    Once a finished task leaves the file in place at `between-tasks`, that
    branch stops firing and the backlog goes silent -- the file exists, so
    the hook assumes work is underway.
    """

    def write_current(self, repo: Path, status: str) -> None:
        current = repo / 'docs' / 'handoffs' / 'CURRENT.md'
        current.write_text(
            f'# Continue here\n\n**Status:** {status}\n\nContext.\n',
        )

    def test_between_tasks_offers_the_next_item(self, repo: Path) -> None:
        self.write_current(repo, 'between-tasks')
        result = run(SESSION_START, cwd=repo)
        assert result.returncode == 0
        assert 'Context.' in result.stdout
        assert 'Wire the flag' in result.stdout
        assert 'Confirm with the user' in result.stdout

    def test_between_tasks_with_empty_backlog_offers_nothing(
        self,
        repo: Path,
    ) -> None:
        (repo / 'docs' / 'handoffs' / 'BACKLOG.md').write_text('# Backlog\n')
        self.write_current(repo, 'between-tasks')
        result = run(SESSION_START, cwd=repo)
        assert 'Confirm with the user' not in result.stdout

    def test_awaiting_review_does_not_offer_work(self, repo: Path) -> None:
        """The user owes the next move -- an agent must not start something."""
        self.write_current(repo, 'awaiting-review')
        result = run(SESSION_START, cwd=repo)
        assert 'Wire the flag' not in result.stdout
        assert 'review' in result.stdout.casefold()

    def test_in_progress_keeps_the_active_trailer(self, repo: Path) -> None:
        self.write_current(repo, 'in-progress')
        result = run(SESSION_START, cwd=repo)
        assert 'Keep CURRENT.md' in result.stdout
        assert 'Confirm with the user' not in result.stdout

    def test_status_inside_a_fence_is_not_read(self, repo: Path) -> None:
        current = repo / 'docs' / 'handoffs' / 'CURRENT.md'
        current.write_text(
            '# Continue here\n\n```\n**Status:** between-tasks\n```\n',
        )
        result = run(SESSION_START, cwd=repo)
        assert 'Confirm with the user' not in result.stdout

    def test_still_does_not_pop(self, repo: Path) -> None:
        self.write_current(repo, 'between-tasks')
        before = (repo / 'docs' / 'handoffs' / 'BACKLOG.md').read_text()
        run(SESSION_START, cwd=repo)
        after = (repo / 'docs' / 'handoffs' / 'BACKLOG.md').read_text()
        assert before == after
