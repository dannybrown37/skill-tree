"""Every shipped hook stays quiet and exits 0 when a dependency is unusable.

A hook's stdout lands in the model's context, and a nonzero exit or stderr
surfaces as an error on every tool call or session start. A hook that
can't do its job must say nothing rather than spam the session.
"""

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent

# Present on any machine a hook runs on; the hooks may assume them.
BASELINE = (
    'bash',
    'sh',
    'env',
    'cat',
    'dirname',
    'basename',
    'mkdir',
    'ln',
    'readlink',
    'rm',
    'mv',
    'cmp',
    'touch',
    'date',
    'stat',
    'cut',
    'head',
    'grep',
    'awk',
    'sed',
    'sleep',
    'timeout',
)

# What a hook may run but can't assume. (`copilot` is left out: install.sh
# only checks it exists, and its presence rightly changes what gets linked.)
OPTIONAL = ('python3', 'jq', 'git', 'claude')

SLOW_SECONDS = 8

CLAUDE_READ_PNG = json.dumps(
    {
        'hook_event_name': 'PreToolUse',
        'tool_name': 'Read',
        'tool_input': {'file_path': 'Pictures/shot.png'},
    },
)
COPILOT_VIEW_PNG = json.dumps(
    {'toolName': 'view', 'toolArgs': {'path': 'Pictures/shot.png'}},
)
SESSION_START = json.dumps(
    {'hook_event_name': 'SessionStart', 'source': 'startup'},
)
COPILOT_ABSTAIN = '{"permissionDecision": "ask"}'


@dataclass(frozen=True)
class Hook:
    script: str
    payload: str
    expected_stdout: str = ''


HOOKS = {
    'screenshot-claude': Hook(
        'skills/screenshot/scripts/screenshot_hook.sh',
        CLAUDE_READ_PNG,
    ),
    'screenshot-copilot': Hook(
        'skills/screenshot/scripts/screenshot_hook.sh',
        COPILOT_VIEW_PNG,
        COPILOT_ABSTAIN,
    ),
    'install': Hook('scripts/install.sh', SESSION_START),
    'check-plugin-update': Hook(
        'scripts/check_plugin_update.sh',
        SESSION_START,
    ),
    'check-repo-update': Hook('scripts/check_repo_update.sh', SESSION_START),
    'handoff-session-start': Hook(
        'skills/handoff/scripts/handoff_session_start.sh',
        SESSION_START,
    ),
}


def shipped_hook_scripts() -> set[str]:
    """Every script a host is told to run, from both hosts' configs."""
    claude = json.loads((REPO / 'hooks' / 'hooks.json').read_text())
    commands = [
        hook['command']
        for groups in claude['hooks'].values()
        for group in groups
        for hook in group['hooks']
    ]
    scripts = {
        re.sub(r'^"\$\{CLAUDE_PLUGIN_ROOT\}"/', '', command).split()[0]
        for command in commands
    }
    install = (REPO / 'scripts' / 'install.sh').read_text()
    scripts |= set(
        re.findall(r'"bash": "\$\{_link_root\}/([^" ]+)', install),
    )
    return scripts


def test_every_shipped_hook_is_covered() -> None:
    covered = {hook.script for hook in HOOKS.values()}
    assert shipped_hook_scripts() <= covered


def link_baseline(bin_dir: Path) -> None:
    bin_dir.mkdir()
    for name in BASELINE:
        found = shutil.which(name)
        if found is not None:
            (bin_dir / name).symlink_to(found)


def write_stub(bin_dir: Path, name: str, body: str) -> None:
    stub = bin_dir / name
    stub.write_text(f'#!/bin/sh\n{body}\n')
    stub.chmod(0o755)


def broken(bin_dir: Path) -> None:
    for name in OPTIONAL:
        write_stub(bin_dir, name, f'echo "{name}: broken" >&2\nexit 1')


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A $HOME where each hook gets far enough to reach its dependencies."""
    path = tmp_path / 'home'
    (path / '.local' / 'bin').mkdir(parents=True)
    # Installed once with everything available, so a rerun is a no-op
    # unless a dependency failure leaks.
    subprocess.run(
        ['bash', str(REPO / 'scripts' / 'install.sh'), '--claude'],
        env={
            'HOME': str(path),
            'PATH': os.environ['PATH'],
            'SKILL_TREE_DIR': str(REPO),
        },
        capture_output=True,
        check=True,
    )
    # No statusLine, so install.sh reaches for jq to merge one in.
    (path / '.claude' / 'settings.json').write_text('{}\n')
    plugins = path / '.claude' / 'plugins'
    plugins.mkdir(parents=True)
    (plugins / 'installed_plugins.json').write_text(
        json.dumps(
            {
                'plugins': {
                    'skill-tree@skill-tree': [{'gitCommitSha': 'a' * 40}],
                },
            },
        ),
    )
    return path


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """Looks like a repo with a handoff, but only git can say which branch."""
    path = tmp_path / 'repo'
    (path / '.git').mkdir(parents=True)
    handoff = path / 'docs' / 'handoffs' / 'main'
    handoff.mkdir(parents=True)
    (handoff / 'CURRENT.md').write_text('**Status:** in-progress\n')
    return path


def run_hook(
    hook: Hook,
    home: Path,
    bin_dir: Path,
    cwd: Path,
) -> tuple[subprocess.CompletedProcess[str], float]:
    env = {
        'HOME': str(home),
        'PATH': f'{bin_dir}:{home / ".local" / "bin"}',
        'SKILL_TREE_DIR': str(REPO),
        'CLAUDE_PLUGIN_ROOT': str(REPO),
    }
    start = time.monotonic()
    result = subprocess.run(
        [str(bin_dir / 'bash'), str(REPO / hook.script)],
        input=hook.payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=SLOW_SECONDS * 3,
        check=False,
    )
    return result, time.monotonic() - start


@pytest.mark.parametrize('mode', ['missing', 'broken'])
@pytest.mark.parametrize('name', sorted(HOOKS))
def test_hook_is_silent_when_dependencies_are_unusable(
    name: str,
    mode: str,
    home: Path,
    workdir: Path,
    tmp_path: Path,
) -> None:
    hook = HOOKS[name]
    bin_dir = tmp_path / 'bin'
    link_baseline(bin_dir)
    if mode == 'broken':
        broken(bin_dir)

    result, elapsed = run_hook(hook, home, bin_dir, workdir)

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        hook.expected_stdout,
        '',
    )
    assert elapsed < SLOW_SECONDS
    assert not list((home / '.claude').glob('settings.json.tmp.*'))


@pytest.mark.parametrize(
    'git',
    [
        pytest.param('exec sleep 60', id='hung'),
        pytest.param(
            'echo "fatal: unable to access" >&2\nexit 128',
            id='offline',
        ),
    ],
)
def test_plugin_update_check_is_silent_without_network(
    git: str,
    home: Path,
    workdir: Path,
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / 'bin'
    link_baseline(bin_dir)
    write_stub(bin_dir, 'jq', f'exec {shutil.which("jq")} "$@"')
    write_stub(bin_dir, 'claude', 'echo "claude ran" >&2')
    write_stub(bin_dir, 'git', git)

    result, elapsed = run_hook(
        HOOKS['check-plugin-update'],
        home,
        bin_dir,
        workdir,
    )

    assert (result.returncode, result.stdout, result.stderr) == (0, '', '')
    assert elapsed < SLOW_SECONDS
