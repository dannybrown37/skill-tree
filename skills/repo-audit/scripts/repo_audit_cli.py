#!/usr/bin/env python3
"""Deterministic half of the repo-audit checklist, over a working tree.

Every check here answers from files on disk. The sections that need a
tool actually run -- the test suite, mypy, ruff, `pre-commit run` -- are
reported as MANUAL with the command, because "the tool isn't installed"
and "the repo is fine" are different answers and only the caller can tell
them apart.

Configuration presence is still checked statically: a repo with no mypy
config fails section 2 without anyone running mypy.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

SKIP_DIRS = frozenset(
    {
        '.git',
        '.venv',
        'venv',
        'node_modules',
        '__pycache__',
        'dist',
        'build',
        '.mypy_cache',
        '.pytest_cache',
        '.ruff_cache',
    },
)

PYTHON_MARKERS = (
    'pyproject.toml',
    'setup.py',
    'setup.cfg',
    'requirements.txt',
)
NODE_MARKERS = ('package.json',)

REQUIRED_HOOKS = ('gitleaks', 'end-of-file-fixer')
PYTHON_HOOKS = ('ruff-check', 'ruff-format', 'mypy', 'pytest')
SHELL_HOOKS = ('shellcheck', 'shfmt')

GITIGNORE_SECRET_PATTERNS = ('.env', '*.pem', 'credentials')

ESLINT_CONFIGS = (
    'eslint.config.js',
    'eslint.config.mjs',
    'eslint.config.cjs',
    '.eslintrc.json',
    '.eslintrc.js',
    '.eslintrc.cjs',
    '.eslintrc.yaml',
    '.eslintrc.yml',
)

NODE_LOCKFILES = ('package-lock.json', 'yarn.lock', 'pnpm-lock.yaml')
PYTHON_DEPENDENCY_MARKERS = ('requirements.txt', 'Pipfile', 'setup.py')
PYTHON_LOCKFILES = (
    'uv.lock',
    'poetry.lock',
    'requirements.lock',
    'Pipfile.lock',
)

SECRET_SUFFIXES = frozenset({'.py', '.ts', '.js', '.tsx', '.jsx', '.sh'})
SECRET_ASSIGNMENT_RE = re.compile(
    r'\b(password|secret|token|api_key|apikey)\s*[=:]\s*[\'"]([^\'"]{6,})[\'"]',
    re.IGNORECASE,
)
# A literal that resolves at runtime isn't a hardcoded secret.
SECRET_ALLOWED_RE = re.compile(
    r'os\.environ|os\.getenv|process\.env|getenv|\$\{|\$\(|secretsmanager',
    re.IGNORECASE,
)
TEST_MARKERS = ('test_', '_test.', '.test.', '.spec.', 'conftest')

README_PLACEHOLDERS = (
    'getting started with create react app',
    'this project was bootstrapped',
    'welcome to your new project',
    'nuxt 3 minimal starter',
)
README_MIN_BODY_CHARS = 40

# `>=` with nothing above it is what drifts; a range or a pin is fine.
UNBOUNDED_RE = re.compile(r'^([A-Za-z0-9._-]+)\s*>=[^,;]*$')

SHELL_SUFFIXES = frozenset({'.sh', '.bash'})
PYTHON_SUFFIXES = frozenset({'.py'})
NODE_SUFFIXES = frozenset({'.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'})

# Long enough for a real suite, short enough that a hung one is an answer.
TOOL_TIMEOUT_SECONDS = 120
PROBE_TIMEOUT_SECONDS = 15

TEST_RUNNERS = (
    ('pytest', ('uv', 'run', '--with', 'pytest', 'pytest', '-q')),
    ('npm test', ('npm', 'test')),
)

# Files that hold no logic worth a test of their own.
EXEMPT_MODULES = frozenset(
    {'__init__.py', 'conftest.py', 'setup.py', '__main__.py'},
)
LOGIC_SUFFIXES = frozenset({'.py', '.ts', '.tsx', '.js', '.jsx'})
LOGIC_RE = re.compile(r'^\s*(def |class |function |export function |=>)', re.M)

DOC_NAMES = ('CLAUDE.md', 'SKILL.md', 'AGENTS.md')
# How many offenders a detail line names before it stops being readable.
MAX_LISTED = 5
# A backticked token only counts as a path if it looks like one: it has a
# suffix or a slash, and no spaces. `pytest -q` is a command, not a file.
BACKTICK_RE = re.compile(r'`([^`\s]+)`')
# A real file reference ends in a short extension. Without that anchor,
# `/code-review`, `origin/develop`, and `pytest.mark.parametrize` all read
# as paths and every doc looks stale.
# Must contain a slash *and* end in a short extension. A bare `foo.py` in
# prose is a generic filename ("add an `__init__.py`"), not a claim about
# this repo, and treating it as one made every doc look stale.
PATHISH_RE = re.compile(r'^[\w.][\w./@-]*/[\w.@-]+\.[A-Za-z0-9]{1,6}$')


class Status(Enum):
    """Outcome of one checklist section."""

    PASS = 'pass'  # noqa: S105
    FAIL = 'fail'
    NA = 'n/a'
    MANUAL = 'manual'


@dataclass(frozen=True)
class CheckResult:
    """One section's verdict, with what to do about it."""

    number: int
    title: str
    status: Status
    detail: str


@dataclass(frozen=True)
class Stack:
    """What the repo is built out of, as the checks need to branch on it."""

    python: bool = False
    node: bool = False
    typescript: bool = False
    shell: bool = False

    @property
    def empty(self) -> bool:
        return not (self.python or self.node or self.shell)


class RepoAuditError(Exception):
    """The target can't be audited at all."""


def walk_files(root: Path) -> Iterable[Path]:
    """Every tracked-ish file, skipping build output and virtualenvs.

    Not `git ls-files`: the audit has to work on a tree that was handed
    over as a tarball, and an untracked secret is still a finding.
    """
    for path in root.rglob('*'):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def detect_stack(root: Path) -> Stack:
    """What to hold this repo to, inferred from manifests and sources.

    Sources count, not just manifests: a repo that is a pile of scripts
    with a mypy.ini and no pyproject.toml is still Python, and keying
    only on manifests made every language check silently n/a for it.
    """
    suffixes = {path.suffix for path in walk_files(root)}

    python = any(
        (root / marker).is_file() for marker in PYTHON_MARKERS
    ) or bool(suffixes & PYTHON_SUFFIXES)
    node = any((root / marker).is_file() for marker in NODE_MARKERS) or bool(
        suffixes & NODE_SUFFIXES,
    )
    return Stack(
        python=python,
        node=node,
        typescript=node and (root / 'tsconfig.json').is_file(),
        shell=bool(suffixes & SHELL_SUFFIXES),
    )


def _read(path: Path) -> str:
    """File text, or empty if it's unreadable or binary."""
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def _pyproject(root: Path) -> dict[str, object]:
    """Parsed pyproject, or empty if absent or malformed."""
    path = root / 'pyproject.toml'
    try:
        return tomllib.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}


def _missing(text: str, hooks: Iterable[str]) -> list[str]:
    return [hook for hook in hooks if f'id: {hook}' not in text]


def check_precommit(root: Path, stack: Stack) -> CheckResult:
    """Section 1 -- the hook config exists and covers the stack."""
    config = root / '.pre-commit-config.yaml'
    if not config.is_file():
        return CheckResult(
            1,
            'Pre-commit hooks',
            Status.FAIL,
            'no .pre-commit-config.yaml -- nothing runs before a commit. '
            'Add one with a linter, a formatter, a secret scanner, and '
            'end-of-file-fixer.',
        )

    text = _read(config)
    expected = list(REQUIRED_HOOKS)
    if stack.python:
        expected += PYTHON_HOOKS
    if stack.shell:
        expected += SHELL_HOOKS

    missing = _missing(text, expected)
    if missing:
        return CheckResult(
            1,
            'Pre-commit hooks',
            Status.FAIL,
            f'config present, hooks missing: {", ".join(missing)}. '
            f'Add them to .pre-commit-config.yaml.',
        )

    return CheckResult(
        1,
        'Pre-commit hooks',
        Status.PASS,
        f'{config.name} covers every hook this stack needs. '
        f'Run `pre-commit run --all-files` to confirm they pass.',
    )


def check_typecheck_config(root: Path, stack: Stack) -> CheckResult:
    """Section 2 -- a type checker is configured, and strictly."""
    if not (stack.python or stack.typescript):
        return CheckResult(
            2,
            'Type checking',
            Status.NA,
            'no Python or TypeScript in this repo.',
        )

    problems: list[str] = []

    if stack.python:
        configured = (
            (root / 'mypy.ini').is_file()
            or (root / '.mypy.ini').is_file()
            or 'mypy' in _pyproject(root).get('tool', {})  # type: ignore[operator]
            or '[mypy]' in _read(root / 'setup.cfg')
        )
        if not configured:
            problems.append(
                'no mypy config (mypy.ini, [tool.mypy], or setup.cfg)',
            )

    if stack.typescript:
        try:
            tsconfig = json.loads(_read(root / 'tsconfig.json'))
            strict = bool(tsconfig.get('compilerOptions', {}).get('strict'))
        except (ValueError, AttributeError):
            problems.append('tsconfig.json is not parseable JSON')
        else:
            if not strict:
                problems.append('tsconfig.json does not set strict: true')

    if problems:
        return CheckResult(
            2,
            'Type checking',
            Status.FAIL,
            '; '.join(problems) + '.',
        )

    return CheckResult(
        2,
        'Type checking',
        Status.PASS,
        'a type checker is configured. Run it bare (`uv run --with mypy '
        'mypy`, `npx tsc --noEmit`) to confirm it is clean.',
    )


def check_lint_config(root: Path, stack: Stack) -> CheckResult:
    """Section 3 -- a linter is configured for each language present."""
    if stack.empty:
        return CheckResult(
            3,
            'Linting and formatting',
            Status.NA,
            'nothing lintable detected.',
        )

    problems: list[str] = []

    if stack.python and not (
        (root / '.ruff.toml').is_file()
        or (root / 'ruff.toml').is_file()
        or 'ruff' in _pyproject(root).get('tool', {})  # type: ignore[operator]
    ):
        problems.append('no ruff config (.ruff.toml or [tool.ruff])')

    if stack.node and not any(
        (root / name).is_file() for name in ESLINT_CONFIGS
    ):
        problems.append('no eslint config')

    if problems:
        return CheckResult(
            3,
            'Linting and formatting',
            Status.FAIL,
            '; '.join(problems) + '.',
        )

    return CheckResult(
        3,
        'Linting and formatting',
        Status.PASS,
        'a linter is configured for every language present.',
    )


def _looks_like_a_test(path: Path) -> bool:
    name = path.name
    return any(marker in name for marker in TEST_MARKERS)


def _hardcoded_secrets(root: Path) -> list[str]:
    """Files with a literal assigned to a secret-shaped name."""
    hits: list[str] = []
    for path in walk_files(root):
        if path.suffix not in SECRET_SUFFIXES or _looks_like_a_test(path):
            continue
        for line in _read(path).splitlines():
            if SECRET_ASSIGNMENT_RE.search(
                line,
            ) and not SECRET_ALLOWED_RE.search(
                line,
            ):
                hits.append(str(path.relative_to(root)))
                break
    return hits


def check_secrets(root: Path) -> CheckResult:
    """Section 6 -- ignored patterns, a scanner, and no literals."""
    problems: list[str] = []

    gitignore = _read(root / '.gitignore')
    if not gitignore:
        problems.append('no .gitignore')
    else:
        missing = [
            pattern
            for pattern in GITIGNORE_SECRET_PATTERNS
            if pattern.strip('*') not in gitignore
        ]
        if missing:
            problems.append(f'.gitignore does not cover {", ".join(missing)}')

    precommit = _read(root / '.pre-commit-config.yaml')
    if precommit and 'gitleaks' not in precommit:
        problems.append('no gitleaks hook in pre-commit')

    hits = _hardcoded_secrets(root)
    if hits:
        problems.append(
            'secret-shaped literals in '
            f'{", ".join(sorted(hits)[:MAX_LISTED])}',
        )

    if problems:
        return CheckResult(
            6,
            'Secrets hygiene',
            Status.FAIL,
            '; '.join(problems) + '.',
        )

    return CheckResult(
        6,
        'Secrets hygiene',
        Status.PASS,
        'secret files ignored, scanner present, no literals found.',
    )


def _declared_dependencies(root: Path) -> list[str]:
    """Dependency specs declared in pyproject, if any."""
    project = _pyproject(root).get('project', {})
    declared = (
        project.get('dependencies', []) if isinstance(project, dict) else []
    )
    if not isinstance(declared, list):
        return []
    return [spec for spec in declared if isinstance(spec, str)]


def _unbounded_dependencies(root: Path) -> list[str]:
    """Declared deps with a floor and no ceiling."""
    return [
        match.group(1)
        for spec in _declared_dependencies(root)
        if (match := UNBOUNDED_RE.match(spec.strip()))
    ]


def check_pinning(root: Path) -> CheckResult:
    """Section 7 -- a lockfile exists and specs have a ceiling."""
    declares_python = bool(_declared_dependencies(root)) or any(
        (root / marker).is_file() for marker in PYTHON_DEPENDENCY_MARKERS
    )
    declares_node = (root / 'package.json').is_file()

    if not (declares_python or declares_node):
        return CheckResult(
            7,
            'Dependency pinning',
            Status.NA,
            'no declared dependencies -- nothing to lock.',
        )

    problems: list[str] = []

    if declares_python and not any(
        (root / name).is_file() for name in PYTHON_LOCKFILES
    ):
        problems.append('no Python lockfile (uv.lock, poetry.lock)')

    if declares_node and not any(
        (root / name).is_file() for name in NODE_LOCKFILES
    ):
        problems.append('no Node lockfile (package-lock.json, pnpm-lock.yaml)')

    unbounded = _unbounded_dependencies(root)
    if unbounded:
        problems.append(
            'unbounded specs (>= with no upper bound): '
            f'{", ".join(unbounded)}',
        )

    if problems:
        return CheckResult(
            7,
            'Dependency pinning',
            Status.FAIL,
            '; '.join(problems) + '.',
        )

    return CheckResult(
        7,
        'Dependency pinning',
        Status.PASS,
        'lockfile committed and every spec is bounded.',
    )


def check_readme(root: Path) -> CheckResult:
    """Section 9 -- the front door exists and says something."""
    readme = root / 'README.md'
    if not readme.is_file():
        return CheckResult(
            9,
            'README quality',
            Status.FAIL,
            'no README.md -- the repo has no front door.',
        )

    text = _read(readme)
    lowered = text.lower()
    hit = next(
        (marker for marker in README_PLACEHOLDERS if marker in lowered),
        None,
    )
    if hit:
        return CheckResult(
            9,
            'README quality',
            Status.FAIL,
            f'README.md is still framework placeholder text ({hit!r}). '
            f'Replace it with what this project is and why to care.',
        )

    body = '\n'.join(
        line for line in text.splitlines() if not line.lstrip().startswith('#')
    ).strip()
    if len(body) < README_MIN_BODY_CHARS:
        return CheckResult(
            9,
            'README quality',
            Status.FAIL,
            'README.md is a heading with no body. The first paragraph '
            'should answer what this is and why to care.',
        )

    return CheckResult(
        9,
        'README quality',
        Status.PASS,
        'README.md exists with real content. Its claims still need '
        'reading against the code -- see section 8.',
    )


def _run(
    command: Sequence[str],
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str] | None:
    """Run a command, or None if it can't be run or wouldn't finish.

    None is deliberately not a failure: a missing tool and a hung suite
    are both "no verdict available here", which the caller reports as
    MANUAL rather than pretending the repo is broken.
    """
    try:
        return subprocess.run(  # noqa: S603
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _has_logic(path: Path) -> bool:
    """Whether a module defines anything, as opposed to just constants."""
    return bool(LOGIC_RE.search(_read(path)))


def untested_modules(root: Path) -> list[str]:
    """Logic modules with no test file anywhere naming them."""
    test_files = [
        path for path in walk_files(root) if _looks_like_a_test(path)
    ]
    stems = {
        path.stem.replace('test_', '')
        .replace('.test', '')
        .replace('.spec', '')
        for path in test_files
    }
    # Name matching alone is too strict: this repo tests `repo_audit_cli.py`
    # from `test_repo_audit.py`. A test that imports the module counts.
    imported = '\n'.join(_read(path) for path in test_files)

    return sorted(
        str(path.relative_to(root))
        for path in walk_files(root)
        if path.suffix in LOGIC_SUFFIXES
        and not _looks_like_a_test(path)
        and path.name not in EXEMPT_MODULES
        and _has_logic(path)
        and path.stem not in stems
        and path.stem not in imported
    )


def _test_runner(root: Path, stack: Stack) -> tuple[str, Sequence[str]] | None:
    """The suite this repo would run, if it has one."""
    has_tests = any(_looks_like_a_test(path) for path in walk_files(root))
    if not has_tests:
        return None
    if stack.python:
        return TEST_RUNNERS[0]
    if stack.node:
        return TEST_RUNNERS[1]
    return None


def _no_suite(untested: list[str]) -> CheckResult:
    """Section 4 when the repo has no test files at all."""
    if untested:
        return CheckResult(
            4,
            'Tests exist and pass',
            Status.FAIL,
            f'no test files at all; {len(untested)} module(s) with logic: '
            f'{", ".join(untested[:MAX_LISTED])}.',
        )
    return CheckResult(
        4,
        'Tests exist and pass',
        Status.NA,
        'no test files and no modules that need them.',
    )


def check_tests(root: Path, stack: Stack, *, run: bool) -> CheckResult:
    """Section 4 -- the suite exists, passes, and covers each module."""
    runner = _test_runner(root, stack)
    untested = untested_modules(root)

    if runner is None:
        return _no_suite(untested)

    name, command = runner
    printable = ' '.join(command)

    if not run:
        if untested:
            return CheckResult(
                4,
                'Tests exist and pass',
                Status.FAIL,
                f'{len(untested)} module(s) with no test file: '
                f'{", ".join(untested[:MAX_LISTED])}. '
                f'Suite not run -- `{printable}`.',
            )
        return CheckResult(
            4,
            'Tests exist and pass',
            Status.MANUAL,
            f'{name} suite found but not run (pass --run). Run `{printable}`.',
        )

    completed = _run(command, root, TOOL_TIMEOUT_SECONDS)
    if completed is None:
        return CheckResult(
            4,
            'Tests exist and pass',
            Status.MANUAL,
            f'`{printable}` could not be run here (missing tool, or it '
            f'exceeded {TOOL_TIMEOUT_SECONDS}s). Run it yourself.',
        )

    problems: list[str] = []
    if completed.returncode != 0:
        tail = (completed.stdout or completed.stderr).strip().splitlines()
        problems.append(
            f'`{printable}` exited {completed.returncode}: '
            f'{tail[-1] if tail else "no output"}',
        )
    if untested:
        problems.append(
            f'{len(untested)} module(s) with no test file: '
            f'{", ".join(untested[:MAX_LISTED])}',
        )

    if problems:
        return CheckResult(
            4,
            'Tests exist and pass',
            Status.FAIL,
            '; '.join(problems) + '.',
        )

    summary_line = (completed.stdout or '').strip().splitlines()
    return CheckResult(
        4,
        'Tests exist and pass',
        Status.PASS,
        f'`{printable}` passed'
        + (f': {summary_line[-1]}' if summary_line else '')
        + '. Every logic module has a test file.',
    )


def find_entrypoints(root: Path) -> dict[str, Path]:
    """Every command this repo asks a human to run, by name."""
    found: dict[str, Path] = {}

    scripts = _pyproject(root).get('project', {})
    if isinstance(scripts, dict):
        for name in scripts.get('scripts', {}) or {}:
            target = root / 'scripts' / str(name)
            found[str(name)] = target

    try:
        package = json.loads(_read(root / 'package.json'))
        binaries = package.get('bin', {})
    except (ValueError, AttributeError):
        binaries = {}
    if isinstance(binaries, dict):
        for name, rel in binaries.items():
            found[str(name)] = root / str(rel)
    elif isinstance(binaries, str):
        found[root.name] = root / binaries

    for path in walk_files(root):
        if (
            path.parent.name == 'scripts'
            and not _looks_like_a_test(path)
            and path.stat().st_mode & 0o111
        ):
            found[path.name] = path

    # A declared-but-missing entrypoint is kept, not filtered out: it is a
    # real finding, and probing reports it as unexecutable.
    return found


def check_entrypoints(root: Path) -> CheckResult:
    """Section 5 -- list the entrypoints; never run them.

    Deliberately not probed, even under --run. Finding out whether
    `--version` works means *executing* the thing, and an entrypoint is
    exactly the kind of script that does something when you do: an early
    version of this check ran `new-skill.sh --version` and created a skill
    directory named `--version`. Discovering a CLI is safe; invoking one
    is the user's call, so this prints the commands instead.
    """
    entrypoints = find_entrypoints(root)
    if not entrypoints:
        return CheckResult(
            5,
            'CLI ergonomics',
            Status.NA,
            'no CLI entrypoints found.',
        )

    listed = ', '.join(sorted(entrypoints)[:MAX_LISTED])
    extra = len(entrypoints) - MAX_LISTED
    more = f' (+{extra} more)' if extra > 0 else ''
    return CheckResult(
        5,
        'CLI ergonomics',
        Status.MANUAL,
        f'{len(entrypoints)} entrypoint(s): {listed}{more}. Not probed -- '
        f'probing means executing them. For each, check `--version` prints '
        f'and exits 0 with no config, a bare run prints help, and any '
        f'prompt fails cleanly under `< /dev/null`.',
    )


def referenced_paths(text: str) -> set[str]:
    """Backticked tokens that look like repo paths, not commands."""
    found: set[str] = set()
    for token in BACKTICK_RE.findall(text):
        if '://' in token or not PATHISH_RE.match(token):
            continue
        if '/' not in token and '.' not in token:
            continue
        if token.startswith('-') or token.endswith('/'):
            continue
        found.add(token)
    return found


def check_docs_freshness(root: Path) -> CheckResult:
    """Section 8 -- every path a doc names still exists."""
    docs = [path for path in walk_files(root) if path.name in DOC_NAMES]
    if not docs:
        return CheckResult(
            8,
            'CLAUDE.md / SKILL.md freshness',
            Status.NA,
            'no CLAUDE.md, SKILL.md, or AGENTS.md in this repo.',
        )

    dangling: list[str] = []
    for doc in docs:
        for token in sorted(referenced_paths(_read(doc))):
            # Relative to the doc or to the root -- both are how people
            # write these, and a hit either way means it is not stale.
            if (root / token).exists() or (doc.parent / token).exists():
                continue
            dangling.append(f'{doc.relative_to(root)} -> {token}')

    if dangling:
        return CheckResult(
            8,
            'CLAUDE.md / SKILL.md freshness',
            Status.FAIL,
            f'{len(dangling)} dangling reference(s): '
            f'{"; ".join(dangling[:MAX_LISTED])}.',
        )

    return CheckResult(
        8,
        'CLAUDE.md / SKILL.md freshness',
        Status.PASS,
        f'every path named by {len(docs)} doc(s) still exists. Framework and '
        f'dependency names still need a human read.',
    )


def run_checks(root: Path, *, run: bool = False) -> list[CheckResult]:
    """Every section, in the order the skill states them."""
    if not root.is_dir():
        message = f'{root} is not a directory'
        raise RepoAuditError(message)

    stack = detect_stack(root)
    if stack.empty and not (root / '.git').exists():
        message = (
            f'{root} has no dependency manifest, no scripts, and no .git -- '
            f'point this at a repo root'
        )
        raise RepoAuditError(message)

    return sorted(
        [
            check_precommit(root, stack),
            check_typecheck_config(root, stack),
            check_lint_config(root, stack),
            check_secrets(root),
            check_pinning(root),
            check_readme(root),
            check_tests(root, stack, run=run),
            check_entrypoints(root),
            check_docs_freshness(root),
        ],
        key=lambda result: result.number,
    )


STATUS_ORDER = (Status.FAIL, Status.MANUAL, Status.NA, Status.PASS)
DEFAULT_COMMAND = 'audit'
TOP_LEVEL_FLAGS = frozenset({'-h', '--help', '--version'})
EXIT_OK = 0
EXIT_FAILED_CHECK = 1
EXIT_UNUSABLE = 2


def with_default_command(argv: list[str]) -> list[str]:
    """Let the only subcommand be implied.

    `repo-audit ./x` and `repo-audit audit ./x` are the same run, and a bare
    `repo-audit` is that run against the default directory. There is exactly
    one subcommand, so requiring it is pure ceremony -- but it stays
    accepted, because it is what existing scripts and docs already type.
    Flags the top-level parser owns (`--version`, `-h`) still have to
    reach it, so they pass through untouched.
    """
    if argv and (argv[0] in TOP_LEVEL_FLAGS or argv[0] == DEFAULT_COMMAND):
        return argv
    return [DEFAULT_COMMAND, *argv]


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


def summary(results: list[CheckResult]) -> str:
    """The one line a reader takes away."""
    counts = {
        status: sum(1 for result in results if result.status is status)
        for status in STATUS_ORDER
    }
    return (
        f'{counts[Status.PASS]} passed, {counts[Status.FAIL]} failed, '
        f'{counts[Status.MANUAL]} need a tool run, '
        f'{counts[Status.NA]} not applicable'
    )


def render(results: list[CheckResult]) -> str:
    """Human-readable report, worst first within the checklist order."""
    lines: list[str] = []
    for status in STATUS_ORDER:
        matching = [result for result in results if result.status is status]
        if not matching:
            continue
        lines.append(status.value.upper())
        for result in matching:
            lines.append(f'  {result.number}. {result.title}')
            lines.extend(f'     {line}' for line in result.detail.splitlines())
        lines.append('')
    lines.append(summary(results))
    return '\n'.join(lines).rstrip() + '\n'


def as_json(results: list[CheckResult]) -> str:
    """The same report, for a caller that wants to branch on it."""
    return json.dumps(
        {
            'checks': [
                {
                    'number': result.number,
                    'title': result.title,
                    'status': result.status.value,
                    'detail': result.detail,
                }
                for result in results
            ],
            'summary': summary(results),
        },
        indent=2,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. 0 clean, 1 a check failed, 2 nothing to audit."""
    parser = argparse.ArgumentParser(
        prog='repo-audit',
        description="The repo-audit checklist's deterministic half.",
        epilog=(
            '`audit` is implied: `repo-audit .` and '
            '`repo-audit audit .` are the same run, and a bare '
            '`repo-audit` runs it against the current directory.'
        ),
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'repo-audit {version()}',
    )
    subparsers = parser.add_subparsers(dest='command')

    audit = subparsers.add_parser(
        'audit',
        help='run the checklist over a repo root',
    )
    audit.add_argument(
        'directory',
        nargs='?',
        default='.',
        type=Path,
        help='repo root; defaults to cwd',
    )
    audit.add_argument(
        '--run',
        action='store_true',
        help='actually run the test suite (slower; without it section 4 '
        'reports MANUAL). Never runs your CLI entrypoints -- see section 5.',
    )
    audit.add_argument(
        '--json',
        action='store_true',
        dest='as_json',
        help='machine-readable output',
    )

    raw = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(with_default_command(raw))

    try:
        results = run_checks(args.directory, run=args.run)
    except RepoAuditError as error:
        print(f'repo-audit: {error}', file=sys.stderr)
        return EXIT_UNUSABLE

    print(as_json(results) if args.as_json else render(results), end='')

    failed = any(result.status is Status.FAIL for result in results)
    return EXIT_FAILED_CHECK if failed else EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
