"""Tests for the Python screenshot CLI."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import screenshot_cli as cli

SCRIPT = Path(__file__).parent / 'screenshot_cli.py'


def image(path: Path, age_seconds: float = 0) -> Path:
    """An image file with a controllable mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'not really a png')
    when = time.time() - age_seconds
    os.utime(path, (when, when))
    return path


class TestUserProfiles:
    def test_skips_the_system_profiles(self, tmp_path: Path) -> None:
        for name in ('Public', 'Default', 'danny'):
            (tmp_path / name).mkdir()

        assert [p.name for p in cli.user_profiles(tmp_path, None)] == ['danny']

    def test_a_named_user_wins_outright(self, tmp_path: Path) -> None:
        (tmp_path / 'danny').mkdir()
        (tmp_path / 'other').mkdir()

        profiles = cli.user_profiles(tmp_path, 'danny')

        assert [p.name for p in profiles] == ['danny']

    def test_a_named_user_that_does_not_exist_falls_back(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / 'other').mkdir()

        assert [p.name for p in cli.user_profiles(tmp_path, 'ghost')] == [
            'other',
        ]

    def test_a_missing_users_root_is_empty_not_an_error(
        self,
        tmp_path: Path,
    ) -> None:
        assert cli.user_profiles(tmp_path / 'nope', None) == []


class TestResolveScreenshotDir:
    def test_an_override_is_taken_as_is(self, tmp_path: Path) -> None:
        resolved = cli.resolve_screenshot_dir(
            override=str(tmp_path),
            users_root=tmp_path / 'unused',
            windows_username=None,
        )

        assert resolved == tmp_path

    def test_a_bad_override_is_an_error_not_a_fallback(
        self,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(cli.ScreenshotError, match='Not a directory'):
            cli.resolve_screenshot_dir(
                override=str(tmp_path / 'missing'),
                users_root=tmp_path,
                windows_username=None,
            )

    def test_the_directory_with_the_newest_shot_wins(
        self,
        tmp_path: Path,
    ) -> None:
        profile = tmp_path / 'danny'
        stale = profile / 'Pictures' / 'Screenshots'
        live = profile / 'OneDrive' / 'Pictures' / 'Screenshots'
        image(stale / 'old.png', age_seconds=9000)
        image(live / 'new.png')

        resolved = cli.resolve_screenshot_dir(
            override=None,
            users_root=tmp_path,
            windows_username=None,
        )

        assert resolved == live

    def test_no_candidates_names_the_env_var_to_set(
        self,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(cli.ScreenshotError, match='SCREENSHOT_DIR'):
            cli.resolve_screenshot_dir(
                override=None,
                users_root=tmp_path,
                windows_username=None,
            )


class TestScreenshotPaths:
    def test_newest_first(self, tmp_path: Path) -> None:
        image(tmp_path / 'old.png', age_seconds=100)
        image(tmp_path / 'new.png')

        names = [p.name for p in cli.screenshot_paths(tmp_path)]

        assert names == ['new.png', 'old.png']

    @pytest.mark.parametrize(
        ('name', 'kept'),
        [
            ('shot.png', True),
            ('shot.JPG', True),
            ('shot.webp', True),
            ('desktop.ini', False),
            ('notes.txt', False),
        ],
    )
    def test_only_image_suffixes_count(
        self,
        tmp_path: Path,
        name: str,
        kept: bool,  # noqa: FBT001
    ) -> None:
        image(tmp_path / name)

        assert bool(cli.screenshot_paths(tmp_path)) is kept

    def test_limit_caps_the_list(self, tmp_path: Path) -> None:
        limit = 2
        for index in range(5):
            image(tmp_path / f'{index}.png', age_seconds=index)

        assert len(cli.screenshot_paths(tmp_path, limit=limit)) == limit

    def test_an_empty_directory_has_no_latest(self, tmp_path: Path) -> None:
        with pytest.raises(cli.ScreenshotError, match='No screenshots'):
            cli.latest_screenshot(tmp_path)


class TestFreeDestination:
    def test_an_unused_name_is_returned_unchanged(
        self,
        tmp_path: Path,
    ) -> None:
        target = tmp_path / 'shot.png'

        assert cli.free_destination(target) == target

    def test_a_taken_name_gets_a_suffix_before_the_extension(
        self,
        tmp_path: Path,
    ) -> None:
        image(tmp_path / 'shot.png')

        assert cli.free_destination(tmp_path / 'shot.png').name == 'shot-1.png'

    def test_suffixes_keep_climbing(self, tmp_path: Path) -> None:
        image(tmp_path / 'shot.png')
        image(tmp_path / 'shot-1.png')

        assert cli.free_destination(tmp_path / 'shot.png').name == 'shot-2.png'


class TestMoveScreenshots:
    def test_moves_each_file_and_reports_the_new_paths(
        self,
        tmp_path: Path,
    ) -> None:
        source = image(tmp_path / 'src' / 'shot.png')
        dest = tmp_path / 'dest'

        moved = cli.move_screenshots([source], dest)

        assert moved == [dest / 'shot.png']
        assert not source.exists()
        assert (dest / 'shot.png').is_file()

    def test_creates_a_missing_destination(self, tmp_path: Path) -> None:
        source = image(tmp_path / 'src' / 'shot.png')

        cli.move_screenshots([source], tmp_path / 'a' / 'b')

        assert (tmp_path / 'a' / 'b' / 'shot.png').is_file()

    def test_never_overwrites_at_the_destination(
        self,
        tmp_path: Path,
    ) -> None:
        source = image(tmp_path / 'src' / 'shot.png')
        dest = tmp_path / 'dest'
        existing = image(dest / 'shot.png')
        existing.write_bytes(b'keep me')

        moved = cli.move_screenshots([source], dest)

        assert moved == [dest / 'shot-1.png']
        assert existing.read_bytes() == b'keep me'

    def test_a_missing_source_is_an_error_naming_it(
        self,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(cli.ScreenshotError, match='No such file'):
            cli.move_screenshots([tmp_path / 'ghost.png'], tmp_path / 'dest')

    def test_a_file_as_the_destination_is_an_error(
        self,
        tmp_path: Path,
    ) -> None:
        source = image(tmp_path / 'src' / 'shot.png')
        blocker = tmp_path / 'dest'
        blocker.write_text('not a directory')

        with pytest.raises(cli.ScreenshotError, match='Not a directory'):
            cli.move_screenshots([source], blocker)


class TestPowerShellQuoting:
    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            (r'C:\Users\danny\shot.png', r"'C:\Users\danny\shot.png'"),
            ('with space.png', "'with space.png'"),
            ("it's.png", "'it''s.png'"),
            ('$env:PATH', "'$env:PATH'"),
        ],
        ids=['plain', 'space', 'quote', 'dollar-is-inert'],
    )
    def test_single_quoted_literal(self, value: str, expected: str) -> None:
        assert cli.powershell_string_literal(value) == expected


class TestVersion:
    def test_reads_the_version_from_the_plugin_manifest(
        self,
        tmp_path: Path,
    ) -> None:
        manifest = tmp_path / '.claude-plugin'
        manifest.mkdir()
        (manifest / 'plugin.json').write_text('{"version": "9.9.9"}')

        assert cli.version(tmp_path) == '9.9.9'

    @pytest.mark.parametrize(
        'contents',
        [None, 'not json', '{}'],
        ids=['missing', 'unparseable', 'no-version-key'],
    )
    def test_an_unreadable_manifest_is_unknown_not_a_crash(
        self,
        tmp_path: Path,
        contents: str | None,
    ) -> None:
        if contents is not None:
            manifest = tmp_path / '.claude-plugin'
            manifest.mkdir()
            (manifest / 'plugin.json').write_text(contents)

        assert cli.version(tmp_path) == 'unknown'

    @pytest.mark.parametrize('flag', ['--version', '-V'])
    def test_the_flag_prints_a_version_and_exits_zero(
        self,
        tmp_path: Path,
        flag: str,
    ) -> None:
        # An empty HOME and a users root that does not exist stand in for
        # "no config, not WSL" -- --version has to answer regardless.
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(SCRIPT), flag],
            capture_output=True,
            text=True,
            check=False,
            env={
                'PATH': os.environ['PATH'],
                'HOME': str(tmp_path),
                'WINDOWS_USERS_ROOT': str(tmp_path / 'no-windows-here'),
            },
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith('screenshot ')
        assert 'unknown' not in result.stdout
