"""Regression tests for the interactive `scripts/backlog` wrapper.

The wrapper is pure shell glue around fzf, so it's driven end to end here
with a fake `fzf` (and `$EDITOR`) earlier on `PATH` than the real ones. The
fake logs every invocation to stderr, which is what lets ordering -- e.g.
"title is asked for before the repo picker opens" -- be asserted at all.
"""

import os
import subprocess
from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent / 'backlog'

FAKE_FZF = """#!/usr/bin/env bash
# Consume stdin so the producing side never sees EPIPE, log the call, then
# emit the next queued response. `_backlog_pick_or_type` reads a query line
# and a choice line; a lone line is read back as the query, which it falls
# back to, so one line per response works for both picker styles.
cat >/dev/null
echo "FZF-RAN $*" >&2
responses="${FAKE_FZF_RESPONSES}"
index_file="${FAKE_FZF_INDEX}"
index="$(cat "${index_file}" 2>/dev/null || echo 1)"
echo "$((index + 1))" >"${index_file}"
sed -n "${index}p" "${responses}"
"""

FAKE_FZF_ECHO_INPUT = """#!/usr/bin/env bash
# Records what the picker was offered, then selects the requested line.
tee -a "${FAKE_FZF_INPUT_LOG}" >/dev/null
sed -n "${FAKE_FZF_PICK_LINE:-1}p" "${FAKE_FZF_INPUT_LOG}"
"""


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A PATH with fake fzf/editor, pointed at a scratch backlog."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()

    fzf = bin_dir / 'fzf'
    fzf.write_text(FAKE_FZF)
    fzf.chmod(0o755)

    editor = bin_dir / 'fake-editor'
    editor.write_text('#!/usr/bin/env bash\necho "EDITOR-RAN" >&2\n')
    editor.chmod(0o755)

    responses = tmp_path / 'responses'
    responses.write_text('')

    backlog_home = tmp_path / 'backlog-home'
    backlog_home.mkdir()

    return {
        **os.environ,
        'PATH': f'{bin_dir}:{os.environ["PATH"]}',
        'EDITOR': str(editor),
        'BACKLOG_HOME': str(backlog_home),
        'FAKE_FZF_RESPONSES': str(responses),
        'FAKE_FZF_INDEX': str(tmp_path / 'fzf-index'),
        'FAKE_FZF_INPUT_LOG': str(tmp_path / 'fzf-input'),
    }


def _queue_fzf(env: dict[str, str], *responses: str) -> None:
    Path(env['FAKE_FZF_RESPONSES']).write_text(
        ''.join(f'{line}\n' for line in responses),
    )


def _run(
    env: dict[str, str],
    *args: str,
    stdin: str = '',
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(WRAPPER), *args],
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _backlog_text(env: dict[str, str]) -> str:
    return (Path(env['BACKLOG_HOME']) / 'backlog').read_text()


def _wrapper_argv(tmp_path: Path, *args: str) -> list[str]:
    """Run the wrapper with `uv`/`fzf` stubbed, returning the uv argv.

    For the cases that are only about which action the wrapper *dispatches*,
    where actually touching a backlog file would be beside the point.
    """
    bin_dir = tmp_path / 'argv-bin'
    bin_dir.mkdir()
    argv_log = tmp_path / 'uv-argv'
    (bin_dir / 'uv').write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" >> "{argv_log}"\n',
    )
    (bin_dir / 'fzf').write_text('#!/usr/bin/env bash\nexit 0\n')
    for stub in ('uv', 'fzf'):
        (bin_dir / stub).chmod(0o755)

    env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
    subprocess.run([str(WRAPPER), *args], env=env, check=True)  # noqa: S603

    return argv_log.read_text().splitlines()


def test_wrapper_passes_an_explicit_action_through(tmp_path: Path) -> None:
    assert 'queue' not in _wrapper_argv(tmp_path, 'list')


def test_wrapper_leaves_help_alone(tmp_path: Path) -> None:
    assert 'queue' not in _wrapper_argv(tmp_path, '--help')


def test_bare_backlog_offers_every_action_in_the_picker(
    env: dict[str, str],
) -> None:
    fzf = Path(env['PATH'].split(':')[0]) / 'fzf'
    fzf.write_text(FAKE_FZF_ECHO_INPUT)
    env['FAKE_FZF_PICK_LINE'] = '3'

    _run(env)
    offered = Path(env['FAKE_FZF_INPUT_LOG']).read_text()

    actions = {line.split()[0] for line in offered.splitlines() if line}
    assert actions == {
        'queue',
        'stack',
        'list',
        'next',
        'claim',
        'complete',
        'tag',
        'edit',
    }


def test_bare_backlog_runs_the_picked_action(env: dict[str, str]) -> None:
    _queue_fzf(env, 'list  Preview the next items')

    result = _run(env)

    assert result.returncode == 0
    assert 'Backlog is empty' in result.stdout


def test_bare_backlog_no_longer_silently_queues(env: dict[str, str]) -> None:
    """The old behavior: bare `backlog` jumped straight into a new item."""
    _queue_fzf(env, 'list  Preview the next items')

    result = _run(env)

    assert 'EDITOR-RAN' not in result.stderr


def test_bare_backlog_exits_when_nothing_is_picked(
    env: dict[str, str],
) -> None:
    _queue_fzf(env, '')

    result = _run(env)

    assert result.returncode == 1
    assert 'nothing selected' in result.stderr


def test_leading_flag_still_means_queue(env: dict[str, str]) -> None:
    _queue_fzf(env, '')  # repo picker: blank means untagged

    result = _run(env, '--title', 'Flagged Item', '--content', 'Body.')

    assert result.returncode == 0
    assert '## Flagged Item' in _backlog_text(env)


@pytest.mark.parametrize('action', ['stack', 'queue'])
def test_new_item_asks_for_title_before_the_repo_picker(
    env: dict[str, str],
    action: str,
) -> None:
    _queue_fzf(env, 'skill-tree')

    result = _run(env, action, '--content', 'Body.', stdin='My New Item\n')
    stderr = result.stderr

    assert result.returncode == 0
    assert '## [skill-tree] My New Item' in _backlog_text(env)
    assert stderr.index('Item title:') < stderr.index('FZF-RAN')


@pytest.mark.parametrize('action', ['stack', 'queue'])
def test_new_item_skips_the_title_prompt_when_given_one(
    env: dict[str, str],
    action: str,
) -> None:
    _queue_fzf(env, 'skill-tree')

    result = _run(env, action, '--title', 'Given', '--content', 'Body.')

    assert result.returncode == 0
    assert 'Item title:' not in result.stderr
    assert '## [skill-tree] Given' in _backlog_text(env)


@pytest.mark.parametrize('action', ['stack', 'queue'])
def test_new_item_rejects_an_empty_title(
    env: dict[str, str],
    action: str,
) -> None:
    result = _run(env, action, stdin='\n')

    assert result.returncode == 1
    assert 'title' in result.stderr.lower()
    assert 'FZF-RAN' not in result.stderr
