"""Tests for hooks_cli -- merged hook visibility across Claude and Copilot."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hooks_cli

CLI = Path(__file__).resolve().parent / 'hooks'


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway $HOME, so the real one is never touched."""
    path = tmp_path / 'home'
    path.mkdir()
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / 'project'
    path.mkdir()
    return path


def _write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class TestClaudeSources:
    def test_user_settings_hooks_are_found(
        self,
        home: Path,
        root: Path,
    ) -> None:
        _write(
            home / '.claude' / 'settings.json',
            {
                'hooks': {
                    'PreToolUse': [
                        {
                            'matcher': 'Bash',
                            'hooks': [
                                {'type': 'command', 'command': 'atuin hook'},
                            ],
                        },
                    ],
                },
            },
        )
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        claude = [e for e in entries if e.host == 'claude']
        assert len(claude) == 1
        assert claude[0].event == 'PreToolUse'
        assert claude[0].matcher == 'Bash'
        assert claude[0].command == 'atuin hook'
        assert claude[0].source == 'user settings'

    def test_project_and_local_settings_are_both_read(
        self,
        home: Path,
        root: Path,
    ) -> None:
        _write(
            root / '.claude' / 'settings.json',
            {
                'hooks': {
                    'SessionStart': [
                        {'hooks': [{'type': 'command', 'command': 'a'}]},
                    ],
                },
            },
        )
        _write(
            root / '.claude' / 'settings.local.json',
            {
                'hooks': {
                    'Stop': [{'hooks': [{'type': 'command', 'command': 'b'}]}],
                },
            },
        )
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        sources = {e.source for e in entries}
        assert 'project settings' in sources
        assert 'local settings' in sources

    def test_missing_settings_files_are_not_an_error(
        self,
        home: Path,
        root: Path,
    ) -> None:
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        assert entries == []

    def test_malformed_settings_file_is_reported_not_raised(
        self,
        home: Path,
        root: Path,
    ) -> None:
        path = home / '.claude' / 'settings.json'
        path.parent.mkdir(parents=True)
        path.write_text('{not json')
        result = hooks_cli.gather(home=home, root=root, plugins_home=home)
        assert result.entries == []
        assert any('settings.json' in warning for warning in result.warnings)

    def test_installed_plugin_hooks_are_found(
        self,
        home: Path,
        root: Path,
    ) -> None:
        install_path = (
            home / 'plugins' / 'cache' / 'skill-tree' / 'skill-tree' / '0.2.1'
        )
        _write(
            home / '.claude' / 'plugins' / 'installed_plugins.json',
            {
                'plugins': {
                    'skill-tree@skill-tree': [
                        {'installPath': str(install_path)},
                    ],
                },
            },
        )
        _write(
            install_path / 'hooks' / 'hooks.json',
            {
                'hooks': {
                    'SessionStart': [
                        {
                            'hooks': [
                                {'type': 'command', 'command': 'install.sh'},
                            ],
                        },
                    ],
                },
            },
        )
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        plugin_entries = [
            e for e in entries if e.source == 'plugin:skill-tree@skill-tree'
        ]
        assert len(plugin_entries) == 1
        assert plugin_entries[0].command == 'install.sh'

    def test_missing_installed_plugin_hooks_file_is_skipped(
        self,
        home: Path,
        root: Path,
    ) -> None:
        install_path = (
            home / 'plugins' / 'cache' / 'no-hooks' / 'no-hooks' / '1.0.0'
        )
        install_path.mkdir(parents=True)
        _write(
            home / '.claude' / 'plugins' / 'installed_plugins.json',
            {
                'plugins': {
                    'no-hooks@no-hooks': [{'installPath': str(install_path)}],
                },
            },
        )
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        assert entries == []


EXPECTED_TIMEOUT_SECONDS = 15


class TestCopilotSources:
    def test_copilot_hooks_are_found(self, home: Path, root: Path) -> None:
        _write(
            home / '.copilot' / 'hooks' / 'skill-tree.json',
            {
                'hooks': {
                    'preToolUse': [
                        {
                            'type': 'command',
                            'matcher': '(?i)bash',
                            'bash': 'screenshot_hook.py',
                            'timeoutSec': EXPECTED_TIMEOUT_SECONDS,
                        },
                    ],
                },
            },
        )
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        copilot = [e for e in entries if e.host == 'copilot']
        assert len(copilot) == 1
        assert copilot[0].event == 'preToolUse'
        assert copilot[0].matcher == '(?i)bash'
        assert copilot[0].command == 'screenshot_hook.py'
        assert copilot[0].timeout == EXPECTED_TIMEOUT_SECONDS
        assert copilot[0].source == 'copilot:skill-tree.json'

    def test_no_copilot_dir_is_not_an_error(
        self,
        home: Path,
        root: Path,
    ) -> None:
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        assert entries == []

    def test_multiple_copilot_hook_files_are_all_read(
        self,
        home: Path,
        root: Path,
    ) -> None:
        _write(
            home / '.copilot' / 'hooks' / 'a.json',
            {'hooks': {'sessionStart': [{'type': 'command', 'bash': 'a.sh'}]}},
        )
        _write(
            home / '.copilot' / 'hooks' / 'b.json',
            {'hooks': {'sessionStart': [{'type': 'command', 'bash': 'b.sh'}]}},
        )
        entries = hooks_cli.collect(home=home, root=root, plugins_home=home)
        assert {e.command for e in entries} == {'a.sh', 'b.sh'}


class TestRenderAndGroup:
    def test_shared_event_is_flagged_when_multiple_sources_hit_it(
        self,
    ) -> None:
        entries = [
            hooks_cli.HookEntry(
                host='claude',
                source='user settings',
                event='PreToolUse',
                matcher='Bash',
                command='a',
                timeout=None,
            ),
            hooks_cli.HookEntry(
                host='claude',
                source='plugin:x@x',
                event='PreToolUse',
                matcher='Bash',
                command='b',
                timeout=None,
            ),
        ]
        text = hooks_cli.render(entries, warnings=[])
        assert 'PreToolUse' in text
        assert '2 sources' in text

    def test_render_with_no_entries_says_so(self) -> None:
        text = hooks_cli.render([], warnings=[])
        assert 'no hooks' in text.lower()

    def test_as_json_round_trips_fields(self) -> None:
        entries = [
            hooks_cli.HookEntry(
                host='claude',
                source='user settings',
                event='PreToolUse',
                matcher='Bash',
                command='a',
                timeout=None,
            ),
        ]
        data = json.loads(hooks_cli.as_json(entries, warnings=[]))
        assert data['hooks'][0]['command'] == 'a'
        assert data['hooks'][0]['host'] == 'claude'


class TestCli:
    def test_version_flag_exits_zero(self) -> None:
        result = subprocess.run(  # noqa: S603
            [str(CLI), '--version'],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert 'hooks' in result.stdout

    def test_bare_run_against_empty_home_prints_no_hooks(
        self,
        home: Path,
        root: Path,
    ) -> None:
        result = subprocess.run(  # noqa: S603
            [str(CLI)],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
            env={'HOME': str(home), 'PATH': '/usr/bin:/bin'},
        )
        assert result.returncode == 0
        assert 'no hooks' in result.stdout.lower()

    def test_json_flag_produces_parseable_output(
        self,
        home: Path,
        root: Path,
    ) -> None:
        _write(
            home / '.claude' / 'settings.json',
            {
                'hooks': {
                    'PreToolUse': [
                        {'hooks': [{'type': 'command', 'command': 'a'}]},
                    ],
                },
            },
        )
        result = subprocess.run(  # noqa: S603
            [str(CLI), '--json'],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
            env={'HOME': str(home), 'PATH': '/usr/bin:/bin'},
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data['hooks'][0]['command'] == 'a'

    def test_claude_only_flag_excludes_copilot(
        self,
        home: Path,
        root: Path,
    ) -> None:
        _write(
            home / '.copilot' / 'hooks' / 'x.json',
            {'hooks': {'sessionStart': [{'type': 'command', 'bash': 'a.sh'}]}},
        )
        result = subprocess.run(  # noqa: S603
            [str(CLI), '--claude'],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
            env={'HOME': str(home), 'PATH': '/usr/bin:/bin'},
        )
        assert 'a.sh' not in result.stdout
