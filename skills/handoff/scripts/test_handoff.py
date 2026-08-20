"""Tests for the handoff backlog CLI."""

from pathlib import Path

import pytest

from handoff_cli import (
    BacklogItem,
    HandoffError,
    add_item,
    find_item,
    handoff_dir,
    main,
    parse_backlog_text,
    pop_item,
    read_items,
    remove_item,
    render_backlog,
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
    directory.mkdir(parents=True)
    path = directory / 'BACKLOG.md'
    path.write_text(content)
    return path


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
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_backlog(tmp_path)
        assert main(['pop', '--repo', str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert 'Wire the flag' in out
        assert 'cli.py:88' in out

    def test_cli_pop_on_empty_backlog_is_quiet_and_succeeds(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The hook calls this constantly -- nothing queued isn't an error."""
        write_backlog(tmp_path, '# Backlog\n')
        assert main(['pop', '--repo', str(tmp_path)]) == 0
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


class TestHandoffDir:
    def test_walks_up_to_the_git_root(self, tmp_path: Path) -> None:
        (tmp_path / '.git').mkdir()
        nested = tmp_path / 'src' / 'deep'
        nested.mkdir(parents=True)
        assert handoff_dir(start=nested) == tmp_path / 'docs' / 'handoffs'

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


class TestCli:
    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        """argparse prints and exits 0 -- the contract is the exit code."""
        with pytest.raises(SystemExit) as exit_info:
            main(['--version'])
        assert exit_info.value.code == 0
        assert capsys.readouterr().out.startswith('handoff ')

    def test_list(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_backlog(tmp_path)
        assert main(['list', '--repo', str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert 'Wire the flag' in out
        assert 'Drop the shim' in out

    def test_titles_are_bare(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_backlog(tmp_path)
        assert main(['titles', '--repo', str(tmp_path)]) == 0
        assert capsys.readouterr().out.split('\n')[:2] == [
            'Wire the flag',
            'Drop the shim',
        ]

    def test_list_empty_backlog_is_not_an_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_backlog(tmp_path, '# Backlog\n')
        assert main(['list', '--repo', str(tmp_path)]) == 0
        assert 'empty' in capsys.readouterr().out.casefold()

    def test_add(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        code = main(
            ['add', '--repo', str(tmp_path), '--title', 'New', '--body', 'b'],
        )
        assert code == 0
        assert read_items(path)[-1].title == 'New'

    def test_next_adds_to_top(self, tmp_path: Path) -> None:
        path = write_backlog(tmp_path)
        main(
            ['next', '--repo', str(tmp_path), '--title', 'Now', '--body', 'b'],
        )
        assert read_items(path)[0].title == 'Now'

    def test_show(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_backlog(tmp_path)
        code = main(
            ['show', '--repo', str(tmp_path), '--item-title', 'Drop the shim'],
        )
        assert code == 0
        assert 'no callers left' in capsys.readouterr().out

    def test_remove_without_a_title_lists_and_fails(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_backlog(tmp_path)
        assert main(['remove', '--repo', str(tmp_path)]) == 1
        assert 'Wire the flag' in capsys.readouterr().err

    def test_unknown_title_exits_one(self, tmp_path: Path) -> None:
        write_backlog(tmp_path)
        code = main(
            ['remove', '--repo', str(tmp_path), '--item-title', 'nope'],
        )
        assert code == 1
