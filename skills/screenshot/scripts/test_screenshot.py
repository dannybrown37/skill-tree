"""Regression tests for scripts/screenshot_cli.py."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from screenshot_cli import (
    IMAGE_SUFFIXES,
    SKIPPED_WINDOWS_USERS,
    ScreenshotError,
    latest_screenshot,
    resolve_screenshot_dir,
    screenshot_paths,
)

CLI = Path(__file__).parent / 'screenshot_cli.py'


def make_image(directory: Path, name: str, mtime: float) -> Path:
    """Create a stub image file with a controlled modification time."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b'stub')
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def users_root(tmp_path: Path) -> Path:
    return tmp_path / 'mnt' / 'c' / 'Users'


def resolve(users_root: Path, **kwargs: object) -> Path:
    defaults: dict[str, object] = {
        'override': None,
        'users_root': users_root,
        'windows_username': None,
    }
    defaults.update(kwargs)
    return resolve_screenshot_dir(**defaults)  # type: ignore[arg-type]


class TestResolveScreenshotDir:
    def test_override_wins_over_everything(
        self,
        users_root: Path,
        tmp_path: Path,
    ) -> None:
        explicit = tmp_path / 'elsewhere'
        explicit.mkdir()
        make_image(
            users_root / 'danny' / 'Pictures' / 'Screenshots',
            'a.png',
            1,
        )

        assert resolve(users_root, override=str(explicit)) == explicit

    def test_override_that_does_not_exist_is_an_error(
        self,
        users_root: Path,
        tmp_path: Path,
    ) -> None:
        missing = tmp_path / 'nope'

        with pytest.raises(ScreenshotError, match='nope'):
            resolve(users_root, override=str(missing))

    @pytest.mark.parametrize(
        'subpath',
        [
            'OneDrive/Pictures/Screenshots',
            'Pictures/Screenshots',
        ],
    )
    def test_finds_either_onedrive_or_plain_pictures(
        self,
        users_root: Path,
        subpath: str,
    ) -> None:
        expected = users_root / 'danny' / subpath
        make_image(expected, 'a.png', 1)

        assert resolve(users_root, windows_username='danny') == expected

    def test_prefers_the_directory_holding_the_newest_screenshot(
        self,
        users_root: Path,
    ) -> None:
        """A OneDrive migration leaves a stale local dir behind."""
        stale = users_root / 'danny' / 'Pictures' / 'Screenshots'
        fresh = users_root / 'danny' / 'OneDrive' / 'Pictures' / 'Screenshots'
        make_image(stale, 'old.png', 1_000)
        make_image(fresh, 'new.png', 2_000)

        assert resolve(users_root, windows_username='danny') == fresh

    def test_discovers_the_user_when_username_is_unset(
        self,
        users_root: Path,
    ) -> None:
        expected = users_root / 'danny' / 'Pictures' / 'Screenshots'
        make_image(expected, 'a.png', 1)

        assert resolve(users_root) == expected

    @pytest.mark.parametrize('skipped', sorted(SKIPPED_WINDOWS_USERS))
    def test_skips_windows_system_profiles(
        self,
        users_root: Path,
        skipped: str,
    ) -> None:
        make_image(
            users_root / skipped / 'Pictures' / 'Screenshots',
            'a.png',
            2_000,
        )
        real = users_root / 'danny' / 'Pictures' / 'Screenshots'
        make_image(real, 'a.png', 1_000)

        assert resolve(users_root) == real

    def test_named_username_is_not_overridden_by_another_profile(
        self,
        users_root: Path,
    ) -> None:
        make_image(
            users_root / 'other' / 'Pictures' / 'Screenshots',
            'newer.png',
            2_000,
        )
        mine = users_root / 'danny' / 'Pictures' / 'Screenshots'
        make_image(mine, 'older.png', 1_000)

        assert resolve(users_root, windows_username='danny') == mine

    def test_empty_but_existing_directory_still_resolves(
        self,
        users_root: Path,
    ) -> None:
        expected = users_root / 'danny' / 'Pictures' / 'Screenshots'
        expected.mkdir(parents=True)

        assert resolve(users_root, windows_username='danny') == expected

    def test_no_candidate_directory_is_an_error(
        self,
        users_root: Path,
    ) -> None:
        users_root.mkdir(parents=True)

        with pytest.raises(ScreenshotError, match='No screenshots directory'):
            resolve(users_root)


class TestScreenshotPaths:
    def test_returns_newest_first(self, tmp_path: Path) -> None:
        make_image(tmp_path, 'old.png', 1_000)
        make_image(tmp_path, 'new.png', 3_000)
        make_image(tmp_path, 'mid.png', 2_000)

        names = [path.name for path in screenshot_paths(tmp_path)]

        assert names == ['new.png', 'mid.png', 'old.png']

    def test_ties_break_on_name_for_determinism(self, tmp_path: Path) -> None:
        make_image(tmp_path, 'b.png', 1_000)
        make_image(tmp_path, 'a.png', 1_000)

        names = [path.name for path in screenshot_paths(tmp_path)]

        assert names == ['b.png', 'a.png']

    @pytest.mark.parametrize('suffix', sorted(IMAGE_SUFFIXES))
    def test_accepts_every_supported_suffix(
        self,
        tmp_path: Path,
        suffix: str,
    ) -> None:
        make_image(tmp_path, f'shot{suffix}', 1_000)

        assert len(screenshot_paths(tmp_path)) == 1

    def test_suffix_match_is_case_insensitive(self, tmp_path: Path) -> None:
        make_image(tmp_path, 'shot.PNG', 1_000)

        assert len(screenshot_paths(tmp_path)) == 1

    def test_ignores_non_images_and_subdirectories(
        self,
        tmp_path: Path,
    ) -> None:
        make_image(tmp_path, 'shot.png', 1_000)
        (tmp_path / 'notes.txt').write_text('nope')
        (tmp_path / 'nested').mkdir()

        names = [path.name for path in screenshot_paths(tmp_path)]

        assert names == ['shot.png']

    def test_limit_truncates_to_the_newest_n(self, tmp_path: Path) -> None:
        for index in range(5):
            make_image(tmp_path, f'{index}.png', 1_000 + index)

        names = [path.name for path in screenshot_paths(tmp_path, limit=2)]

        assert names == ['4.png', '3.png']


class TestLatestScreenshot:
    def test_returns_the_newest_file(self, tmp_path: Path) -> None:
        make_image(tmp_path, 'old.png', 1_000)
        newest = make_image(tmp_path, 'new.png', 2_000)

        assert latest_screenshot(tmp_path) == newest

    def test_empty_directory_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ScreenshotError, match='No screenshots found'):
            latest_screenshot(tmp_path)


class TestCli:
    @pytest.fixture
    def populated(self, tmp_path: Path) -> Path:
        make_image(tmp_path, 'old.png', 1_000)
        make_image(tmp_path, 'new.png', 2_000)
        return tmp_path

    def run(
        self,
        *args: str,
        env_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, str(CLI), *args],
            capture_output=True,
            text=True,
            env={'SCREENSHOT_DIR': str(env_dir), 'PATH': '/usr/bin:/bin'},
            check=False,
        )

    def test_bare_invocation_prints_the_latest_path(
        self,
        populated: Path,
    ) -> None:
        result = self.run(env_dir=populated)

        assert result.returncode == 0
        assert result.stdout.strip() == str(populated / 'new.png')

    def test_dir_prints_the_resolved_directory(self, populated: Path) -> None:
        result = self.run('dir', env_dir=populated)

        assert result.returncode == 0
        assert result.stdout.strip() == str(populated)

    def test_list_prints_newest_first(self, populated: Path) -> None:
        result = self.run('list', env_dir=populated)

        assert result.returncode == 0
        assert result.stdout.splitlines() == [
            str(populated / 'new.png'),
            str(populated / 'old.png'),
        ]

    def test_list_honours_the_count_flag(self, populated: Path) -> None:
        result = self.run('list', '-n', '1', env_dir=populated)

        assert result.stdout.splitlines() == [str(populated / 'new.png')]

    def test_empty_directory_exits_nonzero_with_a_message(
        self,
        tmp_path: Path,
    ) -> None:
        result = self.run(env_dir=tmp_path)

        assert result.returncode == 1
        assert 'No screenshots found' in result.stderr
        assert not result.stdout.strip()
