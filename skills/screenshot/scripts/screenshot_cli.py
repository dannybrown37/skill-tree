#!/usr/bin/env python3
"""Locate Windows screenshots from WSL, newest first."""

import argparse
import os
import shutil
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


def free_destination(destination: Path) -> Path:
    """`destination`, suffixed until it names nothing that exists.

    Screenshot filenames collide easily -- Windows restarts its
    "Screenshot (N)" counter per directory -- and a move is not worth
    losing an older file over.
    """
    if not destination.exists():
        return destination

    for index in range(1, 1000):
        candidate = destination.with_name(
            f'{destination.stem}-{index}{destination.suffix}',
        )
        if not candidate.exists():
            return candidate

    message = f'Too many files named like {destination.name}'
    raise ScreenshotError(message)


def move_screenshots(
    paths: list[Path],
    destination_dir: Path,
) -> list[Path]:
    """Move `paths` into `destination_dir`, returning their new paths."""
    destination_dir = destination_dir.expanduser()
    if destination_dir.exists() and not destination_dir.is_dir():
        message = f'Not a directory: {destination_dir}'
        raise ScreenshotError(message)
    destination_dir.mkdir(parents=True, exist_ok=True)

    moved = []
    for path in paths:
        if not path.is_file():
            message = f'No such file: {path}'
            raise ScreenshotError(message)
        target = free_destination(destination_dir / path.name)
        # shutil.move, not Path.rename: the screenshots directory is on
        # /mnt/c and the destination usually is not, so this is a
        # cross-filesystem move more often than not.
        shutil.move(str(path), str(target))
        moved.append(target)
    return moved


def move_from_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    """Run the `move` action, printing each screenshot's new path."""
    if args.dest is None:
        parser.error('move requires --dest')
    if not args.paths:
        parser.error('move requires at least one path')

    try:
        for path in move_screenshots(args.paths, args.dest):
            print(path)
    except (ScreenshotError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Locate Windows screenshots from WSL, newest first.',
    )
    parser.add_argument(
        'action',
        nargs='?',
        default='latest',
        choices=('latest', 'list', 'dir', 'move'),
        help='latest (default): newest screenshot path; list: newest first; '
        'dir: the resolved screenshots directory; '
        'move: move the given screenshots into --dest',
    )
    parser.add_argument(
        'paths',
        nargs='*',
        type=Path,
        help='with move, the screenshots to move',
    )
    parser.add_argument(
        '-n',
        '--count',
        type=int,
        default=None,
        help='with list, show at most this many',
    )
    parser.add_argument(
        '--dest',
        type=Path,
        default=None,
        help='with move, the destination directory (created if missing)',
    )
    args = parser.parse_args()

    if args.action == 'move':
        move_from_args(parser, args)
        return

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
