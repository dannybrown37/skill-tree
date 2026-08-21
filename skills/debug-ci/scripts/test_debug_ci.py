"""Tests for the debug-ci failure-log extractor.

Nothing here touches the network: `gh` is always a stub, so every test
pins parsing, trimming, and exit-code behaviour rather than GitHub's
availability.
"""

import json
from collections.abc import Sequence

import pytest

import debug_ci_cli
from debug_ci_cli import (
    EXIT_NO_RUN,
    EXIT_OK,
    EXIT_UNUSABLE,
    DebugCIError,
    JobFailure,
    extract_failures,
    error_indices,
    parse_log,
    select_run,
    strip_timestamp,
    trim,
    main,
)

TS = '2026-08-20T10:00:00.0000000Z'
NEWEST_RUN = 222
OLDER_RUN = 111
CAP = 6


def log_line(job: str, step: str, message: str) -> str:
    return f'{job}\t{step}\t{TS} {message}'


def make_log(rows: Sequence[tuple[str, str, str]]) -> str:
    return '\n'.join(log_line(*row) for row in rows) + '\n'


PYTEST_LOG = make_log(
    [
        ('test (3.12)', 'Run pytest', 'collected 3 items'),
        ('test (3.12)', 'Run pytest', 'tests/test_a.py .'),
        ('test (3.12)', 'Run pytest', 'tests/test_b.py F'),
        ('test (3.12)', 'Run pytest', 'E   AssertionError: 1 != 2'),
        ('test (3.12)', 'Run pytest', '1 failed, 2 passed'),
        ('test (3.12)', 'Run pytest', '##[error]Process exited with code 1'),
    ],
)

RUNS_JSON = json.dumps(
    [
        {
            'databaseId': NEWEST_RUN,
            'displayTitle': 'fix: thing',
            'workflowName': 'CI',
            'headBranch': 'main',
            'conclusion': 'failure',
            'createdAt': '2026-08-20T10:00:00Z',
            'url': 'https://example.test/222',
        },
        {
            'databaseId': OLDER_RUN,
            'displayTitle': 'older',
            'workflowName': 'CI',
            'headBranch': 'main',
            'conclusion': 'failure',
            'createdAt': '2026-08-19T10:00:00Z',
            'url': 'https://example.test/111',
        },
    ],
)


@pytest.fixture
def gh(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Stub `gh`, keyed by the subcommand the CLI asks for."""
    responses: dict[str, object] = {
        'list': RUNS_JSON,
        'log': PYTEST_LOG,
    }
    calls: list[list[str]] = []

    def fake_gh(args: Sequence[str]) -> str:
        calls.append(list(args))
        value = responses['list' if 'list' in args else 'log']
        if isinstance(value, DebugCIError):
            raise value
        return str(value)

    monkeypatch.setattr(debug_ci_cli, 'gh', fake_gh)
    monkeypatch.setattr(debug_ci_cli, 'current_branch', lambda: 'main')
    responses['calls'] = calls
    return responses


class TestStripTimestamp:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            (f'{TS} boom', 'boom'),
            ('2026-08-20T10:00:00Z boom', 'boom'),
            ('no timestamp here', 'no timestamp here'),
            (f'{TS} ', ''),
        ],
    )
    def test_leading_timestamp_is_dropped(
        self,
        raw: str,
        expected: str,
    ) -> None:
        assert strip_timestamp(raw) == expected


class TestParseLog:
    def test_splits_job_step_and_message(self) -> None:
        lines = parse_log(PYTEST_LOG)
        assert lines[0].job == 'test (3.12)'
        assert lines[0].step == 'Run pytest'
        assert lines[0].message == 'collected 3 items'

    def test_ignores_blank_and_malformed_lines(self) -> None:
        text = f'\n{log_line("j", "s", "ok")}\nno tabs at all\n'
        assert [line.message for line in parse_log(text)] == ['ok']

    def test_keeps_tabs_inside_the_message(self) -> None:
        text = log_line('j', 's', 'a\tb')
        assert parse_log(text)[0].message == 'a\tb'


class TestErrorIndices:
    @pytest.mark.parametrize(
        'message',
        [
            '##[error]Process exited with code 1',
            'Error: cannot find module',
            'error: unused variable',
            'FAILED tests/test_a.py::test_b',
            'Traceback (most recent call last):',
            'AssertionError: 1 != 2',
            'npm ERR! code ELIFECYCLE',
            'Process completed with exit code 2.',
            'ruff.....................................................Failed',
            '- hook id: ruff-check',
            '✗ build failed',
        ],
    )
    def test_recognised_markers(self, message: str) -> None:
        assert error_indices([message]) == [0]

    @pytest.mark.parametrize(
        'message',
        [
            'collected 3 items',
            'Downloading pytest',
            '0 errors, 0 warnings',
            'shfmt....................................................Passed',
            'no-error-here',
        ],
    )
    def test_ordinary_output_is_not_a_marker(self, message: str) -> None:
        assert error_indices([message]) == []

    def test_returns_every_marker_position(self) -> None:
        messages = ['ok', 'Error: a', 'ok', 'error: b']
        assert error_indices(messages) == [1, 3]


class TestTrim:
    def test_keeps_context_around_the_marker(self) -> None:
        messages = [f'line {index}' for index in range(20)]
        messages[10] = 'Error: boom'
        kept = trim(messages, before=2, after=1, max_lines=50)
        assert kept == [
            '... 8 lines omitted ...',
            'line 8',
            'line 9',
            'Error: boom',
            'line 11',
            '... 8 lines omitted ...',
        ]

    def test_merges_overlapping_regions(self) -> None:
        messages = ['a', 'Error: one', 'b', 'Error: two', 'c']
        kept = trim(messages, before=1, after=1, max_lines=50)
        assert kept == ['a', 'Error: one', 'b', 'Error: two', 'c']

    def test_marks_where_output_was_elided(self) -> None:
        messages = ['keep' for _ in range(30)]
        messages[0] = 'Error: first'
        messages[29] = 'Error: last'
        kept = trim(messages, before=0, after=0, max_lines=50)
        assert kept == [
            'Error: first',
            '... 28 lines omitted ...',
            'Error: last',
        ]

    def test_falls_back_to_the_tail_without_a_marker(self) -> None:
        messages = [f'line {index}' for index in range(20)]
        assert trim(messages, before=3, after=3, max_lines=5) == messages[-5:]

    def test_caps_a_region_longer_than_max_lines(self) -> None:
        messages = ['Error: boom'] + [f'line {i}' for i in range(50)]
        kept = trim(messages, before=0, after=40, max_lines=CAP)
        assert len(kept) == CAP
        assert kept[0] == 'Error: boom'

    def test_empty_input(self) -> None:
        assert trim([], before=2, after=2, max_lines=10) == []


class TestExtractFailures:
    def test_one_entry_per_job_and_step(self) -> None:
        text = make_log(
            [
                ('build', 'Compile', 'error: bad syntax'),
                ('build', 'Compile', 'done'),
                ('test', 'Run pytest', 'AssertionError: nope'),
            ],
        )
        failures = extract_failures(text)
        assert [(f.job, f.step) for f in failures] == [
            ('build', 'Compile'),
            ('test', 'Run pytest'),
        ]

    def test_keeps_the_error_lines(self) -> None:
        (failure,) = extract_failures(PYTEST_LOG)
        assert any('AssertionError: 1 != 2' in line for line in failure.lines)

    def test_drops_steps_with_no_error_marker(self) -> None:
        text = make_log(
            [
                ('build', 'Checkout', 'cloning'),
                ('build', 'Compile', 'error: bad syntax'),
            ],
        )
        assert [f.step for f in extract_failures(text)] == ['Compile']

    def test_empty_log_yields_nothing(self) -> None:
        assert extract_failures('') == []

    def test_preserves_step_order_within_a_job(self) -> None:
        text = make_log(
            [
                ('build', 'Late', 'error: b'),
                ('build', 'Early', 'error: a'),
            ],
        )
        assert [f.step for f in extract_failures(text)] == ['Late', 'Early']


class TestFailingRuns:
    def test_filters_on_conclusion_client_side(
        self,
        gh: dict[str, object],
    ) -> None:
        gh['list'] = json.dumps(
            [
                {'databaseId': 1, 'conclusion': 'success'},
                {'databaseId': 2, 'conclusion': 'failure'},
                {'databaseId': 3, 'conclusion': 'timed_out'},
            ],
        )
        found = debug_ci_cli.failing_runs('main')
        assert [run['databaseId'] for run in found] == [2, 3]

    def test_does_not_pass_the_status_flag(
        self,
        gh: dict[str, object],
    ) -> None:
        debug_ci_cli.failing_runs('main')
        calls = gh['calls']
        assert isinstance(calls, list)
        assert '--status' not in calls[0]

    def test_unparsable_output_is_an_error(
        self,
        gh: dict[str, object],
    ) -> None:
        gh['list'] = 'not json'
        with pytest.raises(DebugCIError):
            debug_ci_cli.failing_runs('main')


class TestSelectRun:
    def test_picks_the_newest_failing_run(self) -> None:
        selected, others = select_run(json.loads(RUNS_JSON))
        assert selected.run_id == NEWEST_RUN
        assert [run.run_id for run in others] == [OLDER_RUN]

    def test_explicit_run_id_wins(self) -> None:
        selected, others = select_run(json.loads(RUNS_JSON), run_id=OLDER_RUN)
        assert selected.run_id == OLDER_RUN
        assert others == []

    def test_unknown_run_id_is_an_error(self) -> None:
        with pytest.raises(DebugCIError):
            select_run(json.loads(RUNS_JSON), run_id=999999)

    def test_no_runs_is_an_error(self) -> None:
        with pytest.raises(DebugCIError):
            select_run([])


class TestMain:
    @pytest.mark.usefixtures('gh')
    def test_prints_the_trimmed_failure(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main([]) == EXIT_OK
        out = capsys.readouterr().out
        assert 'AssertionError: 1 != 2' in out
        assert 'test (3.12)' in out

    @pytest.mark.usefixtures('gh')
    def test_json_output_is_machine_readable(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main(['--json']) == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload['run']['run_id'] == NEWEST_RUN
        assert payload['failures'][0]['job'] == 'test (3.12)'

    @pytest.mark.usefixtures('gh')
    def test_other_failing_runs_are_reported(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        main([])
        assert '111' in capsys.readouterr().out

    def test_no_failing_run_exits_one(
        self,
        gh: dict[str, object],
    ) -> None:
        gh['list'] = '[]'
        assert main([]) == EXIT_NO_RUN

    def test_gh_failure_is_unusable(
        self,
        gh: dict[str, object],
    ) -> None:
        gh['list'] = DebugCIError('gh: not authenticated')
        assert main([]) == EXIT_UNUSABLE

    def test_log_without_markers_still_reports_the_run(
        self,
        gh: dict[str, object],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        gh['log'] = make_log([('build', 'Compile', 'all quiet')])
        assert main([]) == EXIT_OK
        assert 'all quiet' in capsys.readouterr().out

    @pytest.mark.usefixtures('gh')
    def test_run_id_argument_skips_the_listing(self) -> None:
        assert main(['111']) == EXIT_OK

    def test_branch_flag_is_passed_to_gh(
        self,
        gh: dict[str, object],
    ) -> None:
        main(['--branch', 'feature/x'])
        calls = gh['calls']
        assert isinstance(calls, list)
        listing = next(call for call in calls if 'list' in call)
        assert 'feature/x' in listing

    def test_version_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--version'])
        assert exit_info.value.code == EXIT_OK

    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--help'])
        assert exit_info.value.code == EXIT_OK

    def test_unknown_flag_is_an_error(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--nope'])
        assert exit_info.value.code != EXIT_OK


class TestJobFailure:
    def test_render_includes_job_step_and_lines(self) -> None:
        failure = JobFailure(job='j', step='s', lines=['error: x'])
        rendered = debug_ci_cli.render_failure(failure)
        assert 'j' in rendered
        assert 's' in rendered
        assert 'error: x' in rendered
