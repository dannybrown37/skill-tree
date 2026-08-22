"""Regression tests for scripts/install.sh."""

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / 'install.sh'
REPO_ROOT = SCRIPT.parent.parent


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway $HOME, so the real one is never touched."""
    path = tmp_path / 'home'
    (path / '.local' / 'bin').mkdir(parents=True)
    return path


def run(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ['bash', str(SCRIPT), *args],  # noqa: S607
        capture_output=True,
        text=True,
        env={
            'HOME': str(home),
            'PATH': '/usr/bin:/bin',
            'SKILL_TREE_DIR': str(REPO_ROOT),
        },
        check=False,
    )


def skill_names() -> list[str]:
    return sorted(
        path.name
        for path in (REPO_ROOT / 'skills').iterdir()
        if (path / 'SKILL.md').is_file()
    )


@pytest.mark.parametrize(
    ('link', 'target'),
    [
        ('.local/bin/skill-tree', 'scripts/skill-tree'),
        ('.local/bin/handoff', 'skills/handoff/scripts/handoff'),
        (
            '.local/share/bash-completion/completions/skill-tree',
            'scripts/completions/skill-tree.bash',
        ),
    ],
)
def test_install_links_are_created(home: Path, link: str, target: str) -> None:
    result = run(home)

    assert result.returncode == 0, result.stderr
    assert (home / link).resolve() == (REPO_ROOT / target).resolve()


def test_install_is_idempotent(home: Path) -> None:
    assert run(home).returncode == 0
    second = run(home)

    assert second.returncode == 0, second.stderr
    assert (home / '.local' / 'bin' / 'skill-tree').is_symlink()


def test_install_does_not_clobber_a_real_file(home: Path) -> None:
    """Someone else's `skill-tree` on PATH is left alone, not replaced."""
    theirs = home / '.local' / 'bin' / 'skill-tree'
    theirs.write_text('#!/bin/sh\necho not ours\n')

    result = run(home)

    assert result.returncode == 0, result.stderr
    assert theirs.read_text() == '#!/bin/sh\necho not ours\n'
    assert 'Skipping' in result.stderr


def test_install_retires_stale_backlog_shortcuts(home: Path) -> None:
    """A machine that ran an earlier install heals itself."""
    claude_skills = home / '.claude' / 'skills'
    claude_skills.mkdir(parents=True)
    # Points at a path that no longer exists -- backlog was removed from the
    # repo, but the retirement loop only inspects the symlink target string.
    (claude_skills / 'backlog').symlink_to(REPO_ROOT / 'skills' / 'backlog')
    (home / '.local' / 'bin' / 'backlog').symlink_to(
        REPO_ROOT / 'skills' / 'backlog' / 'scripts' / 'backlog',
    )
    (home / '.local' / 'bin' / 'bl').symlink_to(
        REPO_ROOT / 'skills' / 'backlog' / 'scripts' / 'backlog',
    )

    result = run(home)

    assert result.returncode == 0, result.stderr
    assert not (claude_skills / 'backlog').exists()
    assert not (home / '.local' / 'bin' / 'backlog').exists()
    assert not (home / '.local' / 'bin' / 'bl').exists()


class TestCopilot:
    """Copilot has no plugin/marketplace concept -- symlinks are the install.

    It also has no namespace: `skill-tree:verify` doesn't exist there, so
    every skill lands bare under ~/.copilot/skills/ rather than the
    deliberately-short list the Claude side links.
    """

    def test_every_skill_is_linked(self, home: Path) -> None:
        result = run(home, '--copilot')

        assert result.returncode == 0, result.stderr
        for name in skill_names():
            link = home / '.copilot' / 'skills' / name
            assert link.resolve() == (REPO_ROOT / 'skills' / name).resolve()

    def test_is_skipped_unless_asked_for_or_detected(self, home: Path) -> None:
        """A Claude-only machine doesn't grow a ~/.copilot directory."""
        result = run(home)

        assert result.returncode == 0, result.stderr
        assert not (home / '.copilot').exists()

    def test_is_detected_from_an_existing_copilot_home(
        self,
        home: Path,
    ) -> None:
        (home / '.copilot').mkdir(parents=True)

        result = run(home)

        assert result.returncode == 0, result.stderr
        assert (home / '.copilot' / 'skills' / 'verify').is_symlink()

    def test_copilot_only_skips_the_claude_side(self, home: Path) -> None:
        result = run(home, '--copilot')

        assert result.returncode == 0, result.stderr
        assert not (home / '.claude').exists()
        assert not (home / '.local' / 'bin' / 'skill-tree').exists()

    def test_both_flags_install_both_sides(self, home: Path) -> None:
        result = run(home, '--claude', '--copilot')

        assert result.returncode == 0, result.stderr
        assert (home / '.local' / 'bin' / 'skill-tree').is_symlink()
        assert (home / '.copilot' / 'skills' / 'verify').is_symlink()

    def test_is_idempotent(self, home: Path) -> None:
        assert run(home, '--copilot').returncode == 0
        second = run(home, '--copilot')

        assert second.returncode == 0, second.stderr
        assert (home / '.copilot' / 'skills' / 'verify').is_symlink()

    def test_does_not_clobber_a_real_skill_directory(self, home: Path) -> None:
        theirs = home / '.copilot' / 'skills' / 'verify'
        theirs.mkdir(parents=True)
        (theirs / 'SKILL.md').write_text('mine, not yours')

        result = run(home, '--copilot')

        assert result.returncode == 0, result.stderr
        assert (theirs / 'SKILL.md').read_text() == 'mine, not yours'
        assert 'Skipping' in result.stderr


class TestCopilotHooks:
    """The hook config is generated, not symlinked.

    It has to name an absolute path to the hook script, and Copilot's
    schema has no equivalent of ${CLAUDE_PLUGIN_ROOT} to defer that with.
    """

    @staticmethod
    def config(home: Path) -> dict:
        path = home / '.copilot' / 'hooks' / 'skill-tree.json'
        return json.loads(path.read_text())

    def test_is_written_with_absolute_paths(self, home: Path) -> None:
        result = run(home, '--copilot')

        assert result.returncode == 0, result.stderr
        hooks = self.config(home)['hooks']
        commands = [hook['bash'] for event in hooks.values() for hook in event]
        assert commands, 'no hook commands written'
        for command in commands:
            assert str(REPO_ROOT) in command
            assert '$' not in command

    def test_registers_the_screenshot_pre_tool_use_hook(
        self,
        home: Path,
    ) -> None:
        run(home, '--copilot')

        pre = self.config(home)['hooks']['preToolUse']

        assert len(pre) == 1
        assert 'screenshot_hook.py' in pre[0]['bash']
        assert pre[0]['type'] == 'command'
        assert 'matcher' in pre[0]

    def test_session_start_reinstalls_and_checks_for_updates(
        self,
        home: Path,
    ) -> None:
        run(home, '--copilot')

        commands = [
            hook['bash'] for hook in self.config(home)['hooks']['sessionStart']
        ]

        assert any('install.sh --copilot' in c for c in commands)
        assert any('check_repo_update.sh' in c for c in commands)
        assert any('handoff_session_start.sh' in c for c in commands)

    def test_is_rewritten_in_place_on_reinstall(self, home: Path) -> None:
        """A stale config we generated is ours to refresh."""
        run(home, '--copilot')
        path = home / '.copilot' / 'hooks' / 'skill-tree.json'
        path.write_text('{"_source": "skill-tree", "hooks": {}}')

        result = run(home, '--copilot')

        assert result.returncode == 0, result.stderr
        assert self.config(home)['hooks']['preToolUse']

    def test_does_not_clobber_a_hand_written_config(self, home: Path) -> None:
        """Only a file carrying our marker is ours to overwrite."""
        path = home / '.copilot' / 'hooks' / 'skill-tree.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"hooks": {"sessionStart": []}}')

        result = run(home, '--copilot')

        assert result.returncode == 0, result.stderr
        assert path.read_text() == '{"hooks": {"sessionStart": []}}'
        assert 'Skipping' in result.stderr
