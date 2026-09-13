"""Tests for the handoff backlog CLI."""

import json
import re
from pathlib import Path

import pytest

from handoff_cli import (
    CURRENT_NAME,
    HANDLERS,
    BacklogItem,
    HandoffError,
    add_item,
    current_branch,
    find_item,
    handoff_dir,
    main,
    parse_anchor_commit,
    parse_backlog_text,
    parse_status,
    pop_item,
    read_items,
    remove_item,
    render_backlog,
    sanitize_branch,
    scan_projects,
    set_status,
    write_items,
    write_next_action,
)

SAMPLE = """\
# Backlog

## Wire the flag

Thread `--dry-run` through `cli.py:88`.

## Drop the shim

It has no callers left.
"""


def write_backlog(root: Path, content: str = SAMPLE) -> Path:
    directory = root / 'docs' / 'handoffs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'BACKLOG.md'
    path.write_text(content)
    return path


@pytest.fixture
def handoff_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tmp dir with HANDOFF_DIR set so CLI tests skip branch detection."""
    directory = tmp_path / 'docs' / 'handoffs'
    directory.mkdir(parents=True)
    monkeypatch.setenv('HANDOFF_DIR', str(directory))
    return directory


SKILL_DIR = Path(__file__).resolve().parents[1]
WRAPPER_ONLY_COMMANDS = {'edit', 'help'}


class TestParsing:
    def test_titles_and_bodies(self) -> None:
        items = parse_backlog_text(SAMPLE)
        assert [item.title for item in items] == [
            'Wire the flag',
            'Drop the shim',
        ]
        assert items[0].body == 'Thread `--dry-run` through `cli.py:88`.'

    @pytest.mark.parametrize(
        ('content', 'expected'),
        [
            ('', []),
            ('# Backlog\n', []),
            ('# Backlog\n\n## Solo\n', ['Solo']),
            # No `# Backlog` header at all -- items still parse.
            ('## Solo\n\nbody\n', ['Solo']),
            # A `###` subheading belongs to the item above it.
            ('## Solo\n\n### Detail\n\n## Next\n', ['Solo', 'Next']),
            # Trailing whitespace in a header shouldn't split the title.
            ('##   Padded   \n', ['Padded']),
        ],
    )
    def test_shapes(self, content: str, expected: list[str]) -> None:
        assert [item.title for item in parse_backlog_text(content)] == expected

    def test_fenced_hash_line_stays_in_body(self) -> None:
        """A `## ` inside a fenced block is content, not a new item."""
        content = (
            '# Backlog\n\n## Only item\n\n```markdown\n## Not a header\n```\n'
        )
        items = parse_backlog_text(content)
        assert [item.title for item in items] == ['Only item']
        assert '## Not a header' in items[0].body

    def test_round_trip(self) -> None:
        items = parse_backlog_text(SAMPLE)
        assert parse_backlog_text(render_backlog(items)) == items

    def test_render_empty_keeps_header(self) -> None:
        assert render_backlog([]) == '# Backlog\n'


class TestFindItem:
    ITEMS = (
        BacklogItem('Wire the flag', 'a'),
        BacklogItem('Drop the shim', 'b'),
    )

    @pytest.mark.parametrize(
        'title',
        ['Wire the flag', '  Wire the flag  ', 'wire the FLAG'],
    )
    def test_matches(self, title: str) -> None:
        found = find_item(list(self.ITEMS), title)
        assert found is not None
        assert found.title == 'Wire the flag'

    def test_no_match_returns_none(self) -> None:
        assert find_item(list(self.ITEMS), 'nonexistent') is None


class TestAddAndRemove:
    def test_add_appends(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        add_item(path, 'Third', 'body')
        assert [item.title for item in read_items(path)] == [
            'Wire the flag',
            'Drop the shim',
            'Third',
        ]

    def test_add_to_top(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        add_item(path, 'Urgent', 'body', to_top=True)
        assert read_items(path)[0].title == 'Urgent'

    def test_add_creates_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / 'docs' / 'handoffs' / 'BACKLOG.md'
        add_item(path, 'First', 'body')
        assert path.exists()
        assert [item.title for item in read_items(path)] == ['First']

    def test_add_empty_title_is_an_error(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        with pytest.raises(HandoffError):
            add_item(path, '   ', 'body')

    def test_add_preserves_a_body_containing_headers(
        self,
        tmp_path: Path,
    ) -> None:
        path = write_backlog(tmp_path)
        add_item(path, 'Pasted', 'log line\n## looks like a header\nmore')
        items = read_items(path)
        assert [item.title for item in items] == [
            'Wire the flag',
            'Drop the shim',
            'Pasted',
        ]
        assert '## looks like a header' in items[-1].body

    def test_reprotecting_a_body_is_idempotent(self, tmp_path: Path) -> None:
        """Rewriting must not wrap an already-fenced body a second time."""
        path = write_backlog(tmp_path)
        add_item(path, 'Pasted', 'log\n## header\nmore')
        first = path.read_text()
        write_items(path, read_items(path))
        assert path.read_text() == first

    def test_remove(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        remove_item(path, 'Wire the flag')
        assert [item.title for item in read_items(path)] == ['Drop the shim']

    def test_remove_unknown_title_raises(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        with pytest.raises(HandoffError):
            remove_item(path, 'nope')

    def test_remove_last_item_leaves_a_valid_file(
        self,
        tmp_path: Path,
    ) -> None:
        path = write_backlog(tmp_path, '# Backlog\n\n## Solo\n\nbody\n')
        remove_item(path, 'Solo')
        assert read_items(path) == []
        assert path.read_text() == '# Backlog\n'


class TestWriteItems:
    def test_write_is_atomic(self, tmp_path: Path) -> None:
        """No stray temp files left beside the backlog."""
        path = write_backlog(tmp_path)
        write_items(path, [BacklogItem('Only', 'body')])
        assert [p.name for p in path.parent.iterdir()] == ['BACKLOG.md']


CURRENT_WITH_SECTIONS = """\
# Continue here: something

## Goal

Ship the flag.

## Next action

Old stale action nobody should follow.

## Acceptance check

```bash
pytest -q
```
"""


class TestPop:
    def test_takes_the_top_item(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        item = pop_item(path, path.with_name('CURRENT.md'))
        assert item is not None
        assert item.title == 'Wire the flag'
        assert [i.title for i in read_items(path)] == ['Drop the shim']

    def test_writes_the_item_into_current(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        current = path.with_name('CURRENT.md')
        pop_item(path, current)
        text = current.read_text()
        assert 'Wire the flag' in text
        assert 'cli.py:88' in text

    def test_empty_backlog_returns_none_and_writes_nothing(
        self,
        tmp_path: Path,
    ) -> None:
        path = write_backlog(tmp_path, '# Backlog\n')
        current = path.with_name('CURRENT.md')
        assert pop_item(path, current) is None
        assert not current.exists()

    def test_missing_backlog_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / 'docs' / 'handoffs' / 'BACKLOG.md'
        assert pop_item(path, path.with_name('CURRENT.md')) is None

    def test_replaces_an_existing_next_action(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        current = path.with_name('CURRENT.md')
        current.write_text(CURRENT_WITH_SECTIONS)
        pop_item(path, current)
        text = current.read_text()
        assert 'Old stale action' not in text
        assert 'Wire the flag' in text
        # The sections around it survive.
        assert '## Goal' in text
        assert '## Acceptance check' in text
        assert 'pytest -q' in text

    def test_next_action_stays_a_single_section(self, tmp_path: Path) -> None:
        """Two pops must not leave two `## Next action` headings."""
        path = write_backlog(tmp_path)
        current = path.with_name('CURRENT.md')
        pop_item(path, current)
        pop_item(path, current)
        text = current.read_text()
        assert text.count('## Next action') == 1
        assert 'Drop the shim' in text
        assert 'Wire the flag' not in text

    def test_appends_a_section_when_current_has_none(
        self,
        tmp_path: Path,
    ) -> None:
        path = write_backlog(tmp_path)
        current = path.with_name('CURRENT.md')
        current.write_text('# Continue here\n\n## Goal\n\nShip it.\n')
        pop_item(path, current)
        text = current.read_text()
        assert '## Goal' in text
        assert text.count('## Next action') == 1

    def test_cli_pop_prints_the_item(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = handoff_env / 'BACKLOG.md'
        path.write_text(SAMPLE)
        assert main(['pop']) == 0
        out = capsys.readouterr().out
        assert 'Wire the flag' in out
        assert 'cli.py:88' in out

    def test_cli_pop_on_empty_backlog_is_quiet_and_succeeds(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The hook calls this constantly -- nothing queued isn't an error."""
        (handoff_env / 'BACKLOG.md').write_text('# Backlog\n')
        assert main(['pop']) == 0
        assert capsys.readouterr().out == ''


class TestWriteNextAction:
    def test_creates_current_from_nothing(self, tmp_path: Path) -> None:
        current = tmp_path / 'CURRENT.md'
        write_next_action(current, BacklogItem('Do it', 'the details'))
        text = current.read_text()
        assert text.startswith('# Continue here')
        assert 'Do it' in text
        assert '## Next action' in text
        assert 'the details' in text

    def test_a_body_with_headings_does_not_break_current(
        self,
        tmp_path: Path,
    ) -> None:
        current = tmp_path / 'CURRENT.md'
        write_next_action(current, BacklogItem('Do it', '## Not a section'))
        assert current.read_text().count('## Next action') == 1


class TestSanitizeBranch:
    @pytest.mark.parametrize(
        ('branch', 'expected'),
        [
            ('main', 'main'),
            ('feat/foo', 'feat-foo'),
            ('user/danny/feat/bar', 'user-danny-feat-bar'),
            ('release/1.0.0', 'release-1.0.0'),
            ('no-slashes', 'no-slashes'),
        ],
    )
    def test_sanitize(self, branch: str, expected: str) -> None:
        assert sanitize_branch(branch) == expected


class TestCurrentBranch:
    def test_returns_branch_name(self, tmp_path: Path) -> None:
        import subprocess

        subprocess.run(
            ['git', 'init', str(tmp_path)],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ['git', 'checkout', '-b', 'feat/test'],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        assert current_branch(tmp_path) == 'feat/test'

    def test_detached_head_returns_none(self, tmp_path: Path) -> None:
        import subprocess

        subprocess.run(
            ['git', 'init', str(tmp_path)],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ['git', 'commit', '--allow-empty', '-m', 'init'],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        head = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            ['git', 'checkout', head],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        assert current_branch(tmp_path) is None

    def test_non_repo_returns_none(self, tmp_path: Path) -> None:
        assert current_branch(tmp_path) is None


class TestHandoffDir:
    def test_walks_up_to_git_root_with_branch(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import subprocess

        monkeypatch.delenv('HANDOFF_DIR', raising=False)
        subprocess.run(
            ['git', 'init', str(tmp_path)],
            capture_output=True,
            check=True,
        )
        nested = tmp_path / 'src' / 'deep'
        nested.mkdir(parents=True)
        branch = current_branch(tmp_path)
        assert branch is not None
        assert handoff_dir(start=nested) == (
            tmp_path / 'docs' / 'handoffs' / sanitize_branch(branch)
        )

    def test_slash_branch_sanitized_in_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import subprocess

        monkeypatch.delenv('HANDOFF_DIR', raising=False)
        subprocess.run(
            ['git', 'init', str(tmp_path)],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ['git', 'checkout', '-b', 'feat/foo'],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        assert handoff_dir(start=tmp_path) == (
            tmp_path / 'docs' / 'handoffs' / 'feat-foo'
        )

    def test_env_override_wins(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / '.git').mkdir()
        monkeypatch.setenv('HANDOFF_DIR', str(tmp_path / 'elsewhere'))
        assert handoff_dir(start=tmp_path) == tmp_path / 'elsewhere'

    def test_outside_a_repo_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv('HANDOFF_DIR', raising=False)
        with pytest.raises(HandoffError, match='not inside a git repo'):
            handoff_dir(start=tmp_path)

    def test_detached_head_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import subprocess

        monkeypatch.delenv('HANDOFF_DIR', raising=False)
        subprocess.run(
            ['git', 'init', str(tmp_path)],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ['git', 'commit', '--allow-empty', '-m', 'init'],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        head = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            ['git', 'checkout', head],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        with pytest.raises(HandoffError, match='detached HEAD'):
            handoff_dir(start=tmp_path)


class TestCli:
    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        """argparse prints and exits 0 -- the contract is the exit code."""
        with pytest.raises(SystemExit) as exit_info:
            main(['--version'])
        assert exit_info.value.code == 0
        assert capsys.readouterr().out.startswith('handoff ')

    def test_backlog_prints_the_file(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        assert main(['backlog']) == 0
        out = capsys.readouterr().out
        assert 'Wire the flag' in out
        assert 'Drop the shim' in out

    def test_backlog_titles_are_bare(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        assert main(['backlog', '--titles']) == 0
        assert capsys.readouterr().out.split('\n')[:2] == [
            'Wire the flag',
            'Drop the shim',
        ]

    @pytest.mark.parametrize('action', ['list', 'titles', 'show'])
    def test_retired_commands_are_gone(
        self,
        action: str,
    ) -> None:
        with pytest.raises(SystemExit):
            main([action])

    def test_add(self, handoff_env: Path) -> None:
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        code = main(['add', '--title', 'New', '--body', 'b'])
        assert code == 0
        assert read_items(handoff_env / 'BACKLOG.md')[-1].title == 'New'

    def test_next_adds_to_top(self, handoff_env: Path) -> None:
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        main(['next', '--title', 'Now', '--body', 'b'])
        assert read_items(handoff_env / 'BACKLOG.md')[0].title == 'Now'

    def test_remove_without_a_title_lists_and_fails(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        assert main(['remove']) == 1
        assert 'Wire the flag' in capsys.readouterr().err

    def test_remove_exits_zero_on_success(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A working removal must not look like a failure to a hook."""
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        code = main(['remove', '--item-title', 'Drop the shim'])
        assert code == 0
        assert 'Removed: Drop the shim' in capsys.readouterr().out
        assert [
            item.title for item in read_items(handoff_env / 'BACKLOG.md')
        ] == [
            'Wire the flag',
        ]

    def test_unknown_title_exits_one(self, handoff_env: Path) -> None:
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        code = main(['remove', '--item-title', 'nope'])
        assert code == 1


class TestDocs:
    @pytest.mark.parametrize(
        ('action', 'name'),
        [
            ('current', 'CURRENT.md'),
            ('narrative', 'NARRATIVE.md'),
            ('backlog', 'BACKLOG.md'),
        ],
    )
    def test_prints_the_file(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
        action: str,
        name: str,
    ) -> None:
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        (handoff_env / name).write_text('# Heading\n\nbody text\n')
        assert main([action]) == 0
        assert 'body text' in capsys.readouterr().out

    @pytest.mark.parametrize('action', ['current', 'narrative', 'backlog'])
    def test_missing_file_exits_one(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
        action: str,
    ) -> None:
        assert main([action]) == 1
        assert 'no ' in capsys.readouterr().err

    @pytest.mark.parametrize(
        ('action', 'name'),
        [
            ('current', 'CURRENT.md'),
            ('narrative', 'NARRATIVE.md'),
            ('backlog', 'BACKLOG.md'),
        ],
    )
    def test_path_flag_prints_the_path(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
        action: str,
        name: str,
    ) -> None:
        (handoff_env / name).write_text('x\n')
        assert main([action, '--path']) == 0
        assert capsys.readouterr().out.strip() == str(handoff_env / name)


class TestDocsMatchTheCli:
    """Docs naming a subcommand that doesn't exist is a real bug.

    `handoff list` outlived its rename to `backlog` in SKILL.md, and nothing
    caught it.
    """

    @pytest.mark.parametrize(
        'doc',
        ['SKILL.md', 'references/backlog.md', 'references/flow.md'],
    )
    def test_every_documented_subcommand_exists(self, doc: str) -> None:
        text = (SKILL_DIR / doc).read_text()
        known = set(HANDLERS) | WRAPPER_ONLY_COMMANDS
        for command in re.findall(r'`handoff +([a-zA-Z][\w-]*)', text):
            assert command in known, f'{doc} documents `handoff {command}`'


class TestStatusKeyword:
    """The `**Status:**` line in CURRENT.md, and reading it back."""

    @pytest.mark.parametrize(
        ('line', 'expected'),
        [
            ('**Status:** in-progress', 'in-progress'),
            ('**Status:** between-tasks', 'between-tasks'),
            ('**Status:** awaiting-review', 'awaiting-review'),
            ('**Status:** awaiting review', 'awaiting-review'),
            ('**Status:**  IN-PROGRESS ', 'in-progress'),
            ('**Status:** in progress', 'in-progress'),
            ('Status: between-tasks', 'between-tasks'),
            ('- **Status:** in-progress', 'in-progress'),
            ('**Status:** nonsense', None),
            ('no keyword here', None),
        ],
    )
    def test_parse_status(self, line: str, expected: str | None) -> None:
        assert (
            parse_status(f'# Continue here\n\n{line}\n\n## Goal\n') == expected
        )

    def test_fenced_status_is_ignored(self) -> None:
        text = '# Continue here\n\n```\n**Status:** in-progress\n```\n'
        assert parse_status(text) is None

    def test_first_status_wins(self) -> None:
        text = '**Status:** between-tasks\n\n**Status:** in-progress\n'
        assert parse_status(text) == 'between-tasks'

    def test_set_status_adds_line_when_absent(self, tmp_path: Path) -> None:
        current = tmp_path / CURRENT_NAME
        current.write_text('# Continue here\n\n## Goal\n\nShip it.\n')
        set_status(current, 'in-progress')
        assert parse_status(current.read_text()) == 'in-progress'
        assert '## Goal' in current.read_text()

    def test_set_status_replaces_existing_line(self, tmp_path: Path) -> None:
        current = tmp_path / CURRENT_NAME
        current.write_text(
            '# Continue here\n\n**Status:** between-tasks\n\n## Goal\n',
        )
        set_status(current, 'in-progress')
        text = current.read_text()
        assert parse_status(text) == 'in-progress'
        assert text.count('**Status:**') == 1

    def test_set_status_rejects_unknown_value(self, tmp_path: Path) -> None:
        current = tmp_path / CURRENT_NAME
        current.write_text('# Continue here\n')
        with pytest.raises(HandoffError, match=r'in\-progress'):
            set_status(current, 'wat')

    def test_set_status_requires_the_file(self, tmp_path: Path) -> None:
        with pytest.raises(HandoffError, match=r'CURRENT\.md'):
            set_status(tmp_path / CURRENT_NAME, 'in-progress')

    def test_pop_marks_work_in_progress(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        current = path.with_name(CURRENT_NAME)
        pop_item(path, current)
        assert parse_status(current.read_text()) == 'in-progress'

    def test_pop_updates_an_existing_status(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        current = path.with_name(CURRENT_NAME)
        current.write_text('# Continue here\n\n**Status:** between-tasks\n')
        pop_item(path, current)
        assert parse_status(current.read_text()) == 'in-progress'


class TestParseAnchorCommit:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('HEAD `abc1234`', 'abc1234'),
            ('- 2026-08-22, branch `main`, HEAD `861deec`', '861deec'),
            (
                'HEAD `abcdef1234567890abcdef1234567890abcdef12`',
                'abcdef1234567890abcdef1234567890abcdef12',
            ),
            ('no anchor here', None),
            ('HEAD ``', None),
        ],
    )
    def test_parse_anchor_commit(
        self,
        text: str,
        expected: str | None,
    ) -> None:
        assert parse_anchor_commit(text) == expected


class TestReviewedInference:
    """awaiting-review downgrades to reviewed when HEAD advances."""

    def _make_git_project(self, root: Path, name: str) -> Path:
        import subprocess

        project = root / name
        project.mkdir(parents=True)
        subprocess.run(
            ['git', 'init', str(project)],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ['git', 'commit', '--allow-empty', '-m', 'initial'],
            cwd=project,
            capture_output=True,
            check=True,
        )
        return project

    def _head(self, project: Path) -> str:
        import subprocess

        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _branch_dir(self, project: Path) -> Path:
        import subprocess

        branch = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        directory = project / 'docs' / 'handoffs' / sanitize_branch(branch)
        directory.mkdir(parents=True)
        return directory

    def test_awaiting_review_becomes_reviewed_after_new_commit(
        self,
        tmp_path: Path,
    ) -> None:
        import subprocess

        project = self._make_git_project(tmp_path, 'myrepo')
        anchor = self._head(project)[:7]
        directory = self._branch_dir(project)
        (directory / CURRENT_NAME).write_text(
            f'# Continue here\n\n**Status:** awaiting-review\n\n'
            f'## Anchor\n\n- HEAD `{anchor}`\n',
        )
        subprocess.run(
            ['git', 'commit', '--allow-empty', '-m', 'user work'],
            cwd=project,
            capture_output=True,
            check=True,
        )
        (report,) = scan_projects([tmp_path])
        assert report.status == 'reviewed'

    def test_awaiting_review_stays_when_head_matches_anchor(
        self,
        tmp_path: Path,
    ) -> None:
        project = self._make_git_project(tmp_path, 'myrepo')
        anchor = self._head(project)[:7]
        directory = self._branch_dir(project)
        (directory / CURRENT_NAME).write_text(
            f'# Continue here\n\n**Status:** awaiting-review\n\n'
            f'## Anchor\n\n- HEAD `{anchor}`\n',
        )
        (report,) = scan_projects([tmp_path])
        assert report.status == 'awaiting-review'

    def test_awaiting_review_stays_without_anchor(
        self,
        tmp_path: Path,
    ) -> None:
        project = self._make_git_project(tmp_path, 'myrepo')
        directory = self._branch_dir(project)
        (directory / CURRENT_NAME).write_text(
            '# Continue here\n\n**Status:** awaiting-review\n',
        )
        (report,) = scan_projects([tmp_path])
        assert report.status == 'awaiting-review'


class TestProjectScan:
    """`handoff status` across every project under a root."""

    def make_project(
        self,
        root: Path,
        name: str,
        *,
        git: bool = True,
        branch: str = 'main',
        backlog: str | None = None,
        current: str | None = None,
    ) -> Path:
        project = root / name
        project.mkdir(parents=True)
        if git:
            (project / '.git').mkdir()
        if backlog is not None or current is not None:
            directory = project / 'docs' / 'handoffs' / branch
            directory.mkdir(parents=True)
            if backlog is not None:
                (directory / 'BACKLOG.md').write_text(backlog)
            if current is not None:
                (directory / CURRENT_NAME).write_text(current)
        return project

    def test_reports_a_project_with_no_handoff(self, tmp_path: Path) -> None:
        self.make_project(tmp_path, 'bare')
        (report,) = scan_projects([tmp_path])
        assert report.name == 'bare'
        assert report.has_handoff is False
        assert report.status == 'none'
        assert report.backlog_count == 0

    def test_skips_non_repositories(self, tmp_path: Path) -> None:
        self.make_project(tmp_path, 'notarepo', git=False)
        assert scan_projects([tmp_path]) == []

    def test_counts_backlog_items_and_reads_status(
        self,
        tmp_path: Path,
    ) -> None:
        self.make_project(
            tmp_path,
            'busy',
            backlog=SAMPLE,
            current='# Continue here\n\n**Status:** in-progress\n',
        )
        (report,) = scan_projects([tmp_path])
        assert report.has_handoff is True
        assert report.status == 'in-progress'
        assert report.backlog_count == len(parse_backlog_text(SAMPLE))

    def test_current_without_the_keyword_reports_unset(
        self,
        tmp_path: Path,
    ) -> None:
        self.make_project(tmp_path, 'legacy', current='# Continue here\n')
        (report,) = scan_projects([tmp_path])
        assert report.status == 'unset'

    def test_backlog_without_current_is_not_in_progress(
        self,
        tmp_path: Path,
    ) -> None:
        self.make_project(tmp_path, 'parked', backlog=SAMPLE)
        (report,) = scan_projects([tmp_path])
        assert report.has_handoff is False
        assert report.status == 'none'
        assert report.backlog_count == 0

    def test_sorted_by_name_across_roots(self, tmp_path: Path) -> None:
        first, second = tmp_path / 'a', tmp_path / 'b'
        self.make_project(second, 'zeta')
        self.make_project(first, 'alpha')
        assert [r.name for r in scan_projects([first, second])] == [
            'alpha',
            'zeta',
        ]

    def test_missing_root_is_not_an_error(self, tmp_path: Path) -> None:
        assert scan_projects([tmp_path / 'nope']) == []

    def test_multiple_branches_per_project(self, tmp_path: Path) -> None:
        project = self.make_project(
            tmp_path,
            'multi',
            branch='main',
            current='# Continue here\n\n**Status:** between-tasks\n',
        )
        feat_dir = project / 'docs' / 'handoffs' / 'feat-foo'
        feat_dir.mkdir(parents=True)
        (feat_dir / CURRENT_NAME).write_text(
            '# Continue here\n\n**Status:** in-progress\n',
        )
        (feat_dir / 'BACKLOG.md').write_text(SAMPLE)
        (report,) = scan_projects([tmp_path])
        assert report.has_handoff is True
        assert report.branches is not None
        assert len(report.branches) == 2


class TestStatusCommand:
    """The `status` action's own surface."""

    def test_table_lists_each_project(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        scan = TestProjectScan()
        scan.make_project(
            tmp_path,
            'busy',
            backlog=SAMPLE,
            current='# Continue here\n\n**Status:** in-progress\n',
        )
        scan.make_project(tmp_path, 'bare')
        assert main(['status', '--root', str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert 'busy' in out
        assert 'in-progress' in out
        assert 'bare' in out

    def test_json_is_machine_readable(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        scan = TestProjectScan()
        scan.make_project(
            tmp_path,
            'busy',
            backlog=SAMPLE,
            current='**Status:** in-progress\n',
        )
        assert main(['status', '--root', str(tmp_path), '--json']) == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 1
        report = payload[0]
        assert report['name'] == 'busy'
        assert report['has_handoff'] is True
        assert report['status'] == 'in-progress'
        assert report['backlog_count'] == 2
        assert len(report['branches']) == 1
        assert report['branches'][0]['branch'] == 'main'

    def test_empty_root_says_so(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main(['status', '--root', str(tmp_path)]) == 0
        assert 'No projects' in capsys.readouterr().out

    def test_set_writes_the_current_repo(
        self,
        handoff_env: Path,
    ) -> None:
        current = handoff_env / CURRENT_NAME
        current.write_text('# Continue here\n')
        assert main(['status', '--set', 'between-tasks']) == 0
        assert parse_status(current.read_text()) == 'between-tasks'


class TestClose:
    """The `close` command deletes a branch's handoff directory."""

    def test_close_deletes_the_directory(self, handoff_env: Path) -> None:
        (handoff_env / CURRENT_NAME).write_text('# Continue here\n')
        (handoff_env / 'BACKLOG.md').write_text(SAMPLE)
        assert main(['close', '--force']) == 0
        assert not handoff_env.exists()

    def test_close_cleans_up_empty_parent(
        self,
        handoff_env: Path,
    ) -> None:
        (handoff_env / CURRENT_NAME).write_text('# x\n')
        parent = handoff_env.parent
        assert main(['close', '--force']) == 0
        assert not parent.exists()

    def test_close_preserves_sibling_branches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        handoffs_root = tmp_path / 'docs' / 'handoffs'
        branch_a = handoffs_root / 'main'
        branch_b = handoffs_root / 'feat-foo'
        branch_a.mkdir(parents=True)
        branch_b.mkdir(parents=True)
        (branch_a / CURRENT_NAME).write_text('# x\n')
        (branch_b / CURRENT_NAME).write_text('# y\n')
        monkeypatch.setenv('HANDOFF_DIR', str(branch_a))
        assert main(['close', '--force']) == 0
        assert not branch_a.exists()
        assert branch_b.exists()
        assert handoffs_root.exists()

    def test_close_on_missing_directory_is_noop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nonexistent = tmp_path / 'docs' / 'handoffs' / 'gone'
        monkeypatch.setenv('HANDOFF_DIR', str(nonexistent))
        assert main(['close', '--force']) == 0

    def test_close_without_force_prints_reminder(
        self,
        handoff_env: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (handoff_env / CURRENT_NAME).write_text('# x\n')
        assert main(['close']) == 0
        assert 'CLAUDE.md' in capsys.readouterr().out
