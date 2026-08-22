#!/usr/bin/env python3
"""Backlog behind the handoff skill: work that isn't next yet.

One backlog per repo, beside the handoff's other two files, so the path is
the scope -- there are no cross-repo tags to keep straight.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKLOG_HEADER = '# Backlog'
BACKLOG_NAME = 'BACKLOG.md'
CURRENT_NAME = 'CURRENT.md'
DEFAULT_SUBDIR = Path('docs') / 'handoffs'
NARRATIVE_NAME = 'NARRATIVE.md'
FENCE_PREFIXES = ('```', '~~~')
PROJECTS_DIR_FALLBACK = Path('~/projects')
IN_PROGRESS = 'in-progress'
AWAITING_REVIEW = 'awaiting-review'
BETWEEN_TASKS = 'between-tasks'
STATUS_VALUES = (IN_PROGRESS, AWAITING_REVIEW, BETWEEN_TASKS)
NO_CURRENT = 'none'
STATUS_UNSET = 'unset'
STATUS_PATTERN = re.compile(
    r'^\s*(?:[-*]\s+)?\*{0,2}Status\*{0,2}:\*{0,2}\s*(\S.*?)\s*$',
    re.IGNORECASE,
)


class HandoffError(Exception):
    """Something the user asked for can't be done as asked."""


@dataclass(frozen=True)
class ProjectStatus:
    """One project's handoff state, as `status` reports it."""

    name: str
    path: Path
    has_handoff: bool
    status: str
    backlog_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            'name': self.name,
            'path': str(self.path),
            'has_handoff': self.has_handoff,
            'status': self.status,
            'backlog_count': self.backlog_count,
        }


@dataclass(frozen=True)
class BacklogItem:
    """One `## <title>` section and everything under it."""

    title: str
    body: str


def version() -> str:
    """This checkout's plugin version, or `unknown` outside one.

    `--version` has to work with no config and no credentials, so a missing
    or unreadable manifest is an answer rather than a crash.
    """
    manifest = (
        Path(__file__).resolve().parents[3] / '.claude-plugin' / 'plugin.json'
    )
    try:
        return str(json.loads(manifest.read_text())['version'])
    except (OSError, ValueError, KeyError):
        return 'unknown'


def parse_backlog_text(content: str) -> list[BacklogItem]:
    """Every `## ` section in a backlog file, in order.

    Fence-aware: pasted logs and markdown samples routinely contain a line
    starting with `## `, and splitting on one would tear an item in half.
    """
    items: list[BacklogItem] = []
    title: str | None = None
    body: list[str] = []
    fence: str | None = None

    def flush() -> None:
        if title is not None:
            items.append(BacklogItem(title, '\n'.join(body).strip()))

    for line in content.split('\n'):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
        elif stripped.startswith(FENCE_PREFIXES):
            fence = stripped[:3]
        elif line.startswith('## '):
            flush()
            title = line[3:].strip()
            body = []
            continue

        if title is not None:
            body.append(line)

    flush()
    return items


def _protect_body(body: str) -> str:
    """Fence a body that would otherwise parse as a new item.

    Pasted logs and markdown samples contain `## ` at column 0 often enough
    to matter, and an unfenced one silently tears the item in half on the
    next read. The fence is made longer than any backtick run already in the
    body, so a body that's *already* fenced nests correctly instead of
    closing early.
    """
    if not _has_bare_heading(body):
        return body

    longest = max(
        (len(run) for run in _backtick_runs(body)),
        default=0,
    )
    fence = '`' * max(3, longest + 1)
    return f'{fence}\n{body}\n{fence}'


def _has_bare_heading(body: str) -> bool:
    """A `## ` at column 0 and outside any fence.

    Fence-aware so re-rendering an already-protected body doesn't wrap it a
    second time on every write.
    """
    fence: str | None = None
    for line in body.split('\n'):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
        elif stripped.startswith(FENCE_PREFIXES):
            fence = stripped[:3]
        elif line.startswith('## '):
            return True
    return False


def _backtick_runs(text: str) -> list[str]:
    runs: list[str] = []
    current = ''
    for character in text:
        if character == '`':
            current += character
            continue
        if current:
            runs.append(current)
        current = ''
    if current:
        runs.append(current)
    return runs


def render_backlog(items: list[BacklogItem]) -> str:
    """Rebuild the whole file from items -- the only way it's ever written.

    Rendering rather than splicing means a malformed file is repaired by the
    first write instead of corrupted further by a string replace.
    """
    if not items:
        return f'{BACKLOG_HEADER}\n'

    sections = []
    for item in items:
        header = f'## {item.title}'
        body = _protect_body(item.body)
        sections.append(f'{header}\n\n{body}\n' if body else f'{header}\n')
    return f'{BACKLOG_HEADER}\n\n' + '\n'.join(sections)


def find_item(items: list[BacklogItem], title: str) -> BacklogItem | None:
    """Match a title loosely -- titles get retyped and shell-quoted."""
    target = title.strip().casefold()
    return next(
        (item for item in items if item.title.strip().casefold() == target),
        None,
    )


def handoff_dir(
    repo: Path | None = None,
    start: Path | None = None,
) -> Path:
    """Where this repo's handoff files live.

    `--repo` beats `$HANDOFF_DIR` beats walking up to the git root, so an
    explicit path is always the last word.
    """
    if repo is not None:
        return repo.expanduser().resolve() / DEFAULT_SUBDIR

    override = os.environ.get('HANDOFF_DIR')
    if override:
        return Path(override).expanduser()

    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if (directory / '.git').exists():
            return directory / DEFAULT_SUBDIR

    message = (
        f'not inside a git repo (looked up from {current}). '
        f'Pass --repo <path>, or set $HANDOFF_DIR.'
    )
    raise HandoffError(message)


def backlog_path(repo: Path | None = None) -> Path:
    return handoff_dir(repo) / BACKLOG_NAME


def read_items(path: Path) -> list[BacklogItem]:
    if not path.exists():
        return []
    return parse_backlog_text(path.read_text())


def write_items(path: Path, items: list[BacklogItem]) -> None:
    """Replace the backlog atomically -- `pop` mutates two files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.tmp')
    temporary.write_text(render_backlog(items))
    temporary.replace(path)


def add_item(
    path: Path,
    title: str,
    body: str,
    *,
    to_top: bool = False,
) -> BacklogItem:
    if not title.strip():
        message = 'an item needs a title'
        raise HandoffError(message)

    item = BacklogItem(title.strip(), body.strip())
    items = read_items(path)
    write_items(path, [item, *items] if to_top else [*items, item])
    return item


def remove_item(path: Path, title: str) -> BacklogItem:
    items = read_items(path)
    item = find_item(items, title)
    if item is None:
        message = f'no backlog item titled {title!r}'
        raise HandoffError(message)

    write_items(path, [other for other in items if other is not item])
    return item


NEXT_ACTION_HEADING = '## Next action'

# The H1 names the thread, not the item -- a later pop replaces the next
# action underneath it, and a stale item title left in the heading is exactly
# the "describes a world that's gone" failure this skill warns about.
CURRENT_SKELETON = """\
# Continue here

**Status:** in-progress

You are continuing a session that ended with a handoff. Reconstruct context
from the files below, then do the next action.

## Read in this order

1. `NARRATIVE.md` -- what was tried, decided, and finished
2. <the code this touches>

{section}
"""


def _section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    """Where `heading`'s section starts and ends, or None if it's absent.

    Fence-aware for the same reason the backlog parser is: a `## ` inside a
    fenced example is not the end of the section.
    """
    target = heading.casefold()
    start: int | None = None
    fence: str | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith(FENCE_PREFIXES):
            fence = stripped[:3]
            continue
        if not line.startswith('## '):
            continue
        if start is None and stripped.casefold() == target:
            start = index
        elif start is not None:
            return (start, index)

    return None if start is None else (start, len(lines))


def _render_next_action(item: BacklogItem) -> str:
    body = _protect_body(item.body)
    parts = [NEXT_ACTION_HEADING, '', item.title]
    if body:
        parts += ['', body]
    return '\n'.join(parts)


def write_next_action(current_path: Path, item: BacklogItem) -> None:
    """Put `item` in CURRENT.md's next-action slot, replacing what's there.

    Replacing rather than appending is the whole point -- a re-entry prompt
    with two "next action" sections is worse than one that's out of date,
    because nothing says which one is live.
    """
    section = _render_next_action(item)

    if not current_path.exists():
        text = CURRENT_SKELETON.format(section=section)
    else:
        lines = current_path.read_text().split('\n')
        bounds = _section_bounds(lines, NEXT_ACTION_HEADING)
        if bounds is None:
            text = current_path.read_text().rstrip() + f'\n\n{section}\n'
        else:
            start, end = bounds
            replacement = [*section.split('\n'), '']
            text = '\n'.join([*lines[:start], *replacement, *lines[end:]])

    current_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = current_path.with_name(f'.{current_path.name}.tmp')
    temporary.write_text(text.rstrip() + '\n')
    temporary.replace(current_path)


def pop_item(path: Path, current_path: Path) -> BacklogItem | None:
    """Claim the top backlog item: out of BACKLOG.md, into CURRENT.md.

    One operation, because the skill's whole guarantee is that CURRENT.md
    reflects the live work -- an item that left the backlog without landing
    there is work nobody can find again.
    """
    items = read_items(path)
    if not items:
        return None

    item = items[0]
    write_next_action(current_path, item)
    set_status(current_path, IN_PROGRESS)
    write_items(path, items[1:])
    return item


def _normalise_status(raw: str) -> str | None:
    """A written status word, or None if it isn't one we recognise.

    Accepting `in progress` alongside `in-progress` matters because this line
    is usually written by hand mid-session, and a typo that silently reads as
    "no status" is worse than none at all.
    """
    cleaned = raw.strip().strip('*`_').strip().casefold().replace(' ', '-')
    return cleaned if cleaned in STATUS_VALUES else None


def parse_status(text: str) -> str | None:
    """The `**Status:**` keyword in a CURRENT.md, or None if it's absent.

    Fence-aware, so the example line in the skill's own template doesn't read
    as that project's real status.
    """
    fence: str | None = None
    for line in text.split('\n'):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith(FENCE_PREFIXES):
            fence = stripped[:3]
            continue
        match = STATUS_PATTERN.match(line)
        if match is None:
            continue
        status = _normalise_status(match.group(1))
        if status is not None:
            return status
    return None


def _status_line_index(lines: list[str]) -> int | None:
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith(FENCE_PREFIXES):
            fence = stripped[:3]
            continue
        if STATUS_PATTERN.match(line):
            return index
    return None


def set_status(current_path: Path, status: str) -> None:
    """Write the status keyword into CURRENT.md, replacing any existing one."""
    if status not in STATUS_VALUES:
        allowed = ', '.join(STATUS_VALUES)
        message = f'unknown status {status!r} -- use {allowed}'
        raise HandoffError(message)
    if not current_path.exists():
        message = f'no CURRENT.md at {current_path}'
        raise HandoffError(message)

    lines = current_path.read_text().split('\n')
    rendered = f'**Status:** {status}'
    index = _status_line_index(lines)
    if index is not None:
        lines[index] = rendered
    else:
        after_title = 1 if lines and lines[0].startswith('# ') else 0
        lines[after_title:after_title] = (
            ['', rendered] if after_title else [rendered, '']
        )

    temporary = current_path.with_name(f'.{current_path.name}.tmp')
    temporary.write_text('\n'.join(lines).rstrip() + '\n')
    temporary.replace(current_path)


def default_project_root() -> Path:
    """Where projects live: `$PROJECTS_DIR`, same as the wrapper's picker."""
    return Path(os.environ.get('PROJECTS_DIR') or PROJECTS_DIR_FALLBACK)


def project_status(project: Path) -> ProjectStatus:
    directory = project / DEFAULT_SUBDIR
    current = directory / CURRENT_NAME
    if current.exists():
        status = parse_status(current.read_text()) or STATUS_UNSET
    else:
        status = NO_CURRENT
    return ProjectStatus(
        name=project.name,
        path=project,
        has_handoff=directory.is_dir(),
        status=status,
        backlog_count=len(read_items(directory / BACKLOG_NAME)),
    )


def scan_projects(roots: list[Path]) -> list[ProjectStatus]:
    """Every git repo one level under `roots`, with its handoff state.

    One level only: `~/projects/*` is the shape this answers for, and walking
    deeper turns a status check into a filesystem crawl through node_modules.
    """
    reports: dict[Path, ProjectStatus] = {}
    for root in roots:
        expanded = root.expanduser()
        if not expanded.is_dir():
            continue
        for entry in expanded.iterdir():
            if entry.is_dir() and (entry / '.git').exists():
                reports[entry.resolve()] = project_status(entry)
    return sorted(
        reports.values(),
        key=lambda report: (report.name, str(report.path)),
    )


def _render_status_table(reports: list[ProjectStatus]) -> str:
    headers = ('PROJECT', 'HANDOFF', 'STATUS', 'BACKLOG')
    rows = [
        (
            report.name,
            'yes' if report.has_handoff else 'no',
            report.status,
            str(report.backlog_count),
        )
        for report in reports
    ]
    columns = zip(headers, *rows, strict=True)
    widths = [max(len(cell) for cell in column) for column in columns]
    lines = [
        '  '.join(
            cell.ljust(width) for cell, width in zip(row, widths, strict=True)
        ).rstrip()
        for row in (headers, *rows)
    ]
    return '\n'.join(lines)


def cmd_status(_path: Path, args: argparse.Namespace) -> int:
    if args.set is not None:
        current = handoff_dir(args.repo) / CURRENT_NAME
        set_status(current, args.set)
        print(f'{current}: {args.set}')
        return 0

    roots = args.root or [default_project_root()]
    reports = scan_projects(roots)
    if args.json:
        print(json.dumps([report.as_dict() for report in reports], indent=2))
        return 0
    if not reports:
        listed = ', '.join(str(root) for root in roots)
        print(f'No projects found under {listed}.')
        return 0
    print(_render_status_table(reports))
    return 0


def cmd_add(path: Path, args: argparse.Namespace) -> int:
    item = add_item(
        path,
        args.title,
        args.body or '',
        to_top=args.action == 'next',
    )
    where = 'top' if args.action == 'next' else 'bottom'
    print(f'Added to the {where} of {path}: {item.title}')
    return 0


def _require_item(path: Path, title: str | None) -> BacklogItem:
    """Resolve `--item-title`, or fail with the list of what's available.

    Picking interactively is the wrapper's job (it has the terminal); here a
    missing title is an error that has to say what the choices were.
    """
    items = read_items(path)
    if title is None:
        listing = '\n'.join(f'  {item.title}' for item in items)
        message = (
            f'--item-title is required here. Available:\n{listing}'
            if items
            else f'the backlog is empty ({path})'
        )
        raise HandoffError(message)

    item = find_item(items, title)
    if item is None:
        message = f'no backlog item titled {title!r}'
        raise HandoffError(message)
    return item


def cmd_remove(path: Path, args: argparse.Namespace) -> int:
    item = _require_item(path, args.item_title)
    remove_item(path, item.title)
    print(f'Removed: {item.title}')
    return 0


def cmd_pop(path: Path, _args: argparse.Namespace) -> int:
    """Claim the top item and print it -- the agent-facing command.

    Silence on an empty backlog is deliberate: the session-start hook runs
    this on every session, and "nothing queued" is a normal state, not a
    failure worth spending the agent's attention on.
    """
    item = pop_item(path, path.with_name(CURRENT_NAME))
    if item is None:
        return 0

    print(f'## {item.title}\n')
    if item.body:
        print(f'{item.body}\n')
    print(
        f'(Claimed from {path} and written to '
        f'{path.with_name(CURRENT_NAME)} as the next action.)',
    )
    return 0


def cmd_path(path: Path, _args: argparse.Namespace) -> int:
    """Where the backlog is, creating it if this repo has none yet.

    `handoff edit` needs a file to open, and "there isn't one yet" is the
    normal state the first time a repo grows a backlog.
    """
    if not path.exists():
        write_items(path, [])
    print(path)
    return 0


def _cmd_doc(
    path: Path,
    args: argparse.Namespace,
    name: str,
) -> int:
    """Print one of the handoff's prose files, or say where it is.

    Paging is the wrapper's job -- this side runs from hooks and tool calls
    with no terminal, where a pager would hang.
    """
    document = path.with_name(name)
    if args.path:
        print(document)
        return 0
    if not document.exists():
        message = f'no {name} in {document.parent}'
        raise HandoffError(message)
    print(document.read_text().rstrip())
    return 0


def cmd_current(path: Path, args: argparse.Namespace) -> int:
    return _cmd_doc(path, args, CURRENT_NAME)


def cmd_narrative(path: Path, args: argparse.Namespace) -> int:
    return _cmd_doc(path, args, NARRATIVE_NAME)


def cmd_backlog(path: Path, args: argparse.Namespace) -> int:
    """The backlog itself: the whole file, or bare titles for a picker."""
    if args.titles:
        for item in read_items(path):
            print(item.title)
        return 0
    return _cmd_doc(path, args, BACKLOG_NAME)


HANDLERS = {
    'pop': cmd_pop,
    'backlog': cmd_backlog,
    'current': cmd_current,
    'narrative': cmd_narrative,
    'path': cmd_path,
    'add': cmd_add,
    'next': cmd_add,
    'remove': cmd_remove,
    'status': cmd_status,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='handoff',
        description=__doc__,
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'handoff {version()}',
    )
    actions = parser.add_subparsers(dest='action', required=True)

    def add_action(name: str, help_text: str) -> argparse.ArgumentParser:
        action = actions.add_parser(name, help=help_text)
        action.add_argument(
            '--repo',
            type=Path,
            help='repo root to act on (default: the one containing cwd)',
        )
        return action

    add_action(
        'pop',
        "Claim the top item: remove it and make it CURRENT.md's next action",
    )
    add_action('path', "Path to this repo's BACKLOG.md, creating it if new")
    for name, help_text in (
        ('backlog', "Print this repo's BACKLOG.md"),
        ('current', "Print this repo's CURRENT.md"),
        ('narrative', "Print this repo's NARRATIVE.md"),
    ):
        action = add_action(name, help_text)
        action.add_argument(
            '--path',
            action='store_true',
            help='print the file path instead of its contents',
        )
        if name == 'backlog':
            action.add_argument(
                '--titles',
                action='store_true',
                help='bare titles, one per line (what a picker reads)',
            )

    for name, help_text in (
        ('add', 'Add an item to the bottom -- do this eventually'),
        ('next', 'Add an item to the top -- do this next'),
    ):
        action = add_action(name, help_text)
        action.add_argument('--title', required=True)
        action.add_argument('--body', default='')

    remove = add_action('remove', 'Delete an item')
    remove.add_argument('--item-title')

    status = add_action(
        'status',
        "Handoff state of every project under a root, or set this one's",
    )
    status.add_argument(
        '--root',
        type=Path,
        action='append',
        help='project directory to scan, repeatable (default: $PROJECTS_DIR)',
    )
    status.add_argument(
        '--json',
        action='store_true',
        help='machine-readable output',
    )
    status.add_argument(
        '--set',
        choices=STATUS_VALUES,
        help="set this repo's CURRENT.md status instead of scanning",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == 'status':
            return cmd_status(Path(), args)
        path = backlog_path(args.repo)
        return HANDLERS[args.action](path, args)
    except HandoffError as error:
        print(f'handoff: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
