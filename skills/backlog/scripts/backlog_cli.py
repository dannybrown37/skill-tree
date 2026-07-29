#!/usr/bin/env python3
"""Backlog management for AI-assisted work items."""

import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import argparse

IN_PROGRESS_MARKER = ' [in-progress]'
MAX_COMPLETED_CONTENT_LINES = 50
BACKLOG_HEADER = '# Backlog'
COMPLETE_HEADER = '# Completed'

# One backlog serves every repo, so it lives outside all of them.
DEFAULT_BACKLOG_HOME = Path.home() / '.claude' / 'backlog'

REPO_TAG_PATTERN = re.compile(r'^\[([^\[\]]+)\]\s*(\S.*)$')
WORKTREE_GITDIR_PATTERN = re.compile(r'^gitdir:\s*(.+?)/\.git/worktrees/')

MergePreference = Literal['local', 'incoming']


def backlog_home() -> Path:
    """Directory holding the shared backlog files."""
    override = os.environ.get('BACKLOG_HOME')
    return Path(override).expanduser() if override else DEFAULT_BACKLOG_HOME


def default_backlog_path() -> Path:
    return backlog_home() / 'backlog'


def default_complete_path() -> Path:
    return backlog_home() / 'backlog-complete'


def parse_repo_tag(title: str) -> tuple[str | None, str]:
    """Split a leading `[repo]` tag off a title. The tag is optional."""
    match = REPO_TAG_PATTERN.match(title)
    if not match:
        return (None, title)
    return (match.group(1), match.group(2))


def repo_name_from_git_entry(git_entry: Path) -> str:
    """Repo name for a `.git` dir, or for a worktree's `.git` pointer file.

    A worktree directory is named for its branch, not for the repo tags name
    it by, so the pointer has to be followed to get a matching name.
    """
    if git_entry.is_file():
        match = WORKTREE_GITDIR_PATTERN.match(git_entry.read_text().strip())
        if match:
            return Path(match.group(1)).name
    return git_entry.parent.name


def current_repo_name(start: Path | None = None) -> str | None:
    """Name of the repo containing `start`, or None outside a repo."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        git_entry = directory / '.git'
        if git_entry.exists():
            return repo_name_from_git_entry(git_entry)
    return None


class BacklogItem:
    """A single work item from the backlog."""

    def __init__(
        self,
        title: str,
        content: str,
        raw_section: str = '',
    ) -> None:
        self.title = title
        self.content = content
        self.raw_section = raw_section

    @property
    def in_progress(self) -> bool:
        return self.title.endswith(IN_PROGRESS_MARKER.strip())

    @property
    def repo(self) -> str | None:
        """The repo this item is tagged for, if it names one at all."""
        return parse_repo_tag(strip_in_progress_marker(self.title))[0]

    def __repr__(self) -> str:
        lines = self.content.split('\n')
        preview = lines[0][:60] if lines else ''
        return f'{self.title}\n  {preview}...'


def strip_in_progress_marker(title: str) -> str:
    """Drop the trailing in-progress marker, if present, from a title."""
    marker = IN_PROGRESS_MARKER.strip()
    if title.endswith(marker):
        return title[: -len(marker)].rstrip()
    return title


def filter_items_for_repo(
    items: list[BacklogItem],
    repo: str | None,
) -> tuple[list[BacklogItem], int]:
    """Keep items for `repo` plus untagged ones; also count what was hidden.

    An untagged item is work that isn't tied to a repo, so it stays visible
    everywhere rather than being stranded in whichever repo it was written in.
    """
    if repo is None:
        return (items, 0)

    visible = [
        item
        for item in items
        if item.repo is None or item.repo.casefold() == repo.casefold()
    ]
    return (visible, len(items) - len(visible))


def filter_untagged_items(
    items: list[BacklogItem],
) -> tuple[list[BacklogItem], int]:
    """Keep items with no `[repo]` tag; also count what was hidden.

    Used by the tag picker's default view, so retagging doesn't accidentally
    land on something that's already tagged for a repo.
    """
    visible = [item for item in items if item.repo is None]
    return (visible, len(items) - len(visible))


def find_item(items: list[BacklogItem], title: str) -> BacklogItem | None:
    """Find an item by title, ignoring whether it's marked in-progress."""
    target = strip_in_progress_marker(title)
    return next(
        (
            item
            for item in items
            if strip_in_progress_marker(item.title) == target
        ),
        None,
    )


def parse_backlog_file(file_path: Path) -> list[BacklogItem]:
    """Parse .backlog markdown file and extract items under ## headers."""
    if not file_path.exists():
        return []

    return parse_backlog_text(file_path.read_text())


def parse_backlog_text(content: str) -> list[BacklogItem]:
    """Extract items under ## headers from backlog-formatted markdown."""
    lines = content.split('\n')

    items = []
    current_title = None
    current_content = []
    current_raw_lines = []

    def finalize_current_item() -> None:
        item_content = '\n'.join(current_content).strip()
        raw_section = '\n'.join(current_raw_lines)
        items.append(BacklogItem(current_title, item_content, raw_section))

    for line in lines:
        if line.startswith('## '):
            if current_title is not None:
                finalize_current_item()
            current_title = line[3:].strip()
            current_content = []
            current_raw_lines = [line]
        elif current_title is not None:
            current_content.append(line)
            current_raw_lines.append(line)

    if current_title is not None:
        finalize_current_item()

    return items


def render_backlog(items: list[BacklogItem]) -> str:
    """Rebuild a .backlog file from items, dropping merge-time whitespace."""
    sections = []
    for item in items:
        content = item.content.strip()
        header = f'## {item.title}'
        sections.append(
            f'{header}\n\n{content}\n' if content else f'{header}\n',
        )

    if not sections:
        return f'{BACKLOG_HEADER}\n'
    return f'{BACKLOG_HEADER}\n\n' + '\n'.join(sections)


def render_completed(items: list[BacklogItem]) -> str:
    """Rebuild a .backlog-complete file; content already has its own rules."""
    if not items:
        return f'{COMPLETE_HEADER}\n\n'

    sections = [f'## {item.title}\n{item.content.strip()}\n' for item in items]
    return f'{COMPLETE_HEADER}\n\n' + '\n'.join(sections)


def index_by_title(items: list[BacklogItem]) -> dict[str, BacklogItem]:
    """Map normalized title to item, keeping the first of any duplicates."""
    indexed: dict[str, BacklogItem] = {}
    for item in items:
        indexed.setdefault(strip_in_progress_marker(item.title), item)
    return indexed


def merge_backlog_text(
    local_text: str,
    incoming_text: str,
    tombstones: set[str],
    prefer: MergePreference,
) -> str:
    """Union both sides by title, minus anything already completed.

    Items on both sides follow the preferred side's order and body; items on
    only one side are appended in title order so that two machines merging the
    same pair of files land on byte-identical output and stop churning the
    password-store.
    """
    local = index_by_title(parse_backlog_text(local_text))
    incoming = index_by_title(parse_backlog_text(incoming_text))
    primary, secondary = (
        (local, incoming) if prefer == 'local' else (incoming, local)
    )

    shared = [title for title in primary if title in secondary]
    exclusive = sorted(local.keys() ^ incoming.keys())

    merged = []
    for title in shared + exclusive:
        if title in tombstones:
            continue
        source = primary.get(title) or secondary[title]
        # A stray "## " typed into either file parses as a titleless item;
        # propagating it would put a blank line in front of the fzf picker.
        if not title and not source.content.strip():
            continue
        claimed = any(
            side[title].in_progress
            for side in (local, incoming)
            if title in side
        )
        header = f'{title}{IN_PROGRESS_MARKER}' if claimed else title
        merged.append(BacklogItem(header, source.content))

    return render_backlog(merged)


def completed_record_key(item: BacklogItem) -> tuple[str, str]:
    """Identify a completion by title plus the stamp backlog_cli.py wrote."""
    match = re.search(r'^- Completed: (.+)$', item.content, re.MULTILINE)
    stamp = match.group(1).strip() if match else ''
    return (strip_in_progress_marker(item.title), stamp)


def merge_completed_text(local_text: str, incoming_text: str) -> str:
    """Union the two completion logs, ordered by when work finished."""
    records: dict[tuple[str, str], BacklogItem] = {}
    for item in parse_backlog_text(local_text) + parse_backlog_text(
        incoming_text,
    ):
        records.setdefault(completed_record_key(item), item)

    ordered = sorted(records, key=lambda key: (key[1], key[0]))
    return render_completed([records[key] for key in ordered])


def completed_titles(complete_path: Path) -> set[str]:
    """Titles that have been completed anywhere -- the merge's tombstones."""
    return {
        strip_in_progress_marker(item.title)
        for item in parse_backlog_file(complete_path)
    }


def read_if_present(file_path: Path) -> str:
    """Read a sync participant that may not exist on this machine yet."""
    return file_path.read_text() if file_path.exists() else ''


def remove_item_from_backlog(backlog_path: Path, item: BacklogItem) -> None:
    """Remove an item from the backlog file."""
    if not backlog_path.exists():
        return

    content = backlog_path.read_text()
    updated = content.replace(item.raw_section, '', 1)
    updated = re.sub(r'\n{3,}', '\n\n', updated).strip()
    backlog_path.write_text(updated + '\n')


def trim_content(
    content: str,
    max_lines: int = MAX_COMPLETED_CONTENT_LINES,
) -> str:
    """Cap content at max_lines and note the trim so it's unambiguous."""
    lines = content.split('\n')
    if len(lines) <= max_lines:
        return content

    kept = '\n'.join(lines[:max_lines])
    note = f'_[Trimmed from {len(lines)} to {max_lines} lines]_'
    return f'{kept}\n\n{note}'


def add_to_completed(
    complete_path: Path,
    item: BacklogItem,
    end_time: datetime,
) -> None:
    """Add completed item to .backlog-complete with a completion timestamp."""
    if not complete_path.exists():
        complete_path.write_text('# Completed\n\n')

    existing = complete_path.read_text()

    end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    title = strip_in_progress_marker(item.title)

    entry = f"""## {title}
- Completed: {end_str}

{trim_content(item.content)}

---

"""

    new_content = existing.rstrip() + '\n\n' + entry
    complete_path.write_text(new_content)


def replace_item_header(
    backlog_path: Path,
    item: BacklogItem,
    new_title: str,
) -> None:
    """Swap an item's `## title` line for a new title; body stays untouched."""
    content = backlog_path.read_text()
    old_header = f'## {item.title}'
    new_header = f'## {new_title}'
    new_raw_section = new_header + item.raw_section[len(old_header) :]
    updated = content.replace(item.raw_section, new_raw_section, 1)
    backlog_path.write_text(updated)


def mark_item_in_progress(backlog_path: Path, item: BacklogItem) -> None:
    """Append the in-progress marker to an item's header in .backlog."""
    replace_item_header(
        backlog_path,
        item,
        f'{item.title}{IN_PROGRESS_MARKER}',
    )


def set_item_repo_tag(
    backlog_path: Path,
    item: BacklogItem,
    repo: str | None,
) -> str:
    """Set, replace, or (if repo is None) remove an item's `[repo]` tag.

    Returns the new title.
    """
    suffix = IN_PROGRESS_MARKER if item.in_progress else ''
    bare_title = parse_repo_tag(strip_in_progress_marker(item.title))[1]
    prefix = f'[{repo}] ' if repo else ''
    new_title = f'{prefix}{bare_title}{suffix}'

    replace_item_header(backlog_path, item, new_title)
    return new_title


def visible_items(
    backlog_path: Path | None,
    repo: str | None,
) -> tuple[list[BacklogItem], int]:
    """Backlog items the given repo should see, plus the hidden count."""
    items = parse_backlog_file(backlog_path or default_backlog_path())
    return filter_items_for_repo(items, repo)


def get_next_item(
    backlog_path: Path | None = None,
    repo: str | None = None,
) -> BacklogItem | None:
    """Get the first item the given repo should see."""
    items, _ = visible_items(backlog_path, repo)
    return items[0] if items else None


def list_items(
    backlog_path: Path | None = None,
    limit: int = 5,
    repo: str | None = None,
) -> list[BacklogItem]:
    """Get first N items the given repo should see."""
    items, _ = visible_items(backlog_path, repo)
    return items[:limit]


def list_titles(backlog_path: Path, repo: str | None = None) -> list[str]:
    """Every visible title, one per item, for an external picker to offer."""
    items, _ = visible_items(backlog_path, repo)
    return [item.title for item in items]


def show_item(item: BacklogItem) -> None:
    """Display an item for review."""
    print(f'\n{"=" * 70}')
    print(f'📋 {item.title}')
    print(f'{"=" * 70}')
    print(item.content)
    print(f'{"=" * 70}\n')


def hidden_note(
    hidden: int,
    action: str,
    reason: str = 'for other repos',
) -> str:
    """Say what a filter left out, so nothing vanishes silently."""
    return f'({hidden} hidden {reason} — `backlog {action} --all`)'


def action_next(backlog_path: Path, repo: str | None = None) -> None:
    """Show next item for discussion."""
    items, hidden = visible_items(backlog_path, repo)
    if items:
        show_item(items[0])
        print(f'Proceed with: {items[0].title}? (y/n)')
    else:
        print('✓ Backlog is empty!')
    if hidden:
        print(hidden_note(hidden, 'next'))


def action_list(backlog_path: Path, repo: str | None = None) -> None:
    """List next items."""
    items, hidden = visible_items(backlog_path, repo)
    items = items[:10]
    if not items:
        print('✓ Backlog is empty!')
    else:
        print(f'\n📋 Next {len(items)} items:\n')
        for i, item in enumerate(items, 1):
            print(f'{i}. {item.title}')
            if item.content:
                lines = item.content.split('\n')
                preview = lines[0][:60]
                print(f'   {preview}')
        print()
    if hidden:
        print(hidden_note(hidden, 'list'))


def action_titles(
    backlog_path: Path,
    repo: str | None = None,
    *,
    untagged_only: bool = False,
) -> None:
    """Print bare titles, one per line, for piping into fzf.

    `untagged_only` is a different filter dimension than `repo` scoping --
    it's what the tag picker uses by default, so retagging an already-tagged
    item takes an explicit `--all` rather than happening by accident.
    """
    if untagged_only:
        items, hidden = filter_untagged_items(
            parse_backlog_file(backlog_path),
        )
        reason = 'already tagged'
    else:
        items, hidden = visible_items(backlog_path, repo)
        reason = 'for other repos'
    for item in items:
        print(item.title)
    if hidden:
        # stdout is the picker's input; a note there would be selectable.
        print(hidden_note(hidden, 'titles', reason), file=sys.stderr)


def prompt_for_title() -> str:
    """Prompt the user to enter a title."""
    return input('Item title: ').strip()


def open_editor_for_content() -> str:
    """Open $EDITOR for the user to write content, return the written text."""
    editor = os.environ.get('EDITOR', 'vim')

    with tempfile.NamedTemporaryFile(
        mode='w+',
        suffix='.md',
        delete=False,
    ) as f:
        temp_path = f.name

    try:
        subprocess.run([editor, temp_path], check=True)  # noqa: S603
        return Path(temp_path).read_text().strip()
    finally:
        Path(temp_path).unlink(missing_ok=True)


def action_edit(backlog_path: Path) -> None:
    """Open the backlog file directly in $EDITOR.

    For hand-fixing something the picker-driven actions can't reach --
    reordering, rewording, or untangling a bad merge. Prints the resolved
    path first since it lives outside every repo and is easy to lose track
    of.
    """
    editor = os.environ.get('EDITOR', 'vim')
    print(f'Opening {backlog_path} in {editor}...')
    subprocess.run([editor, str(backlog_path)], check=True)  # noqa: S603


def resolve_new_item(
    title: str | None,
    content: str | None,
) -> tuple[str, str]:
    """Fill in a new item's title/content, prompting for whichever is unset.

    If title is not provided, prompt for it.
    If content is not provided, open $EDITOR.
    """
    if not title:
        title = prompt_for_title()
        if not title:
            print('Error: Title cannot be empty', file=sys.stderr)
            sys.exit(1)

    if content is None:
        content = open_editor_for_content()

    return title, content


def apply_repo_tag(title: str, repo: str | None) -> str:
    """Prefix a bare title with `[repo]`, replacing any tag it already has."""
    bare_title = parse_repo_tag(title)[1]
    return f'[{repo}] {bare_title}' if repo else bare_title


def action_stack(
    backlog_path: Path,
    title: str | None = None,
    content: str | None = None,
    repo: str | None = None,
) -> None:
    """Insert a new item at the top of the backlog -- do this next."""
    title, content = resolve_new_item(title, content)
    title = apply_repo_tag(title, repo)
    items = parse_backlog_file(backlog_path)
    items.insert(0, BacklogItem(title, content))
    backlog_path.write_text(render_backlog(items))
    print(f'✓ Stacked: {title}')


def action_queue(
    backlog_path: Path,
    title: str | None = None,
    content: str | None = None,
    repo: str | None = None,
) -> None:
    """Insert a new item at the bottom of the backlog -- do this eventually."""
    title, content = resolve_new_item(title, content)
    title = apply_repo_tag(title, repo)
    items = parse_backlog_file(backlog_path)
    items.append(BacklogItem(title, content))
    backlog_path.write_text(render_backlog(items))
    print(f'✓ Queued: {title}')


def action_claim(backlog_path: Path, item_title: str) -> None:
    """Mark an item in-progress so other agents know it's taken."""
    items = parse_backlog_file(backlog_path)
    item = find_item(items, item_title)
    if not item:
        msg = f"Error: Item '{item_title}' not found"
        print(msg, file=sys.stderr)
        sys.exit(1)

    if item.in_progress:
        title = strip_in_progress_marker(item.title)
        msg = f"Error: '{title}' is already in progress"
        print(msg, file=sys.stderr)
        sys.exit(1)

    mark_item_in_progress(backlog_path, item)
    print(f'→ Claimed: {item.title}')


def action_complete(
    backlog_path: Path,
    complete_path: Path,
    item_title: str,
    end_time: str | None = None,
) -> None:
    """Mark item complete and move to .backlog-complete."""
    items = parse_backlog_file(backlog_path)
    item = find_item(items, item_title)
    if not item:
        msg = f"Error: Item '{item_title}' not found"
        print(msg, file=sys.stderr)
        sys.exit(1)

    end_dt = datetime.fromisoformat(end_time) if end_time else datetime.now()

    add_to_completed(complete_path, item, end_dt)
    remove_item_from_backlog(backlog_path, item)
    print(f'✓ Completed: {strip_in_progress_marker(item.title)}')


def action_tag(
    backlog_path: Path,
    item_title: str,
    repo: str | None,
) -> None:
    """Set, replace, or remove an item's `[repo]` tag."""
    items = parse_backlog_file(backlog_path)
    item = find_item(items, item_title)
    if not item:
        msg = f"Error: Item '{item_title}' not found"
        print(msg, file=sys.stderr)
        sys.exit(1)

    new_title = set_item_repo_tag(backlog_path, item, repo)
    if repo:
        print(f'→ Tagged [{repo}]: {new_title}')
    else:
        print(f'→ Untagged: {new_title}')


def action_merge_completed(complete_path: Path, incoming_path: Path) -> None:
    """Reconcile .backlog-complete with the copy from the password-store."""
    merged = merge_completed_text(
        read_if_present(complete_path),
        read_if_present(incoming_path),
    )
    complete_path.write_text(merged)
    count = len(parse_backlog_text(merged))
    print(f'  merged {complete_path.name} ({count} completed)')


def action_merge_backlog(
    backlog_path: Path,
    complete_path: Path,
    incoming_path: Path,
    prefer: MergePreference,
) -> None:
    """Reconcile .backlog with the copy from the password-store."""
    merged = merge_backlog_text(
        read_if_present(backlog_path),
        read_if_present(incoming_path),
        completed_titles(complete_path),
        prefer,
    )
    backlog_path.write_text(merged)
    count = len(parse_backlog_text(merged))
    print(f'  merged {backlog_path.name} ({count} open)')


def dispatch_merge(
    args: 'argparse.Namespace',
    backlog_path: Path,
    complete_path: Path,
) -> None:
    """Route the two merge actions, both of which need --incoming."""
    if not args.incoming:
        print('Error: --incoming required', file=sys.stderr)
        sys.exit(1)

    if args.action == 'merge-backlog':
        action_merge_backlog(
            backlog_path,
            complete_path,
            args.incoming,
            args.prefer,
        )
    else:
        action_merge_completed(complete_path, args.incoming)


def dispatch_item_action(
    args: 'argparse.Namespace',
    backlog_path: Path,
    complete_path: Path,
) -> None:
    """Route claim/complete/tag, which all need --item-title to find one."""
    if not args.item_title:
        # The shell wrapper picks a title with fzf; anything else gets the
        # list so the exact string is easy to copy.
        print('Error: --item-title required', file=sys.stderr)
        for title in list_titles(backlog_path):
            print(f'  {title}', file=sys.stderr)
        sys.exit(1)

    if args.action == 'claim':
        action_claim(backlog_path, args.item_title)
    elif args.action == 'complete':
        action_complete(
            backlog_path,
            complete_path,
            args.item_title,
            args.end_time,
        )
    else:
        if args.repo is None:
            msg = 'Error: --repo required (pass --repo "" to untag)'
            print(msg, file=sys.stderr)
            sys.exit(1)
        action_tag(backlog_path, args.item_title, args.repo or None)


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Backlog management for Claude Code',
    )
    parser.add_argument(
        'action',
        choices=[
            'next',
            'list',
            'titles',
            'edit',
            'stack',
            'queue',
            'claim',
            'complete',
            'tag',
            'merge-backlog',
            'merge-completed',
        ],
        help='Backlog action to perform',
    )
    parser.add_argument(
        '--backlog-path',
        type=Path,
        default=None,
        help=f'Path to the backlog file (default: {default_backlog_path()})',
    )
    parser.add_argument(
        '--complete-path',
        type=Path,
        default=None,
        help=(
            'Path to the completed-items file '
            f'(default: {default_complete_path()})'
        ),
    )
    parser.add_argument(
        '--repo',
        type=str,
        default=None,
        help=(
            'For list/next/titles: repo to show (default: the repo the cwd '
            'is in). For tag: repo to tag the item with (pass "" to untag). '
            'For stack/queue: repo to tag the new item with.'
        ),
    )
    parser.add_argument(
        '--all',
        '-a',
        action='store_true',
        help='List every item, including ones tagged for other repos',
    )
    parser.add_argument(
        '--untagged-only',
        action='store_true',
        help='For titles: list only items with no [repo] tag yet',
    )
    parser.add_argument(
        '--end-time',
        type=str,
        help='ISO format completion time for complete action (default: now)',
    )
    parser.add_argument(
        '--item-title',
        type=str,
        help='Title of item to claim or complete',
    )
    parser.add_argument(
        '--incoming',
        type=Path,
        help='Path to the password-store copy to merge in',
    )
    parser.add_argument(
        '--prefer',
        choices=['local', 'incoming'],
        default='local',
        help='Which side wins order and body for items present on both',
    )
    parser.add_argument(
        '--title',
        type=str,
        default=None,
        help='Title of item to stack/queue (if omitted, will prompt)',
    )
    parser.add_argument(
        '--content',
        type=str,
        default=None,
        help=(
            'Content for the stacked/queued item (if omitted, will open '
            '$EDITOR)'
        ),
    )

    args = parser.parse_args()

    backlog_path = args.backlog_path or default_backlog_path()
    complete_path = args.complete_path or default_complete_path()
    repo = None if args.all else (args.repo or current_repo_name())

    if args.action == 'next':
        action_next(backlog_path, repo)
    elif args.action == 'list':
        action_list(backlog_path, repo)
    elif args.action == 'titles':
        action_titles(backlog_path, repo, untagged_only=args.untagged_only)
    elif args.action == 'edit':
        action_edit(backlog_path)
    elif args.action == 'stack':
        action_stack(backlog_path, args.title, args.content, args.repo)
    elif args.action == 'queue':
        action_queue(backlog_path, args.title, args.content, args.repo)
    elif args.action in ('merge-backlog', 'merge-completed'):
        dispatch_merge(args, backlog_path, complete_path)
    elif args.action in ('claim', 'complete', 'tag'):
        dispatch_item_action(args, backlog_path, complete_path)


if __name__ == '__main__':
    main()
