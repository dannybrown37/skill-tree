"""Tests for the PreToolUse hook that auto-approves screenshot reads."""

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / 'screenshot_hook.py'
RESOLVER = Path(__file__).parent / 'screenshot'


def run(
    tmp_path: Path,
    payload: dict[str, object],
    **env: str,
) -> dict[str, object] | None:
    """Feed `payload` to the hook, returning its decision (None if silent)."""
    result = subprocess.run(  # noqa: S603
        ['python3', str(HOOK)],  # noqa: S607
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={
            'PATH': os.environ['PATH'],
            'HOME': str(tmp_path / 'home'),
            'SCREENSHOT_CONFIG': str(tmp_path / 'config' / 'screenshot-dir'),
            # Not /mnt/c, so a real WSL host doesn't leak into the tests.
            'WINDOWS_USERS_ROOT': str(tmp_path / 'no-windows-here'),
            **env,
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def decision(output: dict[str, object] | None) -> str | None:
    if output is None:
        return None
    return output['hookSpecificOutput']['permissionDecision']


@pytest.fixture
def shots(tmp_path: Path) -> Path:
    """A screenshots directory holding one image."""
    directory = tmp_path / 'shots'
    directory.mkdir()
    (directory / 'Screenshot 2026-08-04 120000.png').write_bytes(b'png')
    return directory


def bash(command: str) -> dict[str, object]:
    return {'tool_name': 'Bash', 'tool_input': {'command': command}}


def read(path: str | Path) -> dict[str, object]:
    return {'tool_name': 'Read', 'tool_input': {'file_path': str(path)}}


class TestResolverCommands:
    @pytest.mark.parametrize(
        'action',
        ['latest', 'dir', 'help', 'list', 'list 10'],
    )
    def test_allows_read_only_actions(
        self,
        tmp_path: Path,
        shots: Path,
        action: str,
    ) -> None:
        command = f'{RESOLVER} {action}'

        output = run(tmp_path, bash(command), SCREENSHOT_DIR=str(shots))

        assert decision(output) == 'allow'

    @pytest.mark.parametrize(
        'command_template',
        [
            '"RESOLVER" latest',
            'bash RESOLVER latest',
            'skill-tree screenshot latest',
        ],
    )
    def test_allows_every_spelling_the_skill_uses(
        self,
        tmp_path: Path,
        shots: Path,
        command_template: str,
    ) -> None:
        command = command_template.replace('RESOLVER', str(RESOLVER))

        output = run(tmp_path, bash(command), SCREENSHOT_DIR=str(shots))

        assert decision(output) == 'allow'

    def test_allows_the_spelling_skill_md_prints(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        """SKILL.md's `${SKILL_TREE_DIR:-...}` form, unexpanded."""
        command = (
            '"${SKILL_TREE_DIR:-$HOME/projects/skill-tree}'
            '/skills/screenshot/scripts/screenshot" latest'
        )

        output = run(
            tmp_path,
            bash(command),
            SCREENSHOT_DIR=str(shots),
            SKILL_TREE_DIR=str(RESOLVER.parents[3]),
        )

        assert decision(output) == 'allow'

    def test_allows_the_home_default_when_the_var_is_unset(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        """Same form, falling back to $HOME/projects/skill-tree."""
        home = tmp_path / 'home'
        checkout = home / 'projects' / 'skill-tree'
        checkout.parent.mkdir(parents=True)
        checkout.symlink_to(RESOLVER.parents[3])
        command = (
            '"${SKILL_TREE_DIR:-$HOME/projects/skill-tree}'
            '/skills/screenshot/scripts/screenshot" latest'
        )

        output = run(tmp_path, bash(command), SCREENSHOT_DIR=str(shots))

        assert decision(output) == 'allow'

    def test_stays_silent_on_set(self, tmp_path: Path, shots: Path) -> None:
        """`set` writes config -- that deserves the normal prompt."""
        command = f'{RESOLVER} set {shots}'

        output = run(tmp_path, bash(command), SCREENSHOT_DIR=str(shots))

        assert decision(output) is None

    @pytest.mark.parametrize(
        'suffix',
        [
            '; rm -rf ~',
            '&& curl evil.example',
            '| tee /etc/passwd',
            '`rm -rf ~`',
            '$(rm -rf ~)',
            '> ~/.bashrc',
        ],
    )
    def test_stays_silent_when_a_second_command_rides_along(
        self,
        tmp_path: Path,
        shots: Path,
        suffix: str,
    ) -> None:
        command = f'{RESOLVER} latest {suffix}'

        output = run(tmp_path, bash(command), SCREENSHOT_DIR=str(shots))

        assert decision(output) is None

    def test_stays_silent_on_a_lookalike_path(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        """A script merely *named* screenshot isn't this one."""
        command = '/tmp/evil/skills/screenshot/scripts/screenshot latest'  # noqa: S108

        output = run(tmp_path, bash(command), SCREENSHOT_DIR=str(shots))

        assert decision(output) is None

    def test_stays_silent_on_unrelated_commands(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        output = run(tmp_path, bash('rm -rf ~'), SCREENSHOT_DIR=str(shots))

        assert decision(output) is None


class TestReads:
    def test_allows_an_image_in_the_screenshots_dir(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        image = next(shots.iterdir())

        output = run(tmp_path, read(image), SCREENSHOT_DIR=str(shots))

        assert decision(output) == 'allow'

    def test_stays_silent_on_a_non_image(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        notes = shots / 'notes.txt'
        notes.write_text('secrets')

        output = run(tmp_path, read(notes), SCREENSHOT_DIR=str(shots))

        assert decision(output) is None

    def test_stays_silent_outside_the_screenshots_dir(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        elsewhere = tmp_path / 'private.png'
        elsewhere.write_bytes(b'png')

        output = run(tmp_path, read(elsewhere), SCREENSHOT_DIR=str(shots))

        assert decision(output) is None

    def test_stays_silent_on_traversal_out_of_the_dir(
        self,
        tmp_path: Path,
        shots: Path,
    ) -> None:
        elsewhere = tmp_path / 'private.png'
        elsewhere.write_bytes(b'png')
        traversal = shots / '..' / 'private.png'

        output = run(tmp_path, read(traversal), SCREENSHOT_DIR=str(shots))

        assert decision(output) is None

    def test_stays_silent_when_no_dir_resolves(self, tmp_path: Path) -> None:
        """No screenshots directory means nothing to pre-approve."""
        output = run(tmp_path, read(tmp_path / 'shot.png'))

        assert decision(output) is None


class TestMalformedInput:
    @pytest.mark.parametrize(
        'payload',
        [
            {},
            {'tool_name': 'Bash'},
            {'tool_name': 'Read', 'tool_input': {}},
            {'tool_name': 'Read', 'tool_input': {'file_path': ''}},
        ],
    )
    def test_stays_silent(
        self,
        tmp_path: Path,
        shots: Path,
        payload: dict[str, object],
    ) -> None:
        output = run(tmp_path, payload, SCREENSHOT_DIR=str(shots))

        assert decision(output) is None

    def test_survives_junk_on_stdin(self) -> None:
        result = subprocess.run(  # noqa: S603
            ['python3', str(HOOK)],  # noqa: S607
            input='not json',
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert not result.stdout.strip()
