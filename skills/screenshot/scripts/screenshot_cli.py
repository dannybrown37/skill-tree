#!/usr/bin/env python3
"""Locate Windows screenshots from WSL, newest first."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
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


POWERSHELL = 'powershell.exe'
CLIP = 'clip.exe'

# Windows' own naming, so a captured file sorts and reads like one taken
# with Win+PrtScn. The spaces are deliberate -- they're the reason every
# path this CLI prints to a terminal is shell-quoted.
CAPTURE_NAME_FORMAT = 'Screenshot %Y-%m-%d %H%M%S.png'

# VirtualScreen, not PrimaryScreen: a multi-monitor desktop should come out
# whole rather than silently cropped to whichever monitor Windows calls
# first. `$OutPath` is prepended by powershell_string_literal -- `-Command`
# has no way to take arguments (anything after it is appended to the command
# text, not bound to a param block), so the path has to be part of the
# script text.
CAPTURE_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
try {
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen(
            $bounds.Location,
            [System.Drawing.Point]::Empty,
            $bounds.Size
        )
    } finally { $graphics.Dispose() }
    $bitmap.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally { $bitmap.Dispose() }
"""

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def powershell_string_literal(value: str) -> str:
    """`value` as a PowerShell single-quoted literal.

    Single quotes don't interpolate in PowerShell, so `$` and backticks are
    inert inside them; doubling an embedded quote is the whole escape.
    """
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def windows_path(path: Path) -> str:
    """`path` as Windows sees it, for handing to PowerShell."""
    result = run_command(['wslpath', '-w', str(path)])
    if result.returncode != 0:
        message = (
            f'Could not translate {path} to a Windows path: '
            f'{result.stderr.strip() or "wslpath failed"}'
        )
        raise ScreenshotError(message)
    return result.stdout.strip()


def capture_screen(
    directory: Path,
    now: datetime | None = None,
    runner: Runner = run_command,
) -> Path:
    """Capture the whole Windows desktop into `directory`."""
    if shutil.which(POWERSHELL) is None:
        message = (
            f'{POWERSHELL} not found -- capturing needs Windows interop, '
            f'so this only works from WSL.'
        )
        raise ScreenshotError(message)

    directory.mkdir(parents=True, exist_ok=True)
    stamp = now or datetime.now().astimezone()
    target = free_destination(directory / stamp.strftime(CAPTURE_NAME_FORMAT))

    assignment = (
        f'$OutPath = {powershell_string_literal(windows_path(target))}'
    )
    result = runner(
        [
            POWERSHELL,
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            f'{assignment}\n{CAPTURE_SCRIPT}',
        ],
    )
    if result.returncode != 0:
        message = f'Capture failed: {result.stderr.strip() or "no output"}'
        raise ScreenshotError(message)
    if not target.is_file():
        message = f'Capture reported success but wrote nothing to {target}'
        raise ScreenshotError(message)
    return target


def copy_to_clipboard(text: str) -> None:
    """Best-effort copy to the Windows clipboard.

    A missing clip.exe means this isn't WSL, which is a fine reason to have
    no clipboard and a bad reason to fail a capture that already succeeded.
    """
    if shutil.which(CLIP) is None:
        return
    try:
        subprocess.run(  # noqa: S603
            [CLIP],
            input=text,
            text=True,
            check=False,
            capture_output=True,
        )
    except OSError:
        return


def emit_path(path: Path, *, clipboard: bool = True) -> None:
    """Print `path`, shell-quoted and copied when a human is reading.

    Screenshot filenames contain spaces, so an interactive user wants
    something they can paste straight into a command. A pipe wants the raw
    path -- `pick`'s fzf list and any agent calling this would otherwise
    have to unquote it.
    """
    if not sys.stdout.isatty():
        print(path)
        return

    quoted = shlex.quote(str(path))
    if clipboard:
        copy_to_clipboard(quoted)
    print(quoted)


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
        moved = move_screenshots(args.paths, args.dest)
        for path in moved:
            emit_path(path, clipboard=len(moved) == 1)
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
        default='take',
        choices=('take', 'latest', 'list', 'dir', 'move'),
        help='take (default): capture the screen, print the new file; '
        'latest: newest screenshot path; list: newest first; '
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

        if args.action == 'take':
            print("Took screenshot, it's at:", file=sys.stderr)
            emit_path(capture_screen(directory))
            return

        if args.action == 'dir':
            emit_path(directory, clipboard=False)
            return

        if args.action == 'latest':
            emit_path(latest_screenshot(directory))
            return

        paths = screenshot_paths(directory, limit=args.count)
        if not paths:
            message = f'No screenshots found in {directory}'
            raise ScreenshotError(message)  # noqa: TRY301
        for path in paths:
            emit_path(path, clipboard=False)
    except (ScreenshotError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
