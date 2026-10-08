#!/usr/bin/env python3
"""How often each skill in this repo actually gets invoked.

Counted from Claude Code's own session transcripts, so there is nothing
to install and nothing to have been recording beforehand. A skill is
invoked two ways and they mean different things, so they are counted
apart: the user typing `/<plugin>:<name>`, and the model calling the
`Skill` tool on its own.

A third number matters as much as either: `Skill` calls that *errored*.
A skill the model keeps asking for and cannot load is a reference going
stale somewhere (a CLAUDE.md naming a skill that was since deleted), and
nothing else in the repo surfaces that.

Claude Code prunes transcripts after about a month by default, so "never"
here means "not in the days still on disk". Copilot CLI keeps no
comparable record, so its sessions are not counted.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_skill_structure import find_skill_dirs, parse_frontmatter

LOADED = 'loaded'
REASONS = {
    'unknown': 'not in this repo',
    'blocked': 'model invocation disabled',
    'error': 'failed while loading',
}

# Skill-backed commands put <command-message> first; the CLI's built-ins
# (/clear, /model) put <command-name> first. That order is the only thing
# in a transcript that tells the two apart. Anchored at the start so a
# prompt that merely pastes these tags is not counted.
SLASH_SKILL = re.compile(
    r'\s*<command-message>[^<]*</command-message>\s*'
    r'<command-name>([^<]*)</command-name>',
)
TIMESTAMP = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')


@dataclass(frozen=True)
class Invocation:
    """One attempt to start a skill, as a transcript recorded it."""

    key: str
    name: str
    by_user: bool
    when: datetime
    project: str
    outcome: str = LOADED


@dataclass
class Usage:
    user: int = 0
    agent: int = 0
    last_used: date | None = None


@dataclass
class Failure:
    """A skill the model asked for and did not get."""

    name: str
    reason: str
    count: int = 0
    last: date | None = None
    projects: Counter[str] = field(default_factory=Counter)


@dataclass
class Report:
    source: Path
    first_day: date | None
    usage: dict[str, Usage]
    failed: list[Failure]


def transcripts_dir() -> Path:
    config = os.environ.get('CLAUDE_CONFIG_DIR')
    base = Path(config) if config else Path.home() / '.claude'
    return base / 'projects'


def slash_skill(text: str) -> str | None:
    """The skill a typed `/name` prompt started, or None."""
    match = SLASH_SKILL.match(text)
    if match is None:
        return None
    return match.group(1).strip().lstrip('/') or None


def parse_stamp(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def blocks(content: object) -> list[dict]:
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def plain_text(content: object) -> str:
    if isinstance(content, str):
        return content
    return ' '.join(
        str(block.get('text', ''))
        for block in blocks(content)
        if block.get('type', 'text') == 'text'
    )


def load_outcome(tool_result: dict) -> str:
    if not tool_result.get('is_error'):
        return LOADED
    message = plain_text(tool_result.get('content'))
    if 'Unknown skill' in message:
        return 'unknown'
    if 'disable-model-invocation' in message:
        return 'blocked'
    return 'error'


class TranscriptScan:
    """One transcript's invocations, built up a record at a time."""

    def __init__(self, path: Path) -> None:
        self.fallback_project = path.parent.name
        self.started: datetime | None = None
        self.typed: list[Invocation] = []
        self.calls: dict[str, Invocation] = {}
        self.awaiting: set[str] = set()

    def invocations(self) -> list[Invocation]:
        return [*self.typed, *self.calls.values()]

    def worth_parsing(self, line: str) -> bool:
        """Most lines are tool output; decoding them all takes seconds."""
        if '"Skill"' in line or '<command-message>' in line:
            return True
        return 'tool_result' in line and any(
            call in line for call in self.awaiting
        )

    def read(self, line: str) -> None:
        if self.started is None:
            found = TIMESTAMP.search(line)
            self.started = parse_stamp(found.group(1)) if found else None
        if not self.worth_parsing(line):
            return
        try:
            record = json.loads(line)
        except ValueError:
            return
        if isinstance(record, dict):
            self.take(record)

    def take(self, record: dict) -> None:
        message = record.get('message')
        content = message.get('content') if isinstance(message, dict) else None
        when = parse_stamp(record.get('timestamp'))
        cwd = record.get('cwd')
        project = Path(cwd).name if isinstance(cwd, str) and cwd else ''
        project = project or self.fallback_project

        if record.get('type') == 'assistant' and when:
            self.take_calls(blocks(content), when, project)
        elif record.get('type') == 'user':
            self.take_results(blocks(content))
            name = slash_skill(plain_text(content))
            if name and when:
                key = str(record.get('uuid') or f'{name}@{when.isoformat()}')
                self.typed.append(
                    Invocation(key, name, True, when, project),  # noqa: FBT003
                )

    def take_calls(
        self,
        content: list[dict],
        when: datetime,
        project: str,
    ) -> None:
        for block in content:
            if block.get('type') != 'tool_use' or block.get('name') != 'Skill':
                continue
            tool_input = block.get('input')
            if not isinstance(tool_input, dict):
                continue
            name = tool_input.get('skill')
            call = block.get('id')
            if not (isinstance(name, str) and name and isinstance(call, str)):
                continue
            self.calls[call] = Invocation(
                call,
                name,
                False,  # noqa: FBT003
                when,
                project,
            )
            self.awaiting.add(call)

    def take_results(self, content: list[dict]) -> None:
        for block in content:
            call = block.get('tool_use_id')
            if block.get('type') != 'tool_result' or call not in self.awaiting:
                continue
            self.awaiting.discard(call)
            self.calls[call] = dataclasses.replace(
                self.calls[call],
                outcome=load_outcome(block),
            )


def scan(path: Path) -> TranscriptScan:
    transcript = TranscriptScan(path)
    try:
        with path.open(errors='replace') as handle:
            for line in handle:
                transcript.read(line)
    except OSError:
        pass
    return transcript


def own_name(recorded: str, skills: set[str], plugin: str) -> str | None:
    """`recorded` as one of this repo's skills, or None if it isn't ours.

    The plugin prefix makes a name ours even when no such skill exists
    any more -- that is exactly the stale reference worth reporting.
    """
    prefix = f'{plugin}:'
    if recorded.startswith(prefix):
        return recorded[len(prefix) :]
    return recorded if recorded in skills else None


def collect(
    projects_dir: Path,
    skills: set[str],
    plugin: str,
    since: datetime | None,
) -> Report:
    usage = {name: Usage() for name in skills}
    failures: dict[tuple[str, str], Failure] = {}
    seen: set[str] = set()
    first: datetime | None = None

    for path in sorted(projects_dir.rglob('*.jsonl')):
        transcript = scan(path)
        started = transcript.started
        if started and (first is None or started < first):
            first = started

        for invocation in transcript.invocations():
            # A resumed session carries its history along, so the same
            # record turns up in more than one file.
            if invocation.key in seen:
                continue
            seen.add(invocation.key)
            if since and invocation.when < since:
                continue
            name = own_name(invocation.name, skills, plugin)
            if name is not None:
                tally(invocation, name, usage, failures)

    if first and since and since > first:
        first = since
    return Report(
        source=projects_dir,
        first_day=first.astimezone().date() if first else None,
        usage=usage,
        failed=sorted(
            failures.values(),
            key=lambda failure: (-failure.count, failure.name),
        ),
    )


def tally(
    invocation: Invocation,
    name: str,
    usage: dict[str, Usage],
    failures: dict[tuple[str, str], Failure],
) -> None:
    day = invocation.when.astimezone().date()

    if invocation.outcome != LOADED:
        failure = failures.setdefault(
            (name, invocation.outcome),
            Failure(name, invocation.outcome),
        )
        failure.count += 1
        failure.projects[invocation.project] += 1
        failure.last = max(failure.last or day, day)
        return

    row = usage.get(name)
    if row is None:
        return
    if invocation.by_user:
        row.user += 1
    else:
        row.agent += 1
    row.last_used = max(row.last_used or day, day)


def busiest_first(usage: dict[str, Usage]) -> list[tuple[str, Usage]]:
    return sorted(
        usage.items(),
        key=lambda item: (-(item[1].user + item[1].agent), item[0]),
    )


def render(report: Report, model_invocable: dict[str, bool]) -> str:
    since = report.first_day.isoformat() if report.first_day else 'n/a'
    lines = [
        f'Skill invocations since {since}, from {report.source}',
        '',
    ]

    name_w = max((len(name) for name in report.usage), default=5)
    lines.append(f'  {"SKILL".ljust(name_w)}  USER  AGENT  LAST')
    for name, row in busiest_first(report.usage):
        blocked = not model_invocable.get(name, True) and row.agent == 0
        agent = '-' if blocked else str(row.agent)
        last = row.last_used.isoformat() if row.last_used else 'never'
        lines.append(
            f'  {name.ljust(name_w)}  {row.user:>4}  {agent:>5}  {last}',
        )

    idle = sum(1 for row in report.usage.values() if not row.last_used)
    lines += [
        '',
        f'{idle} of {len(report.usage)} skills not invoked in that time.',
        'AGENT "-": disable-model-invocation is set, so only you start it.',
    ]

    if report.failed:
        lines += ['', 'The agent asked for skills it could not load:']
        fail_w = max(len(failure.name) for failure in report.failed)
        reason_w = max(len(REASONS[f.reason]) for f in report.failed)
        for failure in report.failed:
            where = ', '.join(
                f'{project} {count}'
                for project, count in failure.projects.most_common(3)
            )
            lines.append(
                f'  {failure.name.ljust(fail_w)}  {failure.count:>3}x  '
                f'{REASONS[failure.reason].ljust(reason_w)}  '
                f'last {failure.last}  ({where})',
            )
        lines.append(
            '"not in this repo": something still tells the agent to invoke '
            "it -- grep those projects' CLAUDE.md for the name.",
        )
    return '\n'.join(lines)


def as_json(report: Report, model_invocable: dict[str, bool]) -> str:
    return json.dumps(
        {
            'source': str(report.source),
            'since': report.first_day.isoformat()
            if report.first_day
            else None,
            'skills': [
                {
                    'name': name,
                    'user': row.user,
                    'agent': row.agent,
                    'last_used': row.last_used.isoformat()
                    if row.last_used
                    else None,
                    'model_invocable': model_invocable.get(name, True),
                }
                for name, row in busiest_first(report.usage)
            ],
            'failed': [
                {
                    'name': failure.name,
                    'reason': failure.reason,
                    'count': failure.count,
                    'last': failure.last.isoformat() if failure.last else None,
                    'projects': dict(failure.projects),
                }
                for failure in report.failed
            ],
        },
        indent=2,
    )


def manifest_field(root: Path, key: str, default: str) -> str:
    """A plugin.json value, or `default` when there is no usable manifest.

    `--version` has to answer on a broken install, so a missing manifest
    is an answer rather than a crash.
    """
    manifest = root / '.claude-plugin' / 'plugin.json'
    try:
        return str(json.loads(manifest.read_text())[key])
    except (OSError, ValueError, KeyError, TypeError):
        return default


def model_invocable_by_skill(root: Path) -> dict[str, bool]:
    skills = {}
    for skill_dir in find_skill_dirs(root):
        skill_md = skill_dir / 'SKILL.md'
        if not skill_md.is_file():
            continue
        fields = parse_frontmatter(skill_md.read_text(errors='replace'))
        disabled = fields.get('disable-model-invocation', '').lower()
        skills[skill_dir.name] = disabled != 'true'
    return skills


def positive_days(raw: str) -> int:
    try:
        days = int(raw)
    except ValueError:
        days = 0
    if days < 1:
        message = f'expected a whole number of days, 1 or more (got {raw!r})'
        raise argparse.ArgumentTypeError(message)
    return days


def build_parser(root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='skill-tree stats',
        description=(
            'How often each skill in this repo was invoked, counted from '
            "Claude Code's session transcripts. USER is you typing "
            '/<skill>; AGENT is the model loading it on its own.'
        ),
        epilog=(
            'Transcripts are pruned after about a month, so "never" means '
            'not in the days still on disk. Set CLAUDE_CONFIG_DIR if yours '
            'are not under ~/.claude.'
        ),
    )
    parser.add_argument(
        '--days',
        type=positive_days,
        metavar='N',
        help='only count the last N days (default: everything on disk)',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='machine-readable output',
    )
    parser.add_argument(
        '-V',
        '--version',
        action='version',
        version=f'%(prog)s {manifest_field(root, "version", "unknown")}',
    )
    return parser


def main(
    argv: list[str] | None = None,
    root: Path | None = None,
    projects_dir: Path | None = None,
) -> int:
    root = Path(__file__).resolve().parent.parent if root is None else root
    args = build_parser(root).parse_args(argv)
    source = transcripts_dir() if projects_dir is None else projects_dir

    if not source.is_dir():
        print(
            f'skill-tree stats: no Claude Code transcripts at {source} '
            '(set CLAUDE_CONFIG_DIR if yours live somewhere else)',
            file=sys.stderr,
        )
        return 1

    model_invocable = model_invocable_by_skill(root)
    since = (
        datetime.now(UTC) - timedelta(days=args.days) if args.days else None
    )
    report = collect(
        source,
        skills=set(model_invocable),
        plugin=manifest_field(root, 'name', 'skill-tree'),
        since=since,
    )

    if args.json:
        print(as_json(report, model_invocable))
    else:
        print(render(report, model_invocable))
    return 0


if __name__ == '__main__':
    sys.exit(main())
