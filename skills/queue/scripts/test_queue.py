"""Regression tests for scripts/queue_cli.py."""

import re
from datetime import datetime
from pathlib import Path

import pytest

from queue_cli import (
    IN_PROGRESS_MARKER,
    MAX_COMPLETED_CONTENT_LINES,
    action_claim,
    action_complete,
    action_edit,
    action_insert,
    action_list,
    action_merge_completed,
    action_merge_queue,
    action_tag,
    action_titles,
    completed_titles,
    current_repo_name,
    default_complete_path,
    default_queue_path,
    filter_items_for_repo,
    filter_untagged_items,
    list_titles,
    merge_completed_text,
    merge_queue_text,
    parse_queue_file,
    parse_queue_text,
    parse_repo_tag,
    remove_item_from_queue,
    trim_content,
)

TWO_ITEM_QUEUE = (
    '# Queue\n'
    '\n'
    '## First Item\n'
    '\n'
    'First body text.\n'
    '\n'
    '## Second Item\n'
    '\n'
    'Second body text.\n'
)


def _write_queue(tmp_path: Path, body: str) -> Path:
    queue_path = tmp_path / '.queue'
    queue_path.write_text(body)
    return queue_path


def test_remove_item_from_queue_drops_item_with_blank_line_before_body(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(
        tmp_path,
        '# Queue\n'
        '\n'
        '## First Item\n'
        '\n'
        'First body text.\n'
        '\n'
        '## Second Item\n'
        '\n'
        'Second body text.\n',
    )

    items = parse_queue_file(queue_path)
    first_item = next(item for item in items if item.title == 'First Item')

    remove_item_from_queue(queue_path, first_item)

    remaining = parse_queue_file(queue_path)
    remaining_titles = [item.title for item in remaining]

    assert remaining_titles == ['Second Item']


def test_action_complete_removes_item_from_active_queue(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(
        tmp_path,
        '# Queue\n'
        '\n'
        '## First Item\n'
        '\n'
        'First body text.\n'
        '\n'
        '## Second Item\n'
        '\n'
        'Second body text.\n',
    )
    complete_path = tmp_path / '.queue-complete'

    action_complete(
        queue_path,
        complete_path,
        'First Item',
        '2026-01-01T01:00:00',
    )

    remaining = parse_queue_file(queue_path)
    remaining_titles = [item.title for item in remaining]

    assert remaining_titles == ['Second Item']
    assert 'First Item' in complete_path.read_text()


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        (TWO_ITEM_QUEUE, ['First Item', 'Second Item']),
        ('# Queue\n', []),
        ('# Queue\n\n## Only One\n\nbody\n', ['Only One']),
    ],
)
def test_list_titles_returns_one_title_per_item(
    tmp_path: Path,
    body: str,
    expected: list[str],
) -> None:
    assert list_titles(_write_queue(tmp_path, body)) == expected


def test_list_titles_preserves_titles_containing_markup(
    tmp_path: Path,
) -> None:
    """fzf matches on the exact string queue_cli.py later looks up."""
    body = '# Queue\n\n## Add `.queue` to pass -- now\n\nbody\n'

    assert list_titles(_write_queue(tmp_path, body)) == [
        'Add `.queue` to pass -- now',
    ]


@pytest.mark.parametrize(
    'end_time',
    [None, '2026-01-01T01:00:00'],
)
def test_action_complete_defaults_missing_end_time_to_now(
    tmp_path: Path,
    end_time: str | None,
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)
    complete_path = tmp_path / '.queue-complete'
    before = datetime.now().replace(microsecond=0)

    action_complete(
        queue_path,
        complete_path,
        'First Item',
        end_time,
    )

    written = complete_path.read_text()
    stamps = re.findall(r'- Completed: (.+)', written)
    assert len(stamps) == 1

    parsed = datetime.fromisoformat(stamps[0])
    if end_time is None:
        assert parsed >= before
    else:
        assert parsed == datetime.fromisoformat(end_time)

    assert [item.title for item in parse_queue_file(queue_path)] == [
        'Second Item',
    ]


def test_action_complete_does_not_write_started_timestamp(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)
    complete_path = tmp_path / '.queue-complete'

    action_complete(queue_path, complete_path, 'First Item')

    assert 'Started' not in complete_path.read_text()


def test_parse_queue_file_detects_in_progress_marker(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(
        tmp_path,
        f'# Queue\n\n## First Item{IN_PROGRESS_MARKER}\n\nbody\n',
    )

    items = parse_queue_file(queue_path)

    assert items[0].title == f'First Item{IN_PROGRESS_MARKER}'
    assert items[0].in_progress is True


def test_parse_queue_file_treats_unmarked_item_as_not_in_progress(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)

    items = parse_queue_file(queue_path)

    assert all(not item.in_progress for item in items)


def test_action_claim_adds_marker_to_queue_file(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)

    action_claim(queue_path, 'First Item')

    items = parse_queue_file(queue_path)
    first = next(item for item in items if 'First Item' in item.title)
    second = next(item for item in items if item.title == 'Second Item')

    assert first.in_progress is True
    assert second.in_progress is False


def test_action_claim_errors_when_item_not_found(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)

    with pytest.raises(SystemExit) as exc_info:
        action_claim(queue_path, 'Nonexistent Item')

    assert exc_info.value.code == 1
    assert 'not found' in capsys.readouterr().err


def test_action_claim_errors_when_item_already_in_progress(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)
    action_claim(queue_path, 'First Item')

    with pytest.raises(SystemExit) as exc_info:
        action_claim(queue_path, 'First Item')

    assert exc_info.value.code == 1
    assert 'already in progress' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('line_count', 'expect_trimmed'),
    [
        (50, False),
        (51, True),
        (1500, True),
    ],
)
def test_trim_content_only_trims_over_max_lines(
    line_count: int,
    *,
    expect_trimmed: bool,
) -> None:
    content = '\n'.join(f'line {n}' for n in range(line_count))

    result = trim_content(content)

    if expect_trimmed:
        max_lines = MAX_COMPLETED_CONTENT_LINES
        assert len(result.split('\n')) > max_lines
        assert f'Trimmed from {line_count} to {max_lines}' in result
        assert 'line 0' in result
        assert f'line {line_count - 1}' not in result
    else:
        assert result == content


def test_action_complete_trims_oversized_content_in_complete_file(
    tmp_path: Path,
) -> None:
    huge_body = '\n'.join(f'line {n}' for n in range(1500))
    queue_path = _write_queue(
        tmp_path,
        f'# Queue\n\n## Huge Item\n\n{huge_body}\n',
    )
    complete_path = tmp_path / '.queue-complete'

    action_complete(queue_path, complete_path, 'Huge Item')

    completed = complete_path.read_text()
    assert 'Trimmed from 1500 to 50 lines' in completed
    assert 'line 1499' not in completed


def test_action_complete_does_not_trim_short_content(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)
    complete_path = tmp_path / '.queue-complete'

    action_complete(queue_path, complete_path, 'First Item')

    completed = complete_path.read_text()
    assert 'Trimmed' not in completed
    assert 'First body text.' in completed


def test_action_complete_matches_item_regardless_of_marker(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, TWO_ITEM_QUEUE)
    complete_path = tmp_path / '.queue-complete'
    action_claim(queue_path, 'First Item')

    action_complete(queue_path, complete_path, 'First Item')

    remaining_titles = [item.title for item in parse_queue_file(queue_path)]
    assert remaining_titles == ['Second Item']
    completed = complete_path.read_text()
    assert 'First Item' in completed
    assert IN_PROGRESS_MARKER not in completed


def _queue(*titles: str) -> str:
    sections = ''.join(f'## {t}\n\n{t} body.\n\n' for t in titles)
    return f'# Queue\n\n{sections}'


def _titles(queue_text: str) -> list[str]:
    return [item.title for item in parse_queue_text(queue_text)]


def _completed(*pairs: tuple[str, str]) -> str:
    entries = ''.join(
        f'## {title}\n- Completed: {stamp}\n\n{title} body.\n\n---\n\n'
        for title, stamp in pairs
    )
    return f'# Completed\n\n{entries}'


def test_merge_queue_text_keeps_items_added_on_the_other_machine(
    tmp_path: Path,
) -> None:
    """The reported bug: a pull replaced .queue instead of merging it."""
    queue_path = _write_queue(tmp_path, _queue('Local Only'))
    complete_path = tmp_path / '.queue-complete'
    incoming_path = tmp_path / 'incoming'
    incoming_path.write_text(_queue('Remote Only'))

    action_merge_queue(queue_path, complete_path, incoming_path, 'incoming')

    assert _titles(queue_path.read_text()) == ['Local Only', 'Remote Only']


@pytest.mark.parametrize('prefer', ['local', 'incoming'])
def test_merge_queue_text_unions_both_sides(prefer: str) -> None:
    merged = merge_queue_text(
        _queue('Shared', 'Local Only'),
        _queue('Shared', 'Remote Only'),
        tombstones=set(),
        prefer=prefer,
    )

    assert sorted(_titles(merged)) == [
        'Local Only',
        'Remote Only',
        'Shared',
    ]


def test_merge_queue_text_drops_titles_completed_on_the_other_machine() -> (
    None
):
    merged = merge_queue_text(
        _queue('Still Open', 'Done Elsewhere'),
        _queue('Still Open', 'Done Elsewhere'),
        tombstones={'Done Elsewhere'},
        prefer='local',
    )

    assert _titles(merged) == ['Still Open']


def test_merge_queue_text_tombstone_matches_an_in_progress_title() -> None:
    merged = merge_queue_text(
        _queue(f'Done Elsewhere{IN_PROGRESS_MARKER}'),
        '# Queue\n',
        tombstones={'Done Elsewhere'},
        prefer='local',
    )

    assert _titles(merged) == []


@pytest.mark.parametrize(
    ('prefer', 'expected'),
    [
        ('local', ['B', 'A']),
        ('incoming', ['A', 'B']),
    ],
)
def test_merge_queue_text_orders_shared_items_by_preferred_side(
    prefer: str,
    expected: list[str],
) -> None:
    merged = merge_queue_text(
        _queue('B', 'A'),
        _queue('A', 'B'),
        tombstones=set(),
        prefer=prefer,
    )

    assert _titles(merged) == expected


def test_merge_queue_text_sorts_side_exclusive_items_for_convergence() -> None:
    """Without a shared anchor, both machines must agree on the order."""
    from_local = merge_queue_text(
        _queue('Zebra'),
        _queue('Apple'),
        tombstones=set(),
        prefer='local',
    )
    from_remote = merge_queue_text(
        _queue('Apple'),
        _queue('Zebra'),
        tombstones=set(),
        prefer='local',
    )

    assert _titles(from_local) == ['Apple', 'Zebra']
    assert from_local == from_remote


def test_merge_queue_text_converges_after_concurrent_adds() -> None:
    """A save then a load on the other machine must reach a fixed point."""
    store = merge_queue_text(
        _queue('Shared', 'Added Here'),
        _queue('Shared'),
        tombstones=set(),
        prefer='local',
    )
    other = merge_queue_text(
        _queue('Shared', 'Added There'),
        store,
        tombstones=set(),
        prefer='incoming',
    )
    store_after_other_saves = merge_queue_text(
        other,
        store,
        tombstones=set(),
        prefer='local',
    )
    back_home = merge_queue_text(
        store,
        store_after_other_saves,
        tombstones=set(),
        prefer='incoming',
    )

    assert back_home == store_after_other_saves
    assert sorted(_titles(back_home)) == [
        'Added Here',
        'Added There',
        'Shared',
    ]


@pytest.mark.parametrize('prefer', ['local', 'incoming'])
def test_merge_queue_text_keeps_in_progress_claimed_on_either_side(
    prefer: str,
) -> None:
    merged = merge_queue_text(
        _queue(f'Taken{IN_PROGRESS_MARKER}'),
        _queue('Taken'),
        tombstones=set(),
        prefer=prefer,
    )

    assert _titles(merged) == [f'Taken{IN_PROGRESS_MARKER}']


@pytest.mark.parametrize(
    ('prefer', 'expected'),
    [
        ('local', 'local body'),
        ('incoming', 'incoming body'),
    ],
)
def test_merge_queue_text_resolves_body_conflict_to_preferred_side(
    prefer: str,
    expected: str,
) -> None:
    merged = merge_queue_text(
        '# Queue\n\n## Same\n\nlocal body\n',
        '# Queue\n\n## Same\n\nincoming body\n',
        tombstones=set(),
        prefer=prefer,
    )

    assert parse_queue_text(merged)[0].content == expected


def test_merge_queue_text_drops_a_stray_empty_header() -> None:
    merged = merge_queue_text(
        '# Queue\n\n## Real Item\n\nbody\n\n## \n\n',
        '# Queue\n',
        tombstones=set(),
        prefer='local',
    )

    assert _titles(merged) == ['Real Item']


def test_merge_queue_text_keeps_a_titleless_item_that_has_a_body() -> None:
    """Dropping it would silently lose whatever was written under it."""
    merged = merge_queue_text(
        '# Queue\n\n## \n\nnotes with no header\n',
        '# Queue\n',
        tombstones=set(),
        prefer='local',
    )

    assert parse_queue_text(merged)[0].content == 'notes with no header'


def test_merge_queue_text_handles_an_empty_side() -> None:
    merged = merge_queue_text(
        _queue('Only Item'),
        '',
        tombstones=set(),
        prefer='local',
    )

    assert _titles(merged) == ['Only Item']


def test_merge_completed_text_unions_records_from_both_machines() -> None:
    merged = merge_completed_text(
        _completed(('Here', '2026-01-02 03:04:05')),
        _completed(('There', '2026-01-01 01:00:00')),
    )

    assert _titles(merged) == ['There', 'Here']


def test_merge_completed_text_dedupes_the_same_record() -> None:
    same = _completed(('Done', '2026-01-01 01:00:00'))

    merged = merge_completed_text(same, same)

    assert _titles(merged) == ['Done']


def test_merge_completed_text_keeps_reruns_of_the_same_title() -> None:
    merged = merge_completed_text(
        _completed(('Done', '2026-01-01 01:00:00')),
        _completed(('Done', '2026-02-02 02:00:00')),
    )

    assert _titles(merged) == ['Done', 'Done']


def test_merge_completed_text_is_order_independent() -> None:
    here = _completed(('Here', '2026-01-02 03:04:05'))
    there = _completed(('There', '2026-01-01 01:00:00'))

    assert merge_completed_text(here, there) == merge_completed_text(
        there,
        here,
    )


def test_completed_titles_strips_the_in_progress_marker(
    tmp_path: Path,
) -> None:
    complete_path = tmp_path / '.queue-complete'
    complete_path.write_text(
        _completed((f'Done{IN_PROGRESS_MARKER}', '2026-01-01 01:00:00')),
    )

    assert completed_titles(complete_path) == {'Done'}


def test_completed_titles_is_empty_when_the_file_is_missing(
    tmp_path: Path,
) -> None:
    assert completed_titles(tmp_path / 'nope') == set()


def test_action_merge_completed_writes_the_union_to_disk(
    tmp_path: Path,
) -> None:
    complete_path = tmp_path / '.queue-complete'
    complete_path.write_text(_completed(('Here', '2026-01-02 03:04:05')))
    incoming_path = tmp_path / 'incoming'
    incoming_path.write_text(_completed(('There', '2026-01-01 01:00:00')))

    action_merge_completed(complete_path, incoming_path)

    assert _titles(complete_path.read_text()) == ['There', 'Here']


def test_action_merge_queue_output_stays_parseable_by_the_cli(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, _queue('Keep Me'))
    complete_path = tmp_path / '.queue-complete'
    incoming_path = tmp_path / 'incoming'
    incoming_path.write_text(_queue('New From Remote'))

    action_merge_queue(queue_path, complete_path, incoming_path, 'local')
    action_claim(queue_path, 'New From Remote')
    action_complete(queue_path, complete_path, 'New From Remote')

    assert list_titles(queue_path) == ['Keep Me']
    assert 'New From Remote' in complete_path.read_text()


def test_action_merge_queue_drops_items_completed_on_the_other_machine(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, _queue('Open', 'Done There'))
    complete_path = tmp_path / '.queue-complete'
    complete_path.write_text(_completed(('Done There', '2026-01-01 01:00:00')))
    incoming_path = tmp_path / 'incoming'
    incoming_path.write_text(_queue('Open'))

    action_merge_queue(queue_path, complete_path, incoming_path, 'incoming')

    assert list_titles(queue_path) == ['Open']


def test_action_edit_opens_editor_on_the_queue_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_path = _write_queue(tmp_path, _queue('Existing'))
    monkeypatch.setenv('EDITOR', 'my-editor')
    calls = []
    monkeypatch.setattr(
        'queue_cli.subprocess.run',
        lambda args, **kwargs: calls.append((args, kwargs)),
    )

    action_edit(queue_path)

    assert calls == [(['my-editor', str(queue_path)], {'check': True})]


def test_action_insert_adds_item_to_empty_queue(tmp_path: Path) -> None:
    queue_path = _write_queue(tmp_path, '# Queue\n')

    action_insert(queue_path, 'New Item', '')

    assert list_titles(queue_path) == ['New Item']


def test_action_insert_places_new_item_at_top(tmp_path: Path) -> None:
    queue_path = _write_queue(tmp_path, _queue('First', 'Second'))

    action_insert(queue_path, 'New Top Item', '')

    assert list_titles(queue_path) == ['New Top Item', 'First', 'Second']


def test_action_insert_includes_content(tmp_path: Path) -> None:
    queue_path = _write_queue(tmp_path, _queue('Existing'))

    action_insert(queue_path, 'New Item', 'Item description here.')

    items = parse_queue_file(queue_path)
    new_item = next(item for item in items if item.title == 'New Item')
    assert new_item.content == 'Item description here.'


def test_action_insert_with_empty_content_creates_item_with_no_body(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, _queue('Existing'))

    action_insert(queue_path, 'New Item', '')

    items = parse_queue_file(queue_path)
    new_item = next(item for item in items if item.title == 'New Item')
    assert new_item.content == ''


@pytest.mark.parametrize(
    ('title', 'expected'),
    [
        ('[dotfiles] Make queue global', ('dotfiles', 'Make queue global')),
        ('Read that article', (None, 'Read that article')),
        ('[gtd] Fix sync', ('gtd', 'Fix sync')),
        ('[dotfiles]No space', ('dotfiles', 'No space')),
        ('Prose [with] brackets', (None, 'Prose [with] brackets')),
        ('[unclosed Fix it', (None, '[unclosed Fix it')),
        ('[] Empty tag', (None, '[] Empty tag')),
    ],
)
def test_parse_repo_tag_splits_only_a_leading_bracketed_tag(
    title: str,
    expected: tuple[str | None, str],
) -> None:
    assert parse_repo_tag(title) == expected


def test_repo_tag_survives_the_in_progress_marker() -> None:
    item = parse_queue_text(
        f'# Queue\n\n## [dotfiles] Taken{IN_PROGRESS_MARKER}\n\nbody\n',
    )[0]

    assert item.repo == 'dotfiles'
    assert item.in_progress


@pytest.mark.parametrize(
    ('repo', 'expected_visible', 'expected_hidden'),
    [
        ('dotfiles', ['[dotfiles] Tagged Here', 'Untagged'], 1),
        ('gtd', ['Untagged', '[gtd] Tagged There'], 1),
        ('sankey', ['Untagged'], 2),
        (
            None,
            ['[dotfiles] Tagged Here', 'Untagged', '[gtd] Tagged There'],
            0,
        ),
    ],
)
def test_filter_items_for_repo_keeps_untagged_items_visible_everywhere(
    repo: str | None,
    expected_visible: list[str],
    expected_hidden: int,
) -> None:
    items = parse_queue_text(
        _queue('[dotfiles] Tagged Here', 'Untagged', '[gtd] Tagged There'),
    )

    visible, hidden = filter_items_for_repo(items, repo)

    assert [item.title for item in visible] == expected_visible
    assert hidden == expected_hidden


@pytest.mark.parametrize('repo', ['DOTFILES', 'Dotfiles', 'dotfiles'])
def test_filter_items_for_repo_matches_case_insensitively(repo: str) -> None:
    items = parse_queue_text(_queue('[dotfiles] Tagged Here'))

    visible, hidden = filter_items_for_repo(items, repo)

    assert len(visible) == 1
    assert hidden == 0


def test_filter_untagged_items_keeps_only_items_without_a_repo_tag() -> None:
    items = parse_queue_text(
        _queue('[dotfiles] Tagged Here', 'Untagged', '[gtd] Tagged There'),
    )

    visible, hidden = filter_untagged_items(items)
    expected_hidden = 2

    assert [item.title for item in visible] == ['Untagged']
    assert hidden == expected_hidden


def test_filter_untagged_items_hides_nothing_when_all_are_untagged() -> None:
    items = parse_queue_text(_queue('First', 'Second'))

    visible, hidden = filter_untagged_items(items)

    assert [item.title for item in visible] == ['First', 'Second']
    assert hidden == 0


def test_current_repo_name_walks_up_to_the_repo_root(tmp_path: Path) -> None:
    (tmp_path / 'myrepo' / '.git').mkdir(parents=True)
    nested = tmp_path / 'myrepo' / 'src' / 'deep'
    nested.mkdir(parents=True)

    assert current_repo_name(nested) == 'myrepo'


def test_current_repo_name_is_none_outside_a_repo(tmp_path: Path) -> None:
    assert current_repo_name(tmp_path) is None


def test_current_repo_name_reports_the_main_repo_from_a_worktree(
    tmp_path: Path,
) -> None:
    """A worktree dir is named for the branch, not the repo the tags use."""
    main_repo = tmp_path / 'dotfiles'
    (main_repo / '.git' / 'worktrees' / 'feature-x').mkdir(parents=True)
    worktree = tmp_path / 'dotfiles-worktrees' / 'feature-x'
    worktree.mkdir(parents=True)
    (worktree / '.git').write_text(
        f'gitdir: {main_repo}/.git/worktrees/feature-x\n',
    )

    assert current_repo_name(worktree) == 'dotfiles'


def test_default_paths_follow_the_queue_home_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('QUEUE_HOME', str(tmp_path))

    assert default_queue_path() == tmp_path / 'queue'
    assert default_complete_path() == tmp_path / 'queue-complete'


def test_default_paths_land_in_the_claude_dir_without_an_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('QUEUE_HOME', raising=False)

    assert default_queue_path() == Path.home() / '.claude/queue/queue'
    assert default_complete_path() == (
        Path.home() / '.claude/queue/queue-complete'
    )


def test_action_titles_prints_only_titles_on_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stdout feeds fzf, so a hidden-count note there would be selectable."""
    queue_path = _write_queue(
        tmp_path,
        _queue('[dotfiles] Here', 'Untagged', '[gtd] Elsewhere'),
    )

    action_titles(queue_path, 'dotfiles')

    captured = capsys.readouterr()
    assert captured.out.split('\n')[:-1] == ['[dotfiles] Here', 'Untagged']
    assert '1' in captured.err


def test_action_titles_untagged_only_hides_already_tagged_items(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The tag picker's default view -- don't offer already-tagged items."""
    queue_path = _write_queue(
        tmp_path,
        _queue('[dotfiles] Here', 'Untagged', '[gtd] Elsewhere'),
    )

    action_titles(queue_path, untagged_only=True)

    captured = capsys.readouterr()
    assert captured.out.split('\n')[:-1] == ['Untagged']
    assert 'already tagged' in captured.err
    assert '--all' in captured.err


def test_action_titles_untagged_only_ignores_repo_scoping(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Untagged-only is a different filter dimension than repo scoping."""
    queue_path = _write_queue(
        tmp_path,
        _queue('[dotfiles] Here', 'Untagged'),
    )

    action_titles(queue_path, repo='gtd', untagged_only=True)

    assert capsys.readouterr().out.split('\n')[:-1] == ['Untagged']


def test_action_list_reports_how_many_items_are_hidden(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    queue_path = _write_queue(
        tmp_path,
        _queue('[dotfiles] Here', 'Untagged', '[gtd] Elsewhere'),
    )

    action_list(queue_path, 'dotfiles')

    out = capsys.readouterr().out
    assert '[gtd] Elsewhere' not in out
    assert '1 hidden' in out
    assert '--all' in out


def test_action_list_says_nothing_about_hiding_when_nothing_is_hidden(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    queue_path = _write_queue(tmp_path, _queue('[dotfiles] Here', 'Untagged'))

    action_list(queue_path, 'dotfiles')

    assert 'hidden' not in capsys.readouterr().out


def test_action_claim_reaches_an_item_tagged_for_another_repo(
    tmp_path: Path,
) -> None:
    """Lookup is never repo-filtered -- only what gets listed is."""
    queue_path = _write_queue(tmp_path, _queue('[gtd] Elsewhere'))

    action_claim(queue_path, '[gtd] Elsewhere')

    assert IN_PROGRESS_MARKER in queue_path.read_text()


def test_action_complete_reaches_an_item_tagged_for_another_repo(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, _queue('[gtd] Elsewhere'))
    complete_path = tmp_path / 'queue-complete'

    action_complete(queue_path, complete_path, '[gtd] Elsewhere', None)

    assert parse_queue_file(queue_path) == []
    assert '[gtd] Elsewhere' in complete_path.read_text()


def test_action_tag_adds_a_tag_to_an_untagged_item(tmp_path: Path) -> None:
    queue_path = _write_queue(tmp_path, _queue('Untagged Item'))

    action_tag(queue_path, 'Untagged Item', 'dotfiles')

    items = parse_queue_file(queue_path)
    assert items[0].title == '[dotfiles] Untagged Item'
    assert items[0].repo == 'dotfiles'


def test_action_tag_replaces_an_existing_tag(tmp_path: Path) -> None:
    queue_path = _write_queue(tmp_path, _queue('[gtd] Fix rollup'))

    action_tag(queue_path, '[gtd] Fix rollup', 'dotfiles')

    items = parse_queue_file(queue_path)
    assert items[0].title == '[dotfiles] Fix rollup'


def test_action_tag_with_no_repo_removes_the_tag(tmp_path: Path) -> None:
    queue_path = _write_queue(tmp_path, _queue('[gtd] Fix rollup'))

    action_tag(queue_path, '[gtd] Fix rollup', None)

    items = parse_queue_file(queue_path)
    assert items[0].title == 'Fix rollup'
    assert items[0].repo is None


def test_action_tag_preserves_the_in_progress_marker(tmp_path: Path) -> None:
    queue_path = _write_queue(
        tmp_path,
        f'# Queue\n\n## [gtd] Taken{IN_PROGRESS_MARKER}\n\nbody\n',
    )

    action_tag(queue_path, '[gtd] Taken', 'dotfiles')

    items = parse_queue_file(queue_path)
    assert items[0].title == f'[dotfiles] Taken{IN_PROGRESS_MARKER}'
    assert items[0].in_progress


def test_action_tag_matches_item_regardless_of_marker(tmp_path: Path) -> None:
    queue_path = _write_queue(
        tmp_path,
        f'# Queue\n\n## Untagged{IN_PROGRESS_MARKER}\n\nbody\n',
    )

    action_tag(queue_path, 'Untagged', 'dotfiles')

    items = parse_queue_file(queue_path)
    assert items[0].title == f'[dotfiles] Untagged{IN_PROGRESS_MARKER}'


def test_action_tag_leaves_body_and_other_items_untouched(
    tmp_path: Path,
) -> None:
    queue_path = _write_queue(tmp_path, _queue('First', 'Second'))

    action_tag(queue_path, 'First', 'dotfiles')

    items = parse_queue_file(queue_path)
    tagged = next(item for item in items if 'First' in item.title)
    other = next(item for item in items if item.title == 'Second')
    assert tagged.content == 'First body.'
    assert other.title == 'Second'


def test_action_tag_errors_when_item_not_found(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    queue_path = _write_queue(tmp_path, _queue('Existing'))

    with pytest.raises(SystemExit) as exc_info:
        action_tag(queue_path, 'Nonexistent', 'dotfiles')

    assert exc_info.value.code == 1
    assert 'not found' in capsys.readouterr().err


def test_a_completed_tagged_item_stays_completed_through_a_merge(
    tmp_path: Path,
) -> None:
    """The tag is part of the title, so it must match the tombstone too."""
    complete_path = tmp_path / 'queue-complete'
    complete_path.write_text(
        _completed(('[gtd] Done Elsewhere', '2026-01-01 01:00:00')),
    )

    merged = merge_queue_text(
        _queue('[gtd] Done Elsewhere', 'Still Open'),
        _queue('[gtd] Done Elsewhere'),
        tombstones=completed_titles(complete_path),
        prefer='local',
    )

    assert _titles(merged) == ['Still Open']
