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


def fake_windows(tmp_path: Path, *, powershell: str) -> Path:
    """A PATH entry standing in for the Windows interop binaries.

    `wslpath` is the identity here, so the path PowerShell is told to write
    is one the test can look at afterwards.
    """
    bin_dir = tmp_path / 'fakebin'
    bin_dir.mkdir(exist_ok=True)

    wslpath = bin_dir / 'wslpath'
    wslpath.write_text('#!/usr/bin/env bash\nprintf "%s" "$2"\n')
    wslpath.chmod(0o755)

    shell = bin_dir / 'powershell.exe'
    shell.write_text(powershell)
    shell.chmod(0o755)
    return bin_dir


# The output path is the first single-quoted literal in the script text;
# pull it back out and write a file there, the way a capture would.
CAPTURING_POWERSHELL = """#!/usr/bin/env bash
script="${@: -1}"
rest="${script#*\\'}"
printf 'png' > "${rest%%\\'*}"
"""

FAILING_POWERSHELL = """#!/usr/bin/env bash
echo 'CopyFromScreen failed' >&2
exit 1
"""

SILENT_POWERSHELL = '#!/usr/bin/env bash\nexit 0\n'


def take(
    tmp_path: Path,
    shots: Path,
    powershell: str = CAPTURING_POWERSHELL,
) -> subprocess.CompletedProcess[str]:
    bin_dir = fake_windows(tmp_path, powershell=powershell)
    return run(
        tmp_path,
        'take',
        SCREENSHOT_DIR=str(shots),
        PATH=f'{bin_dir}:{os.environ["PATH"]}',
    )


class TestTake:
    def test_captures_into_the_resolved_dir_and_prints_the_path(
        self,
        tmp_path: Path,
    ) -> None:
        shots = tmp_path / 'shots'
        shots.mkdir()

        result = take(tmp_path, shots)

        assert result.returncode == 0
        written = result.stdout.strip()
        assert Path(written).parent == shots
        assert Path(written).is_file()

    def test_the_new_file_is_what_latest_then_returns(
        self,
        tmp_path: Path,
    ) -> None:
        shots = tmp_path / 'shots'
        touch(shots / 'older.png', age_seconds=600)

        written = take(tmp_path, shots).stdout.strip()
        latest = run(tmp_path, 'latest', SCREENSHOT_DIR=str(shots))

        assert latest.stdout.strip() == written

    def test_never_overwrites_an_existing_file(self, tmp_path: Path) -> None:
        shots = tmp_path / 'shots'
        shots.mkdir()

        first = take(tmp_path, shots).stdout.strip()
        second = take(tmp_path, shots).stdout.strip()

        assert first != second
        assert Path(first).is_file()
        assert Path(second).is_file()

    def test_without_windows_interop_it_says_so(self, tmp_path: Path) -> None:
        shots = tmp_path / 'shots'
        shots.mkdir()

        # The stock Unix PATH: enough to run the script, never enough to
        # find powershell.exe, which lives under /mnt/c even on real WSL.
        result = run(
            tmp_path,
            'take',
            SCREENSHOT_DIR=str(shots),
            PATH='/usr/bin:/bin',
        )

        assert result.returncode == 1
        assert 'WSL' in result.stderr

    def test_a_failed_capture_surfaces_powershells_error(
        self,
        tmp_path: Path,
    ) -> None:
        shots = tmp_path / 'shots'
        shots.mkdir()

        result = take(tmp_path, shots, powershell=FAILING_POWERSHELL)

        assert result.returncode == 1
        assert 'CopyFromScreen failed' in result.stderr
        assert not list(shots.iterdir())

    def test_a_silent_capture_that_wrote_nothing_is_an_error(
        self,
        tmp_path: Path,
    ) -> None:
        shots = tmp_path / 'shots'
        shots.mkdir()

        result = take(tmp_path, shots, powershell=SILENT_POWERSHELL)

        assert result.returncode == 1
        assert 'nothing' in result.stderr


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
        for command in ('take', 'latest', 'list', 'dir', 'set'):
            assert command in result.stdout

    def test_unknown_command_is_an_error(self, tmp_path: Path) -> None:
        result = run(tmp_path, 'capture')

        assert result.returncode == 1
        assert 'capture' in result.stderr


class TestVersion:
    @pytest.mark.parametrize('flag', ['--version', '-V'])
    def test_prints_a_version_and_exits_zero(
        self,
        tmp_path: Path,
        flag: str,
    ) -> None:
        result = run(tmp_path, flag)

        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith('screenshot ')
        assert 'unknown' not in result.stdout

    def test_needs_no_screenshots_directory(self, tmp_path: Path) -> None:
        # Every resolution path is pointed at nothing here; --version has
        # to answer anyway, since it must work with no config.
        result = run(tmp_path, '--version', SCREENSHOT_DIR='')

        assert result.returncode == 0, result.stderr
