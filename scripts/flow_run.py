"""`skill-tree run`: drive a flow of skills headlessly, pausing at gates.

A flow is a TOML list of steps; each step runs one skill through the host
CLI (Copilot today), reading earlier steps' output files and writing its
own. Flows are layered -- repo, then user, then built-in -- and a flow can
`extends` another and patch it, so a work machine can reshape the default
loop with a hand-written file and no work content ever lands here.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parent.parent
GATES = ('none', 'approve', 'interactive')
HOSTS = ('copilot', 'claude')
PAUSED_EXIT = 3
TIMEOUT_EXIT = 124
DEFAULT_MAX_STEPS = 20
RUNS_DIR = Path('.skill-tree') / 'runs'
EXCLUDE_LINE = '.skill-tree/runs/'

FLOW_KEYS = frozenset(
    {
        'name',
        'host',
        'extends',
        'context',
        'allow_tools',
        'allow_all',
        'model',
        'max_steps',
        'steps',
        'patch',
    },
)
STEP_KEYS = frozenset(
    {
        'id',
        'skill',
        'in',
        'out',
        'gate',
        'model',
        'allow_tools',
        'allow_all',
        'timeout',
    },
)
PATCH_KEYS = frozenset(
    {'replace', 'remove', 'insert_after', 'insert_before', 'append'},
)


class FlowError(Exception):
    """A flow can't be loaded, resolved, or run; message is user-facing."""


@dataclass(frozen=True)
class Step:
    id: str
    skill: str
    inputs: tuple[str, ...] = ()
    out: str | None = None
    gate: str = 'none'
    model: str | None = None
    allow_tools: tuple[str, ...] = ()
    allow_all: bool = False
    timeout: int | None = None


@dataclass(frozen=True)
class Flow:
    name: str
    steps: tuple[Step, ...]
    host: str = 'copilot'
    context: tuple[str, ...] = ()
    allow_tools: tuple[str, ...] = ()
    allow_all: bool = False
    model: str | None = None
    max_steps: int = DEFAULT_MAX_STEPS
    source: Path | None = None


@dataclass(frozen=True)
class Layers:
    repo: Path
    user: Path
    builtin: Path


@dataclass(frozen=True)
class RunOptions:
    cwd: Path
    model: str | None
    allow_tools: tuple[str, ...]
    allow_all: bool
    timeout: int | None


@dataclass(frozen=True)
class GateIO:
    ask: Callable[[str], str]
    interactive: bool


class Host(Protocol):
    def list_skills(self, cwd: Path) -> dict[str, Path]: ...

    def run_headless(
        self,
        prompt: str,
        options: RunOptions,
        log: Path,
    ) -> int: ...

    def run_interactive(self, prompt: str, options: RunOptions) -> int: ...


# --- loading --------------------------------------------------------------


def _layer_dirs(layers: Layers) -> list[Path]:
    return [layers.repo / '.skill-tree' / 'flows', layers.user, layers.builtin]


def _find_named(name: str, layers: Layers, skip: Path | None) -> Path:
    candidates = [d / f'{name}.toml' for d in _layer_dirs(layers)]
    for path in candidates:
        if path.is_file() and path != skip:
            return path
    searched = '\n  '.join(str(p) for p in candidates)
    msg = f'flow "{name}" not found; searched:\n  {searched}'
    raise FlowError(msg)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        msg = f'invalid TOML in {path}: {exc}'
        raise FlowError(msg) from exc
    unknown = set(data) - FLOW_KEYS
    if unknown:
        msg = f'{path}: unknown key(s): {", ".join(sorted(unknown))}'
        raise FlowError(msg)
    if 'extends' in data and 'steps' in data:
        msg = f'{path}: has both "extends" and "steps"; use [patch]'
        raise FlowError(msg)
    return data


def _step_index(steps: list[dict[str, Any]], step_id: str, where: Path) -> int:
    for index, step in enumerate(steps):
        if step.get('id') == step_id:
            return index
    msg = f'{where}: patch refers to no step "{step_id}"'
    raise FlowError(msg)


def _apply_patch(
    steps: list[dict[str, Any]],
    patch: dict[str, Any],
    where: Path,
) -> list[dict[str, Any]]:
    unknown = set(patch) - PATCH_KEYS
    if unknown:
        msg = f'{where}: unknown patch op(s): {", ".join(sorted(unknown))}'
        raise FlowError(msg)
    steps = [dict(step) for step in steps]
    for step_id, changes in patch.get('replace', {}).items():
        if 'id' in changes:
            msg = f'{where}: patch.replace.{step_id} cannot change "id"'
            raise FlowError(msg)
        index = _step_index(steps, step_id, where)
        steps[index] = {**steps[index], **changes}
    for step_id in patch.get('remove', []):
        del steps[_step_index(steps, step_id, where)]
    for step_id, new in patch.get('insert_after', {}).items():
        index = _step_index(steps, step_id, where) + 1
        steps[index:index] = new
    for step_id, new in patch.get('insert_before', {}).items():
        index = _step_index(steps, step_id, where)
        steps[index:index] = new
    steps.extend(patch.get('append', []))
    return steps


def _resolve(
    path: Path,
    layers: Layers,
    chain: tuple[Path, ...],
) -> dict[str, Any]:
    if path in chain:
        names = ' -> '.join(p.stem for p in (*chain, path))
        msg = f'extends cycle: {names}'
        raise FlowError(msg)
    data = _read_toml(path)
    if 'extends' not in data:
        if 'patch' in data:
            msg = f'{path}: [patch] needs "extends"'
            raise FlowError(msg)
        return data
    parent_path = _find_named(str(data['extends']), layers, skip=path)
    merged = _resolve(parent_path, layers, (*chain, path))
    merged.pop('name', None)
    for key, value in data.items():
        if key not in {'extends', 'patch'}:
            merged[key] = value
    merged['steps'] = _apply_patch(
        merged.get('steps', []),
        data.get('patch', {}),
        path,
    )
    return merged


def _str_list(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(v, str) for v in value
    ):
        msg = f'{what} must be a list of strings'
        raise FlowError(msg)
    return tuple(value)


def _positive_int(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        msg = f'{what} must be a positive integer'
        raise FlowError(msg)
    return value


def _artifact(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        msg = f'{what} must be a file name'
        raise FlowError(msg)
    parts = PurePosixPath(value)
    if parts.is_absolute() or '..' in parts.parts or '\\' in value:
        msg = f'{what} must be a relative path inside the run dir: {value}'
        raise FlowError(msg)
    return value


def _build_step(raw: object, where: str) -> Step:
    if not isinstance(raw, dict):
        msg = f'{where}: each step must be a table'
        raise FlowError(msg)
    unknown = set(raw) - STEP_KEYS
    if unknown:
        msg = f'{where}: unknown step key(s): {", ".join(sorted(unknown))}'
        raise FlowError(msg)
    for required in ('id', 'skill'):
        if not isinstance(raw.get(required), str) or not raw[required]:
            msg = f'{where}: every step needs a string "{required}"'
            raise FlowError(msg)
    label = f'{where}: step "{raw["id"]}"'
    gate = raw.get('gate', 'none')
    if gate not in GATES:
        msg = f'{label}: gate must be one of {", ".join(GATES)}'
        raise FlowError(msg)
    timeout = raw.get('timeout')
    return Step(
        id=raw['id'],
        skill=raw['skill'],
        inputs=tuple(
            _artifact(item, f'{label} "in" entry')
            for item in _str_list(raw.get('in', []), f'{label} "in"')
        ),
        out=None
        if raw.get('out') is None
        else _artifact(raw['out'], f'{label} "out"'),
        gate=gate,
        model=raw.get('model'),
        allow_tools=_str_list(
            raw.get('allow_tools', []),
            f'{label} allow_tools',
        ),
        allow_all=bool(raw.get('allow_all', False)),
        timeout=None
        if timeout is None
        else _positive_int(timeout, f'{label} timeout'),
    )


def _build_flow(data: dict[str, Any], path: Path) -> Flow:
    where = str(path)
    host = data.get('host', 'copilot')
    if host not in HOSTS:
        msg = f'{where}: host must be one of {", ".join(HOSTS)}'
        raise FlowError(msg)
    raw_steps = data.get('steps', [])
    if not raw_steps:
        msg = f'{where}: flow has no steps'
        raise FlowError(msg)
    steps = tuple(_build_step(raw, where) for raw in raw_steps)
    seen: set[str] = set()
    for step in steps:
        if step.id in seen:
            msg = f'{where}: duplicate step id "{step.id}"'
            raise FlowError(msg)
        seen.add(step.id)
    return Flow(
        name=str(data.get('name', path.stem)),
        steps=steps,
        host=host,
        context=_str_list(data.get('context', []), f'{where}: context'),
        allow_tools=_str_list(
            data.get('allow_tools', []),
            f'{where}: allow_tools',
        ),
        allow_all=bool(data.get('allow_all', False)),
        model=data.get('model'),
        max_steps=_positive_int(
            data.get('max_steps', DEFAULT_MAX_STEPS),
            f'{where}: max_steps',
        ),
        source=path,
    )


def flow_path(name: str | None, layers: Layers) -> Path:
    if name is None:
        repo_flow = layers.repo / '.skill-tree' / 'flow.toml'
        if repo_flow.is_file():
            return repo_flow
        name = 'default'
    return _find_named(name, layers, skip=None)


def load_flow(name: str | None, layers: Layers) -> Flow:
    path = flow_path(name, layers)
    return _build_flow(_resolve(path, layers, ()), path)


def list_flows(layers: Layers) -> list[tuple[str, Path]]:
    found: dict[str, Path] = {}
    repo_flow = layers.repo / '.skill-tree' / 'flow.toml'
    if repo_flow.is_file():
        found['(repo default)'] = repo_flow
    for directory in _layer_dirs(layers):
        if directory.is_dir():
            for path in sorted(directory.glob('*.toml')):
                found.setdefault(path.stem, path)
    return list(found.items())


# --- checking -------------------------------------------------------------


def check_flow(flow: Flow, skills: dict[str, Path]) -> list[str]:
    problems = [
        f'step "{step.id}": skill "{step.skill}" not found'
        for step in flow.steps
        if step.skill not in skills
    ]
    problems += [
        f'context skill "{name}" not found'
        for name in flow.context
        if name not in skills
    ]
    produced: set[str] = set()
    for step in flow.steps:
        problems += [
            f'step "{step.id}": input "{item}" is not produced by an'
            ' earlier step'
            for item in step.inputs
            if item not in produced
        ]
        if step.out:
            produced.add(step.out)
    return problems


def render_plan(flow: Flow, skills: dict[str, Path]) -> str:
    def where(name: str) -> str:
        return str(skills[name]) if name in skills else 'MISSING'

    rows = [('#', 'step', 'skill', 'gate', 'source')]
    rows += [
        (str(n), step.id, step.skill, step.gate, where(step.skill))
        for n, step in enumerate(flow.steps, 1)
    ]
    rows += [('ctx', '-', name, '-', where(name)) for name in flow.context]
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = [
        '  '.join(cell.ljust(w) for cell, w in zip(row, widths, strict=False))
        + '  '
        + row[4]
        for row in rows
    ]
    header = f'flow: {flow.name}  ({flow.source})  host: {flow.host}'
    return '\n'.join([header, *lines])


# --- host -----------------------------------------------------------------


class CopilotHost:
    def __init__(self, binary: str = 'copilot') -> None:
        self.binary = binary

    def _flags(self, options: RunOptions) -> list[str]:
        flags: list[str] = []
        if options.model:
            flags += ['--model', options.model]
        for tool in options.allow_tools:
            flags += ['--allow-tool', tool]
        if options.allow_all:
            flags.append('--allow-all-tools')
        return flags

    def list_skills(self, cwd: Path) -> dict[str, Path]:
        try:
            result = subprocess.run(
                [self.binary, 'skill', 'list', '--json'],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            msg = f'copilot CLI not found ({self.binary}); is it installed?'
            raise FlowError(msg) from exc
        if result.returncode != 0:
            msg = f'copilot skill list failed: {result.stderr.strip()}'
            raise FlowError(msg)
        try:
            entries = json.loads(result.stdout)
        except ValueError as exc:
            msg = 'copilot skill list --json returned unparseable output'
            raise FlowError(msg) from exc
        skills: dict[str, Path] = {}
        for entry in entries:
            if entry.get('enabled', True):
                skills.setdefault(entry['name'], Path(entry['path']))
        return skills

    def run_headless(
        self,
        prompt: str,
        options: RunOptions,
        log: Path,
    ) -> int:
        argv = [
            self.binary,
            '-p',
            prompt,
            '--output-format',
            'json',
            *self._flags(options),
        ]
        with log.open('w') as sink:
            try:
                return subprocess.run(
                    argv,
                    cwd=options.cwd,
                    stdout=sink,
                    check=False,
                    timeout=options.timeout,
                ).returncode
            except subprocess.TimeoutExpired:
                return TIMEOUT_EXIT

    def run_interactive(self, prompt: str, options: RunOptions) -> int:
        argv = [self.binary, '-i', prompt, *self._flags(options)]
        return subprocess.run(argv, cwd=options.cwd, check=False).returncode


# Flows name tools in Copilot's vocabulary; Claude spells them differently.
CLAUDE_TOOLS = {'write': 'Write', 'read': 'Read', 'shell': 'Bash'}


def claude_tool(tool: str) -> str:
    base, paren, rest = tool.partition('(')
    return CLAUDE_TOOLS.get(base, base) + paren + rest


def _skill_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if (p / 'SKILL.md').is_file())


class ClaudeHost:
    """Claude Code has no `skill list`, so discovery mirrors its rules.

    Repo `.claude/skills` beats `~/.claude/skills` beats plugin skills for
    a bare name; plugin skills are also always reachable as
    `<plugin>:<skill>`, so a flow written with Copilot's bare names
    still resolves against the skill-tree plugin.
    """

    def __init__(
        self,
        binary: str = 'claude',
        home: Path | None = None,
    ) -> None:
        self.binary = binary
        self.home = home or Path.home()

    def _plugins(self, cwd: Path) -> list[tuple[str, Path]]:
        try:
            result = subprocess.run(
                [self.binary, 'plugin', 'list', '--json'],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            msg = f'claude CLI not found ({self.binary}); is it installed?'
            raise FlowError(msg) from exc
        if result.returncode != 0:
            msg = f'claude plugin list failed: {result.stderr.strip()}'
            raise FlowError(msg)
        try:
            entries = json.loads(result.stdout)
        except ValueError as exc:
            msg = 'claude plugin list --json returned unparseable output'
            raise FlowError(msg) from exc
        return [
            (str(e['id']).split('@', 1)[0], Path(e['installPath']))
            for e in entries
            if e.get('enabled') and e.get('installPath')
        ]

    def list_skills(self, cwd: Path) -> dict[str, Path]:
        skills: dict[str, Path] = {}
        for root in (
            cwd / '.claude' / 'skills',
            self.home / '.claude' / 'skills',
        ):
            for path in _skill_dirs(root):
                skills.setdefault(path.name, path)
        for plugin, install in self._plugins(cwd):
            for path in _skill_dirs(install / 'skills'):
                skills.setdefault(f'{plugin}:{path.name}', path)
                skills.setdefault(path.name, path)
        return skills

    def _flags(self, options: RunOptions) -> list[str]:
        flags: list[str] = []
        if options.model:
            flags += ['--model', options.model]
        if options.allow_all:
            flags += ['--permission-mode', 'bypassPermissions']
        elif options.allow_tools:
            tools = ','.join(claude_tool(t) for t in options.allow_tools)
            flags += ['--allowedTools', tools]
        return flags

    def run_headless(
        self,
        prompt: str,
        options: RunOptions,
        log: Path,
    ) -> int:
        argv = [
            self.binary,
            '-p',
            '--output-format',
            'stream-json',
            '--verbose',
            *self._flags(options),
            '--',
            prompt,
        ]
        with log.open('w') as sink:
            try:
                return subprocess.run(
                    argv,
                    cwd=options.cwd,
                    stdout=sink,
                    check=False,
                    timeout=options.timeout,
                ).returncode
            except subprocess.TimeoutExpired:
                return TIMEOUT_EXIT

    def run_interactive(self, prompt: str, options: RunOptions) -> int:
        argv = [self.binary, *self._flags(options), '--', prompt]
        return subprocess.run(argv, cwd=options.cwd, check=False).returncode


def make_host(name: str) -> Host:
    return ClaudeHost() if name == 'claude' else CopilotHost()


# --- prompt ---------------------------------------------------------------


def build_prompt(
    step: Step,
    *,
    idea: str,
    run_dir: Path,
    skills: dict[str, Path],
    context: tuple[str, ...],
    headless: bool,
) -> str:
    lines = [
        f'skill-tree run [step:{step.id}]: one step of a multi-step flow.',
        '',
        (
            f'Follow the `{step.skill}` skill. Its instructions: '
            f'{skills[step.skill] / "SKILL.md"}'
        ),
    ]
    if context:
        lines += [
            '',
            'Background context: read these skills first, use throughout:',
        ]
        lines += [f'- {name}: {skills[name] / "SKILL.md"}' for name in context]
    lines += ['', f'Request: {idea}']
    if step.inputs:
        lines += ['', 'Input files (read them first):']
        lines += [f'- {run_dir / item}' for item in step.inputs]
    if step.out:
        lines += [
            '',
            f'Write your output to: {run_dir / step.out}',
            (
                'Overwrite that file with your complete final output for'
                ' this step. It is the only thing passed to the next step.'
            ),
        ]
    if headless:
        lines += [
            '',
            (
                'You are running unattended. Do not ask questions; make'
                ' reasonable assumptions and list them under an'
                ' "Assumptions" heading in your output.'
            ),
        ]
    return '\n'.join(lines)


# --- run state ------------------------------------------------------------


def find_repo_root(start: Path) -> Path:
    for directory in (start, *start.parents):
        if (directory / '.git').exists():
            return directory
    return start


def _ensure_git_exclude(repo: Path) -> None:
    info = repo / '.git' / 'info'
    if not (repo / '.git').is_dir():
        return
    info.mkdir(exist_ok=True)
    exclude = info / 'exclude'
    existing = exclude.read_text() if exclude.exists() else ''
    if EXCLUDE_LINE in existing.splitlines():
        return
    prefix = '' if not existing or existing.endswith('\n') else '\n'
    exclude.write_text(f'{existing}{prefix}{EXCLUDE_LINE}\n')


def new_run_dir(repo: Path) -> Path:
    runs = repo / RUNS_DIR
    runs.mkdir(parents=True, exist_ok=True)
    _ensure_git_exclude(repo)
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    candidate, n = runs / stamp, 1
    while candidate.exists():
        n += 1
        candidate = runs / f'{stamp}-{n}'
    candidate.mkdir()
    return candidate


def latest_run(repo: Path) -> Path | None:
    runs = repo / RUNS_DIR
    if not runs.is_dir():
        return None
    dirs = sorted(p for p in runs.iterdir() if (p / 'state.json').exists())
    if not dirs:
        dirs = sorted(p for p in runs.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


def read_state(run_dir: Path) -> dict[str, Any]:
    return dict(json.loads((run_dir / 'state.json').read_text()))


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    (run_dir / 'state.json').write_text(json.dumps(state, indent=2) + '\n')


def init_run(
    run_dir: Path,
    flow: Flow,
    idea: str,
    *,
    flow_arg: str | None = None,
    cwd: Path | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_state(
        run_dir,
        {
            'flow': flow_arg if flow_arg is not None else flow.name,
            'flow_arg': flow_arg,
            'host': flow.host,
            'idea': idea,
            'cwd': str(cwd or Path.cwd()),
            'created': datetime.now(UTC).isoformat(),
            'steps': {step.id: 'pending' for step in flow.steps},
        },
    )


# --- runner ---------------------------------------------------------------


def resume_hint(run_dir: Path) -> str:
    return f'skill-tree run --resume {run_dir.name}'


@dataclass
class _Run:
    flow: Flow
    run_dir: Path
    host: Host
    gate: GateIO
    state: dict[str, Any]
    skills: dict[str, Path]
    executed: int = 0
    total: int = field(init=False)

    def __post_init__(self) -> None:
        self.total = len(self.flow.steps)

    def set_status(self, step: Step, status: str) -> None:
        self.state['steps'][step.id] = status
        _write_state(self.run_dir, self.state)

    def options(self, step: Step) -> RunOptions:
        return RunOptions(
            cwd=Path(self.state.get('cwd') or Path.cwd()),
            model=step.model or self.flow.model,
            allow_tools=tuple(
                dict.fromkeys((*self.flow.allow_tools, *step.allow_tools)),
            ),
            allow_all=self.flow.allow_all or step.allow_all,
            timeout=step.timeout,
        )

    def pause(self, step: Step, status: str, why: str) -> int:
        self.set_status(step, status)
        print(f'⏸  {why}\n   resume: {resume_hint(self.run_dir)}')
        return PAUSED_EXIT

    def execute(self, step: Step) -> bool:
        number = [s.id for s in self.flow.steps].index(step.id) + 1
        missing = [i for i in step.inputs if not (self.run_dir / i).exists()]
        if missing:
            print(f'✗ {step.id}: missing input(s): {", ".join(missing)}')
            self.set_status(step, 'failed')
            return False
        self.executed += 1
        self.set_status(step, 'running')
        headless = step.gate != 'interactive'
        prompt = build_prompt(
            step,
            idea=self.state['idea'],
            run_dir=self.run_dir,
            skills=self.skills,
            context=self.flow.context,
            headless=headless,
        )
        print(f'→ [{number}/{self.total}] {step.id} ({step.skill})', end='')
        started = time.monotonic()
        if headless:
            log = self.run_dir / 'logs' / f'{step.id}.jsonl'
            log.parent.mkdir(exist_ok=True)
            print(' ...', flush=True)
            code = self.host.run_headless(prompt, self.options(step), log)
        else:
            print(' (interactive)', flush=True)
            code = self.host.run_interactive(prompt, self.options(step))
        elapsed = time.monotonic() - started
        out = self.run_dir / step.out if step.out else None
        ok = code == 0 and (
            out is None or (out.exists() and out.stat().st_size > 0)
        )
        if ok:
            where = f' -> {out}' if out else ''
            print(f'✓ {step.id} ({elapsed:.0f}s){where}')
            return True
        reason = f'exit {code}' if code else f'no output at {out}'
        print(f'✗ {step.id} failed ({reason}); log: {self.run_dir / "logs"}')
        self.set_status(step, 'failed')
        return False

    def open_editor(self, step: Step) -> None:
        if not step.out:
            print('   this step has no output file to edit')
            return
        editor = os.environ.get('EDITOR') or os.environ.get('VISUAL') or 'vi'
        subprocess.run(
            [*shlex.split(editor), str(self.run_dir / step.out)],
            check=False,
        )

    def approve(self, step: Step) -> int | None:
        """None when approved; an exit code when the run must stop."""
        if not self.gate.interactive:
            return self.pause(
                step,
                'awaiting-approval',
                f'{step.id} needs approval (no TTY)',
            )
        target = self.run_dir / step.out if step.out else self.run_dir
        while True:
            answer = (
                self.gate.ask(
                    f'{step.id}: review {target}\n'
                    '  [a]pprove  [e]dit  [r]erun  [q]uit > ',
                )
                .strip()
                .lower()[:1]
            )
            if answer == 'a':
                return None
            if answer == 'e':
                self.open_editor(step)
            elif answer == 'q':
                return self.pause(step, 'awaiting-approval', 'paused')
            elif answer == 'r':
                if self.executed >= self.flow.max_steps:
                    return self.pause(
                        step,
                        'awaiting-approval',
                        f'max_steps ({self.flow.max_steps}) reached',
                    )
                if not self.execute(step):
                    return 1
            else:
                print('   answer a, e, r or q')

    def step(self, step: Step) -> int | None:
        status = self.state['steps'][step.id]
        if status == 'done':
            return None
        if status != 'awaiting-approval':
            if step.gate == 'interactive' and not self.gate.interactive:
                return self.pause(
                    step,
                    'pending',
                    f'{step.id} is interactive and needs a TTY',
                )
            if self.executed >= self.flow.max_steps:
                return self.pause(
                    step,
                    'pending',
                    f'max_steps ({self.flow.max_steps}) reached',
                )
            if not self.execute(step):
                print(f'   resume: {resume_hint(self.run_dir)}')
                return 1
        if step.gate == 'approve':
            stop = self.approve(step)
            if stop is not None:
                return stop
        self.set_status(step, 'done')
        return None


def run_flow(
    flow: Flow,
    run_dir: Path,
    host: Host,
    gate: GateIO,
    *,
    start_from: str | None = None,
) -> int:
    state = read_state(run_dir)
    order = [step.id for step in flow.steps]
    old = state.get('steps', {})
    statuses = {sid: old.get(sid, 'pending') for sid in order}
    if start_from is not None:
        if start_from not in statuses:
            msg = f'--from: no step "{start_from}" (steps: {", ".join(order)})'
            raise FlowError(msg)
        for sid in order[order.index(start_from) :]:
            statuses[sid] = 'pending'
    state['steps'] = statuses
    _write_state(run_dir, state)

    if all(status == 'done' for status in statuses.values()):
        print(f'All steps already done in {run_dir}')
        return 0

    skills = host.list_skills(Path(state.get('cwd') or Path.cwd()))
    problems = check_flow(flow, skills)
    if problems:
        raise FlowError('\n'.join(problems))

    runner = _Run(flow, run_dir, host, gate, state, skills)
    for step in flow.steps:
        stop = runner.step(step)
        if stop is not None:
            return stop
    print(f'Done. Artifacts in {run_dir}')
    return 0


# --- CLI ------------------------------------------------------------------


def default_layers(cwd: Path) -> Layers:
    config = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Layers(
        repo=find_repo_root(cwd),
        user=Path(config) / 'skill-tree' / 'flows',
        builtin=ROOT / 'flows',
    )


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='skill-tree run',
        description='Run a flow of skills step by step (Copilot or Claude).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'flows: <repo>/.skill-tree/flow.toml, <repo>/.skill-tree/flows/,'
            '\n       ~/.config/skill-tree/flows/, then built-in.'
            '\n\nexamples:'
            '\n  skill-tree run "add dark mode"'
            '\n  skill-tree run --flow work --dry-run'
            '\n  skill-tree run --resume'
            '\n  skill-tree run --from spec'
            f'\n\nexit codes: 0 done, 1 error, 2 usage, {PAUSED_EXIT} paused'
        ),
    )
    parser.add_argument('idea', nargs='*', help='what to build (new run)')
    parser.add_argument('--flow', help='flow name (default: repo or default)')
    parser.add_argument(
        '--host',
        choices=HOSTS,
        help="override the flow's host (sticks for --resume)",
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='resolve the flow and its skills, run nothing',
    )
    parser.add_argument(
        '--resume',
        nargs='?',
        const='latest',
        metavar='RUN_ID',
        help='continue a run (default: latest)',
    )
    parser.add_argument(
        '--from',
        dest='start_from',
        metavar='STEP',
        help='re-run from STEP (implies --resume)',
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='list available flows',
    )
    parser.add_argument('--version', action='store_true')
    return parser


def _version() -> str:
    try:
        manifest = ROOT / '.claude-plugin' / 'plugin.json'
        return str(json.loads(manifest.read_text())['version'])
    except (OSError, ValueError, KeyError):
        return 'unknown'


def _resume_dir(repo: Path, run_id: str) -> Path:
    if run_id == 'latest':
        found = latest_run(repo)
        if found is None:
            msg = f'no runs found in {repo / RUNS_DIR}'
            raise FlowError(msg)
        return found
    run_dir = repo / RUNS_DIR / run_id
    if not (run_dir / 'state.json').exists():
        msg = f'no run "{run_id}" in {repo / RUNS_DIR}'
        raise FlowError(msg)
    return run_dir


def _dry_run(flow: Flow, host: Host, repo: Path) -> int:
    skills = host.list_skills(repo)
    print(render_plan(flow, skills), flush=True)
    problems = check_flow(flow, skills)
    for problem in problems:
        print(f'✗ {problem}', file=sys.stderr)
    if problems:
        print(
            '  (copilot skill list shows what Copilot can see from here)',
            file=sys.stderr,
        )
        return 1
    print('✓ flow resolves')
    return 0


def _main(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    layers = default_layers(cwd)
    if args.list:
        for name, path in list_flows(layers):
            print(f'{name.ljust(16)}  {path}')
        return 0

    resume = args.resume or ('latest' if args.start_from else None)
    if resume:
        run_dir = _resume_dir(layers.repo, resume)
        state = read_state(run_dir)
        flow = load_flow(args.flow or state.get('flow_arg'), layers)
        flow = replace(flow, host=args.host or state.get('host') or flow.host)
        if args.dry_run:
            return _dry_run(flow, make_host(flow.host), layers.repo)
    else:
        flow = load_flow(args.flow, layers)
        flow = replace(flow, host=args.host or flow.host)
        if args.dry_run:
            return _dry_run(flow, make_host(flow.host), layers.repo)
        if not args.idea:
            _parser().print_help()
            return 2
        run_dir = new_run_dir(layers.repo)
        init_run(
            run_dir,
            flow,
            ' '.join(args.idea),
            flow_arg=args.flow,
            cwd=cwd,
        )
        print(f'run: {run_dir}\nresume later: {resume_hint(run_dir)}')

    return run_flow(
        flow,
        run_dir,
        make_host(flow.host),
        GateIO(ask=input, interactive=_stdin_is_tty()),
        start_from=args.start_from,
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not argv:
        parser.print_help()
        return 2
    args = parser.parse_args(argv)
    if args.version:
        print(f'skill-tree run {_version()}')
        return 0
    try:
        return _main(args)
    except FlowError as exc:
        print(f'skill-tree run: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\ninterrupted; resume with: skill-tree run --resume')
        return 130


if __name__ == '__main__':
    sys.exit(main())
