"""Tests for `skill-tree stats`."""

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import skill_stats as stats

PLUGIN = 'skill-tree'
UNKNOWN = '<tool_use_error>Unknown skill: {name}</tool_use_error>'
BLOCKED = (
    '<tool_use_error>Skill {name} cannot be used with Skill tool due to '
    'disable-model-invocation. Ask the user to run it.</tool_use_error>'
)


def stamp(day: int) -> str:
    """Midday UTC, so the local date is the same in any timezone."""
    return f'2026-09-{day:02d}T12:00:00.000Z'


def typed(name: str, day: int, uuid: str, cwd: str = '/home/u/app') -> dict:
    return {
        'type': 'user',
        'uuid': uuid,
        'timestamp': stamp(day),
        'cwd': cwd,
        'message': {
            'role': 'user',
            'content': (
                f'<command-message>{name}</command-message>\n'
                f'<command-name>/{name}</command-name>\n'
                '<command-args>the thing</command-args>'
            ),
        },
    }


def called(name: str, day: int, call: str, cwd: str = '/home/u/app') -> dict:
    return {
        'type': 'assistant',
        'uuid': f'a-{call}',
        'timestamp': stamp(day),
        'cwd': cwd,
        'message': {
            'role': 'assistant',
            'content': [
                {'type': 'text', 'text': 'Loading the playbook.'},
                {
                    'type': 'tool_use',
                    'id': call,
                    'name': 'Skill',
                    'input': {'skill': name},
                },
            ],
        },
    }


def result(call: str, day: int, error: str | None = None) -> dict:
    block: dict = {
        'type': 'tool_result',
        'tool_use_id': call,
        'content': error or 'Launching skill',
    }
    if error:
        block['is_error'] = True
    return {
        'type': 'user',
        'uuid': f'r-{call}',
        'timestamp': stamp(day),
        'message': {'role': 'user', 'content': [block]},
    }


def write_transcript(
    projects: Path,
    records: list[dict],
    name: str = 'app/session-1.jsonl',
) -> Path:
    path = projects / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(record) + '\n' for record in records))
    return path


@pytest.fixture
def projects(tmp_path: Path) -> Path:
    path = tmp_path / 'projects'
    path.mkdir()
    return path


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A checkout with three skills, one the model may not invoke."""
    root = tmp_path / 'checkout'
    for name, extra in (
        ('handoff', ''),
        ('verify', ''),
        ('repo-audit', 'disable-model-invocation: true\n'),
    ):
        skill = root / 'skills' / name
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text(
            f'---\nname: {name}\ndescription: "x"\n{extra}---\n\n# {name}\n',
        )
    manifest = root / '.claude-plugin' / 'plugin.json'
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({'name': PLUGIN, 'version': '9.9.9'}))
    return root


def collect(projects: Path, since: datetime | None = None) -> stats.Report:
    return stats.collect(
        projects,
        skills={'handoff', 'verify', 'repo-audit'},
        plugin=PLUGIN,
        since=since,
    )


class TestSlashSkill:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            pytest.param(
                '<command-message>skill-tree:handoff</command-message>\n'
                '<command-name>/skill-tree:handoff</command-name>',
                'skill-tree:handoff',
                id='skill-prompt-puts-the-message-first',
            ),
            pytest.param(
                '<command-name>/clear</command-name>\n'
                '<command-message>clear</command-message>',
                None,
                id='built-in-puts-the-name-first',
            ),
            pytest.param('just a normal prompt', None, id='plain-prompt'),
            pytest.param(
                'look at this log:\n<command-message>handoff</command-message>'
                '\n<command-name>/handoff</command-name>',
                None,
                id='tags-pasted-mid-prompt-are-not-an-invocation',
            ),
            pytest.param(
                '<command-message>x</command-message>'
                '<command-name>/</command-name>',
                None,
                id='empty-name',
            ),
        ],
    )
    def test_reads_the_skill_a_prompt_invoked(
        self,
        text: str,
        expected: str | None,
    ) -> None:
        assert stats.slash_skill(text) == expected


class TestCollect:
    def test_counts_typed_and_agent_loaded_invocations_apart(
        self,
        projects: Path,
    ) -> None:
        write_transcript(
            projects,
            [
                typed('skill-tree:handoff', 10, 'u1'),
                typed('skill-tree:handoff', 11, 'u2'),
                called('skill-tree:handoff', 12, 'c1'),
                result('c1', 12),
            ],
        )

        usage = collect(projects).usage['handoff']

        assert (usage.user, usage.agent) == (2, 1)

    def test_a_bare_name_is_the_same_skill(self, projects: Path) -> None:
        write_transcript(
            projects,
            [typed('handoff', 10, 'u1'), called('handoff', 10, 'c1')],
        )

        usage = collect(projects).usage['handoff']

        assert (usage.user, usage.agent) == (1, 1)

    def test_last_used_is_the_most_recent_day(self, projects: Path) -> None:
        write_transcript(
            projects,
            [
                typed('skill-tree:verify', 14, 'u1'),
                called('skill-tree:verify', 20, 'c1'),
                typed('skill-tree:verify', 9, 'u2'),
            ],
        )

        assert collect(projects).usage['verify'].last_used == date(2026, 9, 20)

    def test_a_skill_nobody_invoked_still_gets_a_row(
        self,
        projects: Path,
    ) -> None:
        write_transcript(projects, [typed('skill-tree:handoff', 10, 'u1')])

        usage = collect(projects).usage['verify']

        assert (usage.user, usage.agent, usage.last_used) == (0, 0, None)

    def test_skills_from_elsewhere_are_ignored(self, projects: Path) -> None:
        write_transcript(
            projects,
            [
                typed('other-plugin:handoff', 10, 'u1'),
                called('notion-books', 10, 'c1'),
                result('c1', 10, UNKNOWN.format(name='notion-books')),
            ],
        )

        report = collect(projects)

        assert report.usage['handoff'].user == 0
        assert report.failed == []

    @pytest.mark.parametrize(
        ('name', 'error', 'reason'),
        [
            pytest.param(
                'skill-tree:bash-style',
                UNKNOWN,
                'unknown',
                id='a-skill-this-repo-no-longer-has',
            ),
            pytest.param(
                'repo-audit',
                BLOCKED,
                'blocked',
                id='model-invocation-disabled',
            ),
            pytest.param(
                'skill-tree:handoff',
                'Shell command failed: fatal: bad revision',
                'error',
                id='anything-else',
            ),
        ],
    )
    def test_a_load_that_errored_is_reported_not_counted(
        self,
        projects: Path,
        name: str,
        error: str,
        reason: str,
    ) -> None:
        write_transcript(
            projects,
            [
                called(name, 10, 'c1', cwd='/home/u/dotfiles'),
                result('c1', 10, error.format(name=name)),
                called(name, 15, 'c2', cwd='/home/u/dotfiles'),
                result('c2', 15, error.format(name=name)),
            ],
        )

        report = collect(projects)

        (failure,) = report.failed
        assert failure.name == name.removeprefix('skill-tree:')
        assert failure.reason == reason
        assert failure.count == 2
        assert failure.last == date(2026, 9, 15)
        assert failure.projects == {'dotfiles': 2}
        assert all(usage.agent == 0 for usage in report.usage.values())

    def test_a_call_with_no_recorded_result_counts_as_loaded(
        self,
        projects: Path,
    ) -> None:
        write_transcript(projects, [called('skill-tree:handoff', 10, 'c1')])

        assert collect(projects).usage['handoff'].agent == 1

    def test_a_record_copied_into_a_resumed_session_counts_once(
        self,
        projects: Path,
    ) -> None:
        records = [
            typed('skill-tree:handoff', 10, 'u1'),
            called('skill-tree:handoff', 10, 'c1'),
            result('c1', 10),
        ]
        write_transcript(projects, records, 'app/session-1.jsonl')
        write_transcript(projects, records, 'app/session-2.jsonl')

        usage = collect(projects).usage['handoff']

        assert (usage.user, usage.agent) == (1, 1)

    def test_subagent_transcripts_are_read_too(self, projects: Path) -> None:
        write_transcript(
            projects,
            [called('skill-tree:verify', 10, 'c1'), result('c1', 10)],
            'app/session-1/subagents/agent-a1.jsonl',
        )

        assert collect(projects).usage['verify'].agent == 1

    def test_since_drops_older_invocations(self, projects: Path) -> None:
        write_transcript(
            projects,
            [
                typed('skill-tree:handoff', 5, 'u1'),
                typed('skill-tree:handoff', 20, 'u2'),
            ],
        )
        cutoff = datetime(2026, 9, 10, tzinfo=UTC)

        assert collect(projects, since=cutoff).usage['handoff'].user == 1

    def test_first_day_is_the_oldest_record_on_disk(
        self,
        projects: Path,
    ) -> None:
        write_transcript(
            projects,
            [
                {'type': 'mode', 'mode': 'normal'},
                {'type': 'attachment', 'timestamp': stamp(3)},
                typed('skill-tree:handoff', 8, 'u1'),
            ],
        )
        write_transcript(
            projects,
            [typed('skill-tree:handoff', 12, 'u2')],
            'other/session-9.jsonl',
        )

        assert collect(projects).first_day == date(2026, 9, 3)

    def test_unparseable_lines_are_skipped(self, projects: Path) -> None:
        path = write_transcript(
            projects,
            [typed('skill-tree:handoff', 10, 'u1')],
        )
        with path.open('a') as handle:
            handle.write('{"type":"user","message":"<command-message>trunc\n')
            handle.write('"Skill" but not json\n')
            handle.write('["Skill", "a list, not a record"]\n')

        assert collect(projects).usage['handoff'].user == 1


class TestMain:
    def run(
        self,
        capsys: pytest.CaptureFixture[str],
        root: Path,
        projects: Path,
        *args: str,
    ) -> tuple[int, str, str]:
        code = stats.main(list(args), root=root, projects_dir=projects)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def test_table_has_a_row_per_skill_busiest_first(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
    ) -> None:
        write_transcript(
            projects,
            [
                typed('skill-tree:verify', 10, 'u1'),
                typed('skill-tree:handoff', 11, 'u2'),
                called('skill-tree:handoff', 12, 'c1'),
            ],
        )

        code, out, _ = self.run(capsys, fake_root, projects)

        assert code == 0
        rows = [line.split() for line in out.splitlines()]
        assert ['handoff', '1', '1', '2026-09-12'] in rows
        assert ['verify', '1', '0', '2026-09-10'] in rows
        names = [row[0] for row in rows if row]
        assert names.index('handoff') < names.index('verify')
        assert '1 of 3 skills not invoked' in out

    def test_agent_column_says_when_the_model_is_not_allowed(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
    ) -> None:
        write_transcript(projects, [typed('skill-tree:handoff', 11, 'u1')])

        _, out, _ = self.run(capsys, fake_root, projects)

        rows = [line.split() for line in out.splitlines()]
        assert ['repo-audit', '0', '-', 'never'] in rows
        assert ['verify', '0', '0', 'never'] in rows

    def test_window_names_the_days_the_transcripts_cover(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
    ) -> None:
        write_transcript(projects, [typed('skill-tree:handoff', 11, 'u1')])

        _, out, _ = self.run(capsys, fake_root, projects)

        assert 'since 2026-09-11' in out
        assert str(projects) in out

    def test_failed_loads_get_their_own_section(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
    ) -> None:
        name = 'skill-tree:bash-style'
        write_transcript(
            projects,
            [
                called(name, 10, 'c1', cwd='/home/u/dotfiles'),
                result('c1', 10, UNKNOWN.format(name=name)),
            ],
        )

        _, out, _ = self.run(capsys, fake_root, projects)

        failed = out[out.index('could not load') :]
        assert 'bash-style' in failed
        assert 'not in this repo' in failed
        assert 'dotfiles' in failed

    def test_no_failed_section_when_nothing_failed(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
    ) -> None:
        write_transcript(projects, [typed('skill-tree:handoff', 11, 'u1')])

        _, out, _ = self.run(capsys, fake_root, projects)

        assert 'could not load' not in out

    def test_json_carries_the_same_numbers(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
    ) -> None:
        name = 'skill-tree:bash-style'
        write_transcript(
            projects,
            [
                called(name, 10, 'c1', cwd='/home/u/dotfiles'),
                result('c1', 10, UNKNOWN.format(name=name)),
                typed('skill-tree:handoff', 11, 'u1'),
            ],
        )

        code, out, _ = self.run(capsys, fake_root, projects, '--json')

        payload = json.loads(out)
        assert code == 0
        assert payload['source'] == str(projects)
        assert payload['since'] == '2026-09-10'
        assert payload['skills'][0] == {
            'name': 'handoff',
            'user': 1,
            'agent': 0,
            'last_used': '2026-09-11',
            'model_invocable': True,
        }
        assert {entry['name'] for entry in payload['skills']} == {
            'handoff',
            'verify',
            'repo-audit',
        }
        assert payload['failed'] == [
            {
                'name': 'bash-style',
                'reason': 'unknown',
                'count': 1,
                'last': '2026-09-10',
                'projects': {'dotfiles': 1},
            },
        ]

    def test_days_limits_the_window(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
    ) -> None:
        write_transcript(projects, [typed('skill-tree:handoff', 11, 'u1')])

        _, out, _ = self.run(capsys, fake_root, projects, '--days', '1')

        assert ['handoff', '0', '0', 'never'] in [
            line.split() for line in out.splitlines()
        ]

    @pytest.mark.parametrize('days', ['0', '-3', 'soon'])
    def test_days_must_be_a_positive_number(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        projects: Path,
        days: str,
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            self.run(capsys, fake_root, projects, '--days', days)

        assert exit_info.value.code == 2
        assert '--days' in capsys.readouterr().err

    def test_no_transcripts_directory_says_where_it_looked(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        tmp_path: Path,
    ) -> None:
        missing = tmp_path / 'nowhere'

        code, out, err = self.run(capsys, fake_root, missing)

        assert code == 1
        assert out == ''
        assert str(missing) in err
        assert 'CLAUDE_CONFIG_DIR' in err

    def test_version_needs_no_transcripts(
        self,
        capsys: pytest.CaptureFixture[str],
        fake_root: Path,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            self.run(capsys, fake_root, tmp_path / 'nowhere', '--version')

        assert exit_info.value.code == 0
        assert capsys.readouterr().out.strip() == 'skill-tree stats 9.9.9'


class TestTranscriptsDir:
    def test_defaults_to_the_home_claude_directory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.delenv('CLAUDE_CONFIG_DIR', raising=False)
        monkeypatch.setenv('HOME', str(tmp_path))

        assert stats.transcripts_dir() == tmp_path / '.claude' / 'projects'

    def test_follows_claude_config_dir(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'elsewhere'))

        assert stats.transcripts_dir() == tmp_path / 'elsewhere' / 'projects'
