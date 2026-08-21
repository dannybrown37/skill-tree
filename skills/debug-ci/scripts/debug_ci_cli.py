#!/usr/bin/env python3
"""Fetch a failed GitHub Actions run's logs and trim them to the errors.

`gh run view --log-failed` prints every line of every failed job, which
is the wrong shape for a model's context window: the diagnosis lives in
a handful of lines and the rest is setup noise. This finds the failing
run for a branch and prints, per failed step, the error lines plus a
little context around them.

Diagnosis is not this script's job -- it only decides which lines are
worth reading, and says where it elided the rest so nothing looks
complete when it isn't.
"""

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_NO_RUN = 1
EXIT_UNUSABLE = 2

GH_TIMEOUT_SECONDS = 60
RUN_LIST_LIMIT = 10

# Context around each error marker, and the ceiling on one step's
# output: enough to see the assertion and what led to it, small enough
# that a job looping on the same error can't fill the window.
CONTEXT_BEFORE = 8
CONTEXT_AFTER = 4
MAX_LINES_PER_STEP = 60
# Shown when a step had no marker at all: the tail is where a silent
# failure usually is.
TAIL_LINES = 20
# job, step, message
LOG_FIELDS = 3

RUN_FIELDS = (
    'databaseId,displayTitle,workflowName,headBranch,conclusion,createdAt,url'
)

TIMESTAMP_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z\s?',
)

# Anchored where it can be: `error:` inside prose ("0 errors") and
# inside an identifier ("no-error-here") are not failures.
ERROR_RES = (
    re.compile(r'##\[error\]'),
    re.compile(r'(^|\s)[Ee]rror:\s'),
    re.compile(r'^\s*(FAILED|FAIL)\b'),
    re.compile(r'^\s*Traceback \(most recent call last\)'),
    re.compile(r'\b\w*(Error|Exception):\s'),
    re.compile(r'npm ERR!'),
    re.compile(r'exit code [1-9]'),
    re.compile(r'^\s*E\s{2,}\S'),
    # pre-commit / prettier-style dotted status lines
    re.compile(r'\.{4,}(Failed|FAILED)\b'),
    re.compile(r'^\s*[✗✖]\s'),
    re.compile(r'^\s*- hook id:'),
)


class DebugCIError(Exception):
    """Something the caller has to resolve before this can work."""


class NoFailingRunError(DebugCIError):
    """The branch has no failed run -- an answer, not a malfunction."""


@dataclass(frozen=True)
class Run:
    run_id: int
    title: str
    workflow: str
    branch: str
    created_at: str
    url: str


@dataclass(frozen=True)
class LogLine:
    job: str
    step: str
    message: str


@dataclass(frozen=True)
class JobFailure:
    job: str
    step: str
    lines: list[str]


def version() -> str:
    """This checkout's plugin version, or `unknown` outside one.

    `--version` has to work with no config and no credentials, so a
    missing or unreadable manifest is an answer rather than a crash.
    """
    manifest = (
        Path(__file__).resolve().parents[3] / '.claude-plugin' / 'plugin.json'
    )
    try:
        return str(json.loads(manifest.read_text())['version'])
    except (OSError, ValueError, KeyError):
        return 'unknown'


def gh(args: Sequence[str]) -> str:
    """Run `gh` and return stdout, turning every failure into an error."""
    try:
        result = subprocess.run(  # noqa: S603
            ['gh', *args],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as error:
        message = 'gh is not installed -- see https://cli.github.com'
        raise DebugCIError(message) from error
    except (OSError, subprocess.TimeoutExpired) as error:
        message = f'gh {" ".join(args)} did not complete: {error}'
        raise DebugCIError(message) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        message = f'gh {" ".join(args)} failed: {detail}'
        raise DebugCIError(message)
    return result.stdout


def current_branch() -> str:
    """The checked-out branch, or an error if there isn't one."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        message = f'could not read the current branch: {error}'
        raise DebugCIError(message) from error
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch or branch == 'HEAD':
        message = 'not on a branch -- pass --branch or a run id'
        raise DebugCIError(message)
    return branch


def strip_timestamp(raw: str) -> str:
    """Drop the ISO timestamp `gh` prefixes to every log line."""
    return TIMESTAMP_RE.sub('', raw)


def parse_log(text: str) -> list[LogLine]:
    """Split `gh run view --log-failed` output into job/step/message.

    Lines without the two leading tabs are `gh`'s own framing, not log
    content, and are dropped.
    """
    lines = []
    for raw in text.splitlines():
        parts = raw.split('\t', 2)
        if len(parts) != LOG_FIELDS or not parts[0]:
            continue
        job, step, message = parts
        lines.append(
            LogLine(job=job, step=step, message=strip_timestamp(message)),
        )
    return lines


def error_indices(messages: Sequence[str]) -> list[int]:
    """Positions of the lines that look like a real failure."""
    return [
        index
        for index, message in enumerate(messages)
        if any(pattern.search(message) for pattern in ERROR_RES)
    ]


def _regions(
    markers: Sequence[int],
    *,
    before: int,
    after: int,
    total: int,
) -> list[tuple[int, int]]:
    """Merge each marker's context window into non-overlapping spans."""
    merged: list[tuple[int, int]] = []
    for marker in markers:
        start = max(0, marker - before)
        end = min(total, marker + after + 1)
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def trim(
    messages: Sequence[str],
    *,
    before: int = CONTEXT_BEFORE,
    after: int = CONTEXT_AFTER,
    max_lines: int = MAX_LINES_PER_STEP,
) -> list[str]:
    """Keep the error regions, mark every gap, and cap the total.

    With no marker there's nothing to centre on, so the tail is the
    answer -- that's where a silent failure ends up.
    """
    if not messages:
        return []
    markers = error_indices(messages)
    if not markers:
        return list(messages[-max_lines:])

    regions = _regions(
        markers,
        before=before,
        after=after,
        total=len(messages),
    )
    kept: list[str] = []
    previous_end = 0
    for start, end in regions:
        if start > previous_end:
            kept.append(f'... {start - previous_end} lines omitted ...')
        kept.extend(messages[start:end])
        previous_end = end
    if previous_end < len(messages):
        kept.append(f'... {len(messages) - previous_end} lines omitted ...')

    if len(kept) > max_lines:
        dropped = len(kept) - (max_lines - 1)
        kept = [*kept[: max_lines - 1], f'... {dropped} lines omitted ...']
    return kept


def extract_failures(
    text: str,
    *,
    before: int = CONTEXT_BEFORE,
    after: int = CONTEXT_AFTER,
    max_lines: int = MAX_LINES_PER_STEP,
) -> list[JobFailure]:
    """One trimmed entry per (job, step) that actually reported an error."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for line in parse_log(text):
        grouped.setdefault((line.job, line.step), []).append(line.message)

    failures = []
    for (job, step), messages in grouped.items():
        if not error_indices(messages):
            continue
        failures.append(
            JobFailure(
                job=job,
                step=step,
                lines=trim(
                    messages,
                    before=before,
                    after=after,
                    max_lines=max_lines,
                ),
            ),
        )
    return failures


def _as_run(payload: dict[str, object]) -> Run:
    return Run(
        run_id=int(str(payload.get('databaseId', 0))),
        title=str(payload.get('displayTitle', '')),
        workflow=str(payload.get('workflowName', '')),
        branch=str(payload.get('headBranch', '')),
        created_at=str(payload.get('createdAt', '')),
        url=str(payload.get('url', '')),
    )


def select_run(
    payloads: Sequence[dict[str, object]],
    *,
    run_id: int | None = None,
) -> tuple[Run, list[Run]]:
    """The run to read, plus the other failures worth mentioning.

    Newest wins, but the rest are returned rather than dropped: which
    of several failures matters is a judgement call the playbook makes
    with the user, not one to bury here.
    """
    runs = [_as_run(payload) for payload in payloads]
    if run_id is not None:
        for run in runs:
            if run.run_id == run_id:
                return run, []
        message = f'run {run_id} is not among the failing runs listed'
        raise DebugCIError(message)
    if not runs:
        raise NoFailingRunError
    ordered = sorted(runs, key=lambda run: run.created_at, reverse=True)
    return ordered[0], ordered[1:]


FAILING_CONCLUSIONS = frozenset({'failure', 'timed_out', 'startup_failure'})


def _repo_args(repo: str | None) -> list[str]:
    return ['-R', repo] if repo else []


def failing_runs(
    branch: str,
    repo: str | None = None,
) -> list[dict[str, object]]:
    """Failed runs for a branch, as `gh` reports them.

    The conclusion filter is applied here rather than with
    `gh run list --status`: that flag doesn't exist on every `gh` in
    the wild, and a hard error about an unknown flag is a worse failure
    than one extra list to filter.
    """
    raw = gh(
        [
            'run',
            'list',
            *_repo_args(repo),
            '--branch',
            branch,
            '--limit',
            str(RUN_LIST_LIMIT),
            '--json',
            RUN_FIELDS,
        ],
    )
    try:
        payloads = json.loads(raw or '[]')
    except ValueError as error:
        message = f'could not parse gh run list output: {error}'
        raise DebugCIError(message) from error
    return [
        payload
        for payload in payloads
        if str(payload.get('conclusion', '')) in FAILING_CONCLUSIONS
    ]


def current_repo() -> str:
    """`owner/name` for the repo in cwd."""
    return gh(
        ['repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'],
    ).strip()


def failed_jobs(run_id: int, repo: str) -> list[tuple[int, str, str]]:
    """`(job id, job name, first failed step)` for each failed job."""
    raw = gh(['api', f'repos/{repo}/actions/runs/{run_id}/jobs'])
    try:
        payload = json.loads(raw or '{}')
    except ValueError as error:
        message = f'could not parse the jobs API response: {error}'
        raise DebugCIError(message) from error

    jobs = []
    for job in payload.get('jobs', []):
        if str(job.get('conclusion', '')) not in FAILING_CONCLUSIONS:
            continue
        steps = [
            str(step.get('name', ''))
            for step in job.get('steps', [])
            if str(step.get('conclusion', '')) in FAILING_CONCLUSIONS
        ]
        jobs.append(
            (
                int(job['id']),
                str(job.get('name', '')),
                steps[0] if steps else 'log',
            ),
        )
    return jobs


def api_failure_log(run_id: int, repo: str) -> str:
    """The failed jobs' logs, rewritten into `run view --log` format.

    The REST endpoint returns a bare log with no job or step column, so
    those are filled in from the jobs API -- which keeps every parser
    downstream working on one shape regardless of which fetch ran.
    """
    lines: list[str] = []
    for job_id, job_name, step in failed_jobs(run_id, repo):
        raw = gh(['api', f'repos/{repo}/actions/jobs/{job_id}/logs'])
        lines.extend(
            f'{job_name}\t{step}\t{line.lstrip(chr(0xFEFF))}'
            for line in raw.splitlines()
            if line.strip()
        )
    return '\n'.join(lines) + ('\n' if lines else '')


def failure_log(run_id: int, repo: str | None = None) -> str:
    """The run's failure log, by whichever route this `gh` supports.

    `gh run view --log-failed` exits 0 and prints nothing on older `gh`
    against current Actions logs -- an empty answer that looks like a
    clean run. When that happens, go to the REST API instead.
    """
    text = gh(['run', 'view', *_repo_args(repo), str(run_id), '--log-failed'])
    if text.strip():
        return text
    return api_failure_log(run_id, repo or current_repo())


def render_failure(failure: JobFailure) -> str:
    body = '\n'.join(f'  {line}' for line in failure.lines)
    return f'## {failure.job} -- {failure.step}\n{body}\n'


def render(
    run: Run,
    failures: Sequence[JobFailure],
    others: Sequence[Run],
    raw_log: str,
) -> str:
    parts = [
        f'# run {run.run_id} -- {run.workflow} on {run.branch}\n',
        f'{run.title}\n{run.url}\n\n',
    ]
    if failures:
        parts.extend(render_failure(failure) + '\n' for failure in failures)
    else:
        tail = [line.message for line in parse_log(raw_log)][-TAIL_LINES:]
        parts.append(
            'No error markers in the log; showing its tail.\n'
            + '\n'.join(f'  {line}' for line in tail)
            + '\n\n',
        )
    if others:
        parts.append('Other failing runs on this branch:\n')
        parts.extend(
            f'  {other.run_id}  {other.created_at}  {other.title}\n'
            for other in others
        )
    return ''.join(parts)


def as_json(
    run: Run,
    failures: Sequence[JobFailure],
    others: Sequence[Run],
) -> str:
    return json.dumps(
        {
            'run': {
                'run_id': run.run_id,
                'title': run.title,
                'workflow': run.workflow,
                'branch': run.branch,
                'created_at': run.created_at,
                'url': run.url,
            },
            'failures': [
                {
                    'job': failure.job,
                    'step': failure.step,
                    'lines': failure.lines,
                }
                for failure in failures
            ],
            'other_failing_runs': [other.run_id for other in others],
        },
        indent=2,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. 0 extracted, 1 no failing run, 2 unusable."""
    parser = argparse.ArgumentParser(
        prog='debug-ci',
        description=(
            "A failed Actions run's logs, trimmed to the error regions."
        ),
        epilog=(
            'With no arguments: the newest failing run on the current '
            "branch. Diagnosis is the debug-ci skill's job, not this "
            "script's."
        ),
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'debug-ci {version()}',
    )
    parser.add_argument(
        'run_id',
        nargs='?',
        type=int,
        help='a specific run id; defaults to the newest failing run',
    )
    parser.add_argument(
        '--repo',
        help='owner/name; defaults to the repo in the current directory',
    )
    parser.add_argument(
        '--branch',
        help='branch to search; defaults to the checked-out one',
    )
    parser.add_argument(
        '--context',
        type=int,
        default=CONTEXT_BEFORE,
        help=f'lines kept before each error (default {CONTEXT_BEFORE})',
    )
    parser.add_argument(
        '--max-lines',
        type=int,
        default=MAX_LINES_PER_STEP,
        help=f'ceiling per step (default {MAX_LINES_PER_STEP})',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        dest='as_json',
        help='machine-readable output',
    )
    args = parser.parse_args(argv)

    branch = args.branch
    try:
        branch = branch or current_branch()
        run, others = select_run(
            failing_runs(branch, args.repo),
            run_id=args.run_id,
        )
        raw_log = failure_log(run.run_id, args.repo)
    except NoFailingRunError:
        print(f'debug-ci: no failed runs for branch {branch}', file=sys.stderr)
        return EXIT_NO_RUN
    except DebugCIError as error:
        print(f'debug-ci: {error}', file=sys.stderr)
        return EXIT_UNUSABLE

    failures = extract_failures(
        raw_log,
        before=args.context,
        after=CONTEXT_AFTER,
        max_lines=args.max_lines,
    )
    print(
        as_json(run, failures, others)
        if args.as_json
        else render(run, failures, others, raw_log),
        end='',
    )
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
