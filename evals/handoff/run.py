"""Two-session eval for the handoff skill: write, then resume elsewhere.

`claude plugin eval` grades a single session, but a handoff only proves itself
in the *next* one, so this drives three headless `claude -p` calls per run:
writer (sees the fixture transcript, writes the handoff), resumer (fresh
session, sees only the repo), and judge (scores both against the fixture's
facts and traps).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVALS = Path(__file__).resolve().parent
SKILL = EVALS.parents[1] / 'skills' / 'handoff'
FIXTURES = EVALS / 'fixtures'
ARMS = ('skill', 'baseline', 'baseline-file')
TIMEOUT_S = 900
FAKE_SHAS = ('3f1a2c0',)
IGNORED = frozenset(
    ('.git', '.venv', '.pytest_cache', '__pycache__', '.ruff_cache'),
)

WRITE_PROMPT = """\
Below is the transcript of the session you have been running in the current \
working directory. The files on disk reflect exactly where it ended. Respond \
to the final user message as the assistant would.

<transcript>
{transcript}
</transcript>
"""

SAVE_TO_FILE = (
    '\n\n**User:** And save it to a file in the repo so the next session '
    'can read it.\n'
)

RESUME_PROMPT = """\
Continue where we left off. A previous session wrote a handoff in this repo.

Before doing any work, reconstruct the context and reply with your re-entry \
briefing only. Read and inspect whatever you need, but do not modify files, \
commit, or run anything that changes state.
"""

SKILL_PREAMBLE = """\
The `handoff` skill is active for this request. Its directory is {skill_dir}; \
`references/...` paths in it are relative to that directory, and the \
`handoff` CLI is on PATH.

"""

BRIEFING_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'properties': {
        key: {'type': 'string'}
        for key in (
            'goal',
            'state',
            'next_action',
            'acceptance_check',
            'dead_ends',
            'constraints',
            'open_questions',
            'deferred',
            'other_notes',
        )
    },
    'required': ['goal', 'state', 'next_action'],
}

JUDGE_PROMPT = """\
You are grading a handoff between two AI coding sessions.

Session A had the conversation in <transcript> and wrote handoff files \
(<handoff>, which also includes session A's final chat reply; only the \
files survive into session B). Session B started fresh with only the \
repo, and produced <briefing>. Grade strictly against the fixture's <facts> \
and <traps>.

For each fact, score:
- in_handoff: 1 if the handoff files or session A's chat reply state it \
clearly, 0.5 if partial or \
vague, 0 if absent or wrong.
- in_briefing: the same scale, for session B's briefing.

For each trap, violated=true if session B's briefing does or plans the \
trapped thing. Quote the offending text.

hallucinations: claims in the briefing that the transcript contradicts or \
that were never established (e.g. work described as done that wasn't). \
Omissions don't count, and neither do claims session B verified \
by reading the repo. Empty list if none.

<facts>
{facts}
</facts>

<traps>
{traps}
</traps>

<transcript>
{transcript}
</transcript>

<handoff>
{handoff}
</handoff>

<briefing>
{briefing}
</briefing>
"""

JUDGE_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'properties': {
        'facts': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'string'},
                    'in_handoff': {'type': 'number', 'enum': [0, 0.5, 1]},
                    'in_briefing': {'type': 'number', 'enum': [0, 0.5, 1]},
                    'note': {'type': 'string'},
                },
                'required': ['id', 'in_handoff', 'in_briefing'],
            },
        },
        'traps': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'string'},
                    'violated': {'type': 'boolean'},
                    'quote': {'type': 'string'},
                },
                'required': ['id', 'violated'],
            },
        },
        'hallucinations': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['facts', 'traps', 'hallucinations'],
}


@dataclass(frozen=True)
class Job:
    fixture: str
    arm: str
    index: int

    @property
    def name(self) -> str:
        return f'{self.fixture}__{self.arm}__{self.index}'


@dataclass(frozen=True)
class Models:
    agent: str
    judge: str


def claude(
    prompt: str,
    *,
    cwd: Path,
    model: str,
    tools: str,
    schema: dict[str, Any] | None = None,
    system: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    cmd = [
        'claude',
        '-p',
        prompt,
        '--model',
        model,
        '--output-format',
        'json',
        '--no-session-persistence',
        '--disable-slash-commands',
        '--settings',
        json.dumps({'disableAllHooks': True, 'autoMemoryEnabled': False}),
        '--permission-mode',
        'dontAsk',
        '--tools',
        tools,
        '--allowedTools',
        tools,
    ]
    if schema is not None:
        cmd += ['--json-schema', json.dumps(schema)]
    if system is not None:
        cmd += ['--append-system-prompt', system]
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    try:
        out: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            'is_error': True,
            'result': proc.stdout[-2000:],
            'stderr': proc.stderr[-2000:],
            'total_cost_usd': 0,
        }
    return out


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ['git', '-C', str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def snapshot(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if (
            path.is_file()
            and not IGNORED.intersection(rel.parts)
            and rel.parts[0] != '_skill'
        ):
            files[str(rel)] = path.read_text(errors='replace')
    return files


def changed(before: dict[str, str], after: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in after.items() if before.get(k) != v}


def is_handoff_doc(rel: str) -> bool:
    name = rel.lower()
    return 'handoff' in name or name.endswith(
        ('current.md', 'narrative.md', 'backlog.md'),
    )


def render_files(files: dict[str, str]) -> str:
    if not files:
        return '(no files written)'
    return '\n\n'.join(f'=== {k} ===\n{v}' for k, v in files.items())


def hook_output(cwd: Path, env: dict[str, str]) -> str:
    proc = subprocess.run(
        ['bash', str(SKILL / 'scripts' / 'handoff_session_start.sh')],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def weighted(facts: list[dict[str, Any]], scores: dict[str, float]) -> float:
    total = sum(f['weight'] for f in facts)
    got = sum(f['weight'] * scores.get(f['id'], 0) for f in facts)
    return round(got / total, 3) if total else 0.0


def deterministic_checks(
    fixture: dict[str, Any],
    repo: Path,
    handoff: dict[str, str],
) -> dict[str, Any]:
    text = '\n'.join(handoff.values())
    head = git(repo, 'rev-parse', '--short', 'HEAD')
    match = re.search(r'\*\*Status:\*\*\s*`?([a-z-]+)', text)
    status = match.group(1) if match else None
    current = next(
        (v for k, v in handoff.items() if k.endswith('CURRENT.md')),
        '',
    )
    counter = re.search(r'#(\d+) of this thread', current)
    return {
        'next_action_headings': len(
            re.findall(r'^#+\s*Next action', current, re.MULTILINE | re.I),
        ),
        'handoff_counter': int(counter.group(1)) if counter else None,
        'handoff_files': sorted(handoff),
        'handoff_words': len(text.split()),
        'anchor_head': head in text,
        'copied_fake_sha': any(s in text for s in FAKE_SHAS),
        'status': status,
        'status_ok': (
            None
            if 'expected_status' not in fixture
            else status == fixture['expected_status']
        ),
    }


def run_job(job: Job, models: Models, out_dir: Path) -> dict[str, Any]:
    fixture_dir = FIXTURES / job.fixture
    fixture = json.loads((fixture_dir / 'fixture.json').read_text())
    transcript = (fixture_dir / 'transcript.md').read_text()
    run_dir = out_dir / 'runs' / job.name
    run_dir.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix=f'handoff-eval-{job.name}-'))
    started = time.monotonic()
    try:
        subprocess.run(
            ['bash', str(fixture_dir / 'setup.sh'), str(work)],
            check=True,
            capture_output=True,
        )
        cwd = work / fixture['cwd']
        env = dict(os.environ)
        system = None
        if job.arm == 'skill':
            skill_copy = work / '_skill'
            shutil.copytree(
                SKILL,
                skill_copy,
                ignore=shutil.ignore_patterns(
                    'evals',
                    '__pycache__',
                    '.pytest_cache',
                ),
            )
            env['PATH'] = f'{skill_copy / "scripts"}:{env["PATH"]}'
            env['PROJECTS_DIR'] = str(work)
            system = (
                SKILL_PREAMBLE.format(skill_dir=skill_copy)
                + (SKILL / 'SKILL.md').read_text()
            )

        before = snapshot(work)
        write = claude(
            WRITE_PROMPT.format(
                transcript=transcript
                + (SAVE_TO_FILE if job.arm == 'baseline-file' else ''),
            ),
            cwd=cwd,
            model=models.agent,
            tools='Read,Write,Edit,Grep,Glob,Bash',
            system=system,
            env=env,
        )
        after_write = snapshot(work)
        written = changed(before, after_write)
        handoff = {k: v for k, v in written.items() if is_handoff_doc(k)}
        code_edits = sorted(k for k in written if not is_handoff_doc(k))
        for rel, content in handoff.items():
            dest = run_dir / 'handoff' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)

        resume_system = None
        if job.arm == 'skill':
            injected = hook_output(cwd, env)
            resume_system = (
                f'SessionStart hook output:\n{injected}\n\n{system}'
                if injected
                else system
            )
        resume = claude(
            RESUME_PROMPT,
            cwd=cwd,
            model=models.agent,
            tools='Read,Grep,Glob,Bash',
            schema=BRIEFING_SCHEMA,
            system=resume_system,
            env=env,
        )
        resume_mutations = sorted(changed(after_write, snapshot(work)))
        briefing = resume.get('structured_output') or {
            'error': resume.get('result'),
        }

        judge = claude(
            JUDGE_PROMPT.format(
                facts=json.dumps(fixture['facts'], indent=2),
                traps=json.dumps(fixture['traps'], indent=2),
                transcript=transcript,
                handoff=render_files(handoff)
                + '\n\n=== session A final chat reply (not saved) ===\n'
                + str(write.get('result', '')),
                briefing=json.dumps(briefing, indent=2),
            ),
            cwd=work,
            model=models.judge,
            tools='',
            schema=JUDGE_SCHEMA,
        )
        verdict = judge.get('structured_output') or {}
        facts = verdict.get('facts', [])
        result = {
            'job': job.name,
            'fixture': job.fixture,
            'arm': job.arm,
            'capture': weighted(
                fixture['facts'],
                {f['id']: f['in_handoff'] for f in facts},
            ),
            'transfer': weighted(
                fixture['facts'],
                {f['id']: f['in_briefing'] for f in facts},
            ),
            'traps_violated': [
                t['id'] for t in verdict.get('traps', []) if t['violated']
            ],
            'hallucinations': verdict.get('hallucinations', []),
            'code_edits_during_write': code_edits,
            'resume_mutations': resume_mutations,
            'errors': [
                name
                for name, r in (
                    ('write', write),
                    ('resume', resume),
                    ('judge', judge),
                )
                if r.get('is_error') or (name == 'judge' and not verdict)
            ],
            'cost_usd': round(
                sum(
                    r.get('total_cost_usd', 0) for r in (write, resume, judge)
                ),
                3,
            ),
            'seconds': round(time.monotonic() - started),
            **deterministic_checks(fixture, cwd, handoff),
        }
        for name, payload in (
            ('write', write),
            ('resume', resume),
            ('judge', judge),
            ('briefing', briefing),
            ('verdict', verdict),
            ('result', result),
        ):
            (run_dir / f'{name}.json').write_text(
                json.dumps(payload, indent=2),
            )
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 3) if xs else 0.0


def summarize(results: list[dict[str, Any]]) -> str:
    rows = [
        (
            '| fixture | arm | n | capture | transfer | traps hit | halluc. '
            '| words | anchor | status ok | $ |'
        ),
        '|---|---|---|---|---|---|---|---|---|---|---|',
    ]
    errored = [r['job'] for r in results if r['errors']]
    results = [r for r in results if not r['errors']]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in results:
        groups.setdefault((r['fixture'], r['arm']), []).append(r)
    for (fixture, arm), rs in sorted(groups.items()):
        statuses = [r['status_ok'] for r in rs if r['status_ok'] is not None]
        rows.append(
            f'| {fixture} | {arm} | {len(rs)} '
            f'| {mean([r["capture"] for r in rs]):.2f} '
            f'| {mean([r["transfer"] for r in rs]):.2f} '
            f'| {sum(len(r["traps_violated"]) for r in rs)} '
            f'| {sum(len(r["hallucinations"]) for r in rs)} '
            f'| {mean([r["handoff_words"] for r in rs]):.0f} '
            f'| {sum(r["anchor_head"] for r in rs)}/{len(rs)} '
            f'| {sum(statuses)}/{len(statuses) if statuses else "-"} '
            f'| {sum(r["cost_usd"] for r in rs):.2f} |',
        )
    for arm in ARMS:
        rs = [r for r in results if r['arm'] == arm]
        if rs:
            rows.append(
                f'| **all** | **{arm}** | {len(rs)} '
                f'| **{mean([r["capture"] for r in rs]):.2f}** '
                f'| **{mean([r["transfer"] for r in rs]):.2f}** '
                f'| {sum(len(r["traps_violated"]) for r in rs)} '
                f'| {sum(len(r["hallucinations"]) for r in rs)} '
                f'| {mean([r["handoff_words"] for r in rs]):.0f} | | '
                f'| {sum(r["cost_usd"] for r in rs):.2f} |',
            )
    if errored:
        rows.append(f'\nExcluded (claude errors): {", ".join(errored)}')
    return '\n'.join(rows) + '\n'


def parse_args(argv: list[str]) -> argparse.Namespace:
    fixtures = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    parser = argparse.ArgumentParser(
        description='Write-then-resume eval for the handoff skill.',
    )
    parser.add_argument(
        '--fixture',
        nargs='*',
        default=fixtures,
        choices=fixtures,
    )
    parser.add_argument('--arm', nargs='*', default=list(ARMS), choices=ARMS)
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('-j', '--concurrency', type=int, default=4)
    parser.add_argument('--model', default='claude-opus-5-5')
    parser.add_argument('--judge-model', default='claude-opus-5-5')
    parser.add_argument('--out', type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    stamp = datetime.now(UTC).strftime('%Y-%m-%dT%H-%M-%SZ')
    out_dir = args.out or EVALS / 'results' / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    models = Models(agent=args.model, judge=args.judge_model)
    jobs = [
        Job(f, a, i)
        for f in args.fixture
        for a in args.arm
        for i in range(args.runs)
    ]
    results: list[dict[str, Any]] = []
    crashed = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_job, j, models, out_dir): j for j in jobs}
        for future, job in futures.items():
            try:
                r = future.result()
            except Exception as exc:
                print(f'FAIL {job.name}: {exc!r}', file=sys.stderr)
                crashed += 1
                continue
            results.append(r)
            print(
                f'{job.name}: capture={r["capture"]} transfer={r["transfer"]} '
                f'traps={r["traps_violated"]} errors={r["errors"]}',
                flush=True,
            )
    (out_dir / 'results.json').write_text(json.dumps(results, indent=2))
    summary = summarize(results)
    (out_dir / 'summary.md').write_text(summary)
    print(summary)
    print(f'Results: {out_dir}')
    # Scores are measurements with no pass bar, so only a run that didn't
    # complete is a failure.
    errored = crashed + sum(1 for r in results if r['errors'])
    if errored:
        print(
            f'{errored} of {len(jobs)} job(s) did not complete',
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
