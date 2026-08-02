#!/usr/bin/env python3
"""Locate Windows screenshots from WSL, newest first."""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_USERS_ROOT = Path('/mnt/c/Users')

# Relative to a Windows user profile. OneDrive's "back up my Pictures"
# setting silently redirects the Screenshots folder, so both have to be
# probed -- and a machine that was migrated keeps a stale copy of the other.
SCREENSHOT_SUBPATHS = (
    Path('OneDrive') / 'Pictures' / 'Screenshots',
    Path('Pictures') / 'Screenshots',
)

# Windows ships profiles nobody takes screenshots into; without this a
# system profile's directory can win the "newest file" tiebreak.
SKIPPED_WINDOWS_USERS = frozenset(
    {'All Users', 'Default', 'Default User', 'Public'},
)

IMAGE_SUFFIXES = frozenset(
    {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'},
)

NO_SCREENSHOTS_YET = float('-inf')


class ScreenshotError(Exception):
    """A screenshot directory or file could not be found."""


def user_profiles(
    users_root: Path,
    windows_username: str | None,
) -> list[Path]:
    """Windows profiles to search, most likely first."""
    if windows_username:
        named = users_root / windows_username
        if named.is_dir():
            return [named]

    if not users_root.is_dir():
        return []

    return sorted(
        profile
        for profile in users_root.iterdir()
        if profile.is_dir() and profile.name not in SKIPPED_WINDOWS_USERS
    )


def candidate_dirs(
    users_root: Path,
    windows_username: str | None,
) -> list[Path]:
    profiles = user_profiles(users_root, windows_username)
    return [
        candidate
        for profile in profiles
        for subpath in SCREENSHOT_SUBPATHS
        if (candidate := profile / subpath).is_dir()
    ]


def newest_mtime(directory: Path) -> float:
    paths = screenshot_paths(directory, limit=1)
    return paths[0].stat().st_mtime if paths else NO_SCREENSHOTS_YET


def resolve_screenshot_dir(
    override: str | None,
    users_root: Path,
    windows_username: str | None,
) -> Path:
    """Directory holding this machine's screenshots.

    An explicit override is taken as-is; otherwise the candidate holding
    the most recent screenshot wins, so a stale pre-OneDrive directory
    never shadows the one actually being written to.
    """
    if override:
        directory = Path(override).expanduser()
        if not directory.is_dir():
            message = f'Not a directory: {directory}'
            raise ScreenshotError(message)
        return directory

    candidates = candidate_dirs(users_root, windows_username)
    if not candidates:
        message = (
            f'No screenshots directory under {users_root}. '
            f'Set SCREENSHOT_DIR to point at one.'
        )
        raise ScreenshotError(message)

    return max(
        candidates,
        key=lambda candidate: (
            newest_mtime(candidate),
            -candidates.index(candidate),
        ),
    )


def screenshot_paths(directory: Path, limit: int | None = None) -> list[Path]:
    """Image files in `directory`, newest first."""
    images = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    images.sort(
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    return images[:limit] if limit is not None else images


def latest_screenshot(directory: Path) -> Path:
    paths = screenshot_paths(directory, limit=1)
    if not paths:
        message = f'No screenshots found in {directory}'
        raise ScreenshotError(message)
    return paths[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Locate Windows screenshots from WSL, newest first.',
    )
    parser.add_argument(
        'action',
        nargs='?',
        default='latest',
        choices=('latest', 'list', 'dir'),
        help='latest (default): newest screenshot path; list: newest first; '
        'dir: the resolved screenshots directory',
    )
    parser.add_argument(
        '-n',
        '--count',
        type=int,
        default=None,
        help='with list, show at most this many',
    )
    args = parser.parse_args()

    try:
        directory = resolve_screenshot_dir(
            override=os.environ.get('SCREENSHOT_DIR'),
            users_root=Path(
                os.environ.get('WINDOWS_USERS_ROOT', DEFAULT_USERS_ROOT),
            ),
            windows_username=os.environ.get('WINDOWS_USERNAME'),
        )

        if args.action == 'dir':
            print(directory)
            return

        if args.action == 'latest':
            print(latest_screenshot(directory))
            return

        paths = screenshot_paths(directory, limit=args.count)
        if not paths:
            message = f'No screenshots found in {directory}'
            raise ScreenshotError(message)  # noqa: TRY301
        for path in paths:
            print(path)
    except ScreenshotError as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
