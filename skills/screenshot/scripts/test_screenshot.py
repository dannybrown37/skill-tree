"""Tests for the screenshot path resolver."""

import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / 'screenshot'


def touch(path: Path, age_seconds: float = 0) -> Path:
    """An image file with a controllable mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'not really a png')
    when = time.time() - age_seconds
    os.utime(path, (when, when))
    return path


def run(
    tmp_path: Path,
    *args: str,
    **env: str,
) -> subprocess.CompletedProcess[str]:
    """Invoke the script with every default pointed somewhere disposable."""
    return subprocess.run(  # noqa: S603
        ['bash', str(SCRIPT), *args],  # noqa: S607
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


class TestLatest:
    def test_prints_the_newest_image_absolute(self, tmp_path: Path) -> None:
        shots = tmp_path / 'shots'
        touch(shots / 'old.png', age_seconds=600)
        newest = touch(shots / 'new.png')

        result = run(tmp_path, 'latest', SCREENSHOT_DIR=str(shots))

        assert result.returncode == 0
        assert result.stdout.strip() == str(newest)

    def test_ignores_non_images(self, tmp_path: Path) -> None:
        shots = tmp_path / 'shots'
        image = touch(shots / 'shot.png', age_seconds=600)
        touch(shots / 'desktop.ini')

        result = run(tmp_path, 'latest', SCREENSHOT_DIR=str(shots))

        assert result.stdout.strip() == str(image)

    @pytest.mark.parametrize('name', ['SHOT.PNG', 'shot.JPEG', 'shot.webp'])
    def test_matches_extensions_case_insensitively(
        self,
        tmp_path: Path,
        name: str,
    ) -> None:
        shots = tmp_path / 'shots'
        image = touch(shots / name)

        result = run(tmp_path, 'latest', SCREENSHOT_DIR=str(shots))

        assert result.stdout.strip() == str(image)

    def test_an_empty_directory_is_an_error_naming_it(
        self,
        tmp_path: Path,
    ) -> None:
        shots = tmp_path / 'shots'
        shots.mkdir()

        result = run(tmp_path, 'latest', SCREENSHOT_DIR=str(shots))

        assert result.returncode == 1
        assert str(shots) in result.stderr


class TestList:
    def test_newest_first_and_capped(self, tmp_path: Path) -> None:
        shots = tmp_path / 'shots'
        for index in range(5):
            touch(shots / f'{index}.png', age_seconds=index * 60)

        result = run(tmp_path, 'list', '2', SCREENSHOT_DIR=str(shots))

        assert result.stdout.split() == [
            str(shots / '0.png'),
            str(shots / '1.png'),
        ]


class TestResolution:
    def test_screenshot_dir_wins_over_the_config_file(
        self,
        tmp_path: Path,
    ) -> None:
        env_dir = tmp_path / 'from-env'
        env_dir.mkdir()
        run(tmp_path, 'set', str(tmp_path / 'from-config'))

        result = run(tmp_path, 'dir', SCREENSHOT_DIR=str(env_dir))

        assert result.stdout.strip() == str(env_dir)

    def test_a_bad_screenshot_dir_is_an_error_not_a_fallback(
        self,
        tmp_path: Path,
    ) -> None:
        result = run(tmp_path, 'dir', SCREENSHOT_DIR=str(tmp_path / 'nope'))

        assert result.returncode == 1
        assert 'SCREENSHOT_DIR' in result.stderr

    def test_falls_back_to_the_home_pictures_folder(
        self,
        tmp_path: Path,
    ) -> None:
        expected = tmp_path / 'home' / 'Pictures' / 'Screenshots'
        expected.mkdir(parents=True)

        result = run(tmp_path, 'dir')

        assert result.stdout.strip() == str(expected)

    def test_says_how_to_configure_when_nothing_exists(
        self,
        tmp_path: Path,
    ) -> None:
        result = run(tmp_path, 'dir')

        assert result.returncode == 1
        assert 'set' in result.stderr

    def test_windows_profiles_are_probed_when_mounted(
        self,
        tmp_path: Path,
    ) -> None:
        users = tmp_path / 'Users'
        stale = users / 'danny' / 'Pictures' / 'Screenshots'
        current = users / 'danny' / 'OneDrive' / 'Pictures' / 'Screenshots'
        touch(stale / 'old.png', age_seconds=6000)
        touch(current / 'new.png')

        result = run(tmp_path, 'dir', WINDOWS_USERS_ROOT=str(users))

        assert result.stdout.strip() == str(current)

    def test_shared_windows_profiles_are_skipped(
        self,
        tmp_path: Path,
    ) -> None:
        users = tmp_path / 'Users'
        touch(users / 'Public' / 'Pictures' / 'Screenshots' / 'nope.png')
        mine = users / 'danny' / 'Pictures' / 'Screenshots'
        touch(mine / 'mine.png', age_seconds=6000)

        result = run(tmp_path, 'dir', WINDOWS_USERS_ROOT=str(users))

        assert result.stdout.strip() == str(mine)


class TestSet:
    def test_records_the_directory_and_dir_reads_it_back(
        self,
        tmp_path: Path,
    ) -> None:
        shots = tmp_path / 'elsewhere'
        shots.mkdir()

        assert run(tmp_path, 'set', str(shots)).returncode == 0
        assert run(tmp_path, 'dir').stdout.strip() == str(shots)

    def test_expands_a_leading_tilde(self, tmp_path: Path) -> None:
        shots = tmp_path / 'home' / 'shots'
        shots.mkdir(parents=True)

        assert run(tmp_path, 'set', '~/shots').returncode == 0
        assert run(tmp_path, 'dir').stdout.strip() == str(shots)

    def test_refuses_a_missing_directory(self, tmp_path: Path) -> None:
        result = run(tmp_path, 'set', str(tmp_path / 'nope'))

        assert result.returncode == 1
        assert 'not a directory' in result.stderr

    def test_a_stale_config_says_so_rather_than_guessing(
        self,
        tmp_path: Path,
    ) -> None:
        shots = tmp_path / 'gone'
        shots.mkdir()
        run(tmp_path, 'set', str(shots))
        shots.rmdir()

        result = run(tmp_path, 'dir')

        assert result.returncode == 1
        assert str(shots) in result.stderr


class TestUsage:
    @pytest.mark.parametrize('args', [(), ('help',), ('--help',)])
    def test_help_names_every_command(
        self,
        tmp_path: Path,
        args: tuple[str, ...],
    ) -> None:
        result = run(tmp_path, *args)

        assert result.returncode == 0
        for command in ('latest', 'list', 'dir', 'set'):
            assert command in result.stdout

    def test_unknown_command_is_an_error(self, tmp_path: Path) -> None:
        result = run(tmp_path, 'capture')

        assert result.returncode == 1
        assert 'capture' in result.stderr
