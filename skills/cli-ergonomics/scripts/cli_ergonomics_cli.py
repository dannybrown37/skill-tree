#!/usr/bin/env python3
"""Static linter for the cli-ergonomics skill's binary rules.

Three rules, all decidable from source: `--version` exists, a bare
invocation prints help rather than an argument error, and every prompt is
TTY-guarded.

Nothing here executes an entrypoint, and nothing here should ever start.
Probing a CLI means running it, and an entrypoint is exactly the kind of
script that does something when you do -- an earlier probe in this repo
ran `new-skill.sh --version` and created a skill directory named
`--version`. Static analysis is weaker and safe; the skill's own
`**Check:**` lines tell the human how to confirm at runtime.
"""

import argparse
import ast
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED_CHECK = 1
EXIT_UNUSABLE = 2

DEFAULT_COMMAND = 'lint'
TOP_LEVEL_FLAGS = frozenset({'-h', '--help', '--version'})

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

# Shell helpers (`bootstrap.sh`, `install.sh`) are plumbing a human runs
# once, not versioned CLIs. `--include-helpers` opts them back in.
HELPER_SUFFIXES = frozenset({'.sh', '.bash'})
TEST_MARKERS = ('test_', '_test.', '.test.', '.spec.', 'conftest')
# A hook is wired into a config and fired by a harness, never typed by a
# human, so the skill's rules don't apply to it.
HOOK_MARKERS = ('_hook.', 'hook_')

PYTHON_INPUT_RE = re.compile(r'(?<![\w.])input\s*\(')
SHELL_READ_RE = re.compile(r'(?m)^\s*read\s+')
TTY_GUARD_RE = re.compile(r'isatty|-t\s*0\b|-t\s*1\b')
EXPLICIT_HELP_RE = re.compile(r'print_help|format_help|print_usage')
PYTHON_SHEBANG_RE = re.compile(r'^#!.*python')
SHELL_SHEBANG_RE = re.compile(r'^#!.*\b(ba|z|da)?sh\b')
# A wrapper points at its module by sibling filename; that module is where
# the argument handling actually lives.
SIBLING_RE = re.compile(r'[\w.-]+\.(?:py|js|mjs|cjs|ts)')

OPTIONAL_NARGS = frozenset({'?', '*'})
MAX_LISTED = 5


class Status(Enum):
    """Outcome of one rule against one entrypoint."""

    PASS = 'pass'  # noqa: S105
    FAIL = 'fail'
    MANUAL = 'manual'


@dataclass(frozen=True)
class Check:
    """One rule's verdict, with what to do about it."""

    rule: str
    status: Status
    detail: str


@dataclass(frozen=True)
class CliReport:
    """Every rule's verdict for one entrypoint."""

    name: str
    path: Path
    checks: list[Check]

    @property
    def failed(self) -> bool:
        return any(check.status is Status.FAIL for check in self.checks)


class CliErgonomicsError(Exception):
    """The target can't be linted at all."""


def _read(path: Path) -> str:
    """File text, or empty if it's unreadable or binary."""
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def _looks_like_a_test(path: Path) -> bool:
    return any(marker in path.name for marker in TEST_MARKERS)


def _looks_like_a_hook(path: Path) -> bool:
    return any(marker in path.name for marker in HOOK_MARKERS)


def _walk(root: Path) -> Iterable[Path]:
    for path in root.rglob('*'):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def find_clis(
    root: Path,
    *,
    include_helpers: bool = False,
) -> dict[str, Path]:
    """Every command this repo asks a human to run, by name.

    A declared-but-missing entrypoint is kept rather than filtered out:
    a `[project.scripts]` name with no file behind it is a finding.
    """
    found: dict[str, Path] = {}

    try:
        pyproject = tomllib.loads(_read(root / 'pyproject.toml'))
    except tomllib.TOMLDecodeError:
        pyproject = {}
    project = pyproject.get('project', {})
    if isinstance(project, dict):
        for name in project.get('scripts', {}) or {}:
            found[str(name)] = root / 'scripts' / str(name)

    try:
        binaries = json.loads(_read(root / 'package.json')).get('bin', {})
    except (ValueError, AttributeError):
        binaries = {}
    if isinstance(binaries, dict):
        for name, rel in binaries.items():
            found[str(name)] = root / str(rel)
    elif isinstance(binaries, str):
        found[root.name] = root / binaries

    for path in _walk(root):
        if (
            path.parent.name == 'scripts'
            and not _looks_like_a_test(path)
            and not _looks_like_a_hook(path)
            and path.stat().st_mode & 0o111
        ):
            found[path.name] = path

    return {
        name: path
        for name, path in found.items()
        if include_helpers or Path(name).suffix not in HELPER_SUFFIXES
    }


def sources_for(entrypoint: Path) -> list[Path]:
    """The entrypoint plus the sibling module it hands off to.

    A wrapper that `exec`s `foo_cli.py` holds none of the argument
    handling, so linting the wrapper alone reports every rule as missing.
    """
    if not entrypoint.is_file():
        return []
    sources = [entrypoint]
    for name in dict.fromkeys(SIBLING_RE.findall(_read(entrypoint))):
        sibling = entrypoint.parent / name
        if sibling.is_file() and sibling != entrypoint:
            sources.append(sibling)
    return sources


def _is_shell(path: Path, text: str) -> bool:
    return path.suffix in HELPER_SUFFIXES or bool(
        SHELL_SHEBANG_RE.match(text),
    )


def _is_python(path: Path, text: str) -> bool:
    return (
        path.suffix == '.py'
        or bool(PYTHON_SHEBANG_RE.match(text))
        or 'import argparse' in text
    )


def _prompt_patterns(path: Path, text: str) -> tuple[re.Pattern[str], ...]:
    """How this file could be prompting.

    An extensionless script with no shebang could be either language, so
    it is held to both patterns rather than silently to the wrong one.
    """
    if _is_shell(path, text):
        return (SHELL_READ_RE,)
    if _is_python(path, text):
        return (PYTHON_INPUT_RE,)
    return (PYTHON_INPUT_RE, SHELL_READ_RE)


def check_version(sources: Sequence[Path]) -> Check:
    """`--version` is handled somewhere in the entrypoint's own source."""
    if not sources:
        return Check(
            'version',
            Status.FAIL,
            'entrypoint is declared but not readable -- nothing to run, so '
            '`--version` cannot work.',
        )
    if any('--version' in _read(path) for path in sources):
        return Check(
            'version',
            Status.PASS,
            'handles `--version`. Confirm it exits 0 with no config: '
            '`<cli> --version`.',
        )
    return Check(
        'version',
        Status.FAIL,
        'no `--version` handling. Every versioned CLI prints its own '
        'version and exits 0, with no config, network, or credentials.',
    )


def _required_positionals(tree: ast.AST) -> list[str]:
    """Positionals argparse will error on when the CLI is run bare."""
    required: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != 'add_argument':
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        name = node.args[0].value
        if not isinstance(name, str) or name.startswith('-'):
            continue
        nargs = next(
            (kw.value for kw in node.keywords if kw.arg == 'nargs'),
            None,
        )
        if isinstance(nargs, ast.Constant) and nargs.value in OPTIONAL_NARGS:
            continue
        required.append(name)
    return required


def check_no_args_help(sources: Sequence[Path]) -> Check:
    """A bare invocation prints usage rather than an argument error."""
    for path in sources:
        text = _read(path)
        if not _is_python(path, text) or 'argparse' not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        if EXPLICIT_HELP_RE.search(text):
            return Check(
                'no-args-help',
                Status.PASS,
                f'{path.name} prints help itself; a bare run has usage to '
                'fall back on.',
            )
        required = _required_positionals(tree)
        if required:
            listed = ', '.join(required[:MAX_LISTED])
            return Check(
                'no-args-help',
                Status.FAIL,
                f'{path.name} requires positional(s) {listed}, so a bare '
                'run answers with an argument error. Give them a default '
                '(`nargs="?"`), prompt for them behind a TTY guard, or '
                'print help.',
            )
        return Check(
            'no-args-help',
            Status.PASS,
            f'{path.name} has no required positionals; a bare run parses.',
        )
    return Check(
        'no-args-help',
        Status.MANUAL,
        'no argparse to read -- run the entrypoint bare and confirm the '
        'output is usage text, not a one-line "use --help" error.',
    )


def check_tty_guard(sources: Sequence[Path]) -> Check:
    """Every prompt checks for a TTY before it reads."""
    prompting = []
    for path in sources:
        text = _read(path)
        if any(
            pattern.search(text) for pattern in _prompt_patterns(path, text)
        ):
            prompting.append((path, text))

    if not prompting:
        return Check(
            'tty-guard',
            Status.PASS,
            'no prompts, so nothing can block on EOF in CI.',
        )
    unguarded = [
        path.name for path, text in prompting if not TTY_GUARD_RE.search(text)
    ]
    if unguarded:
        return Check(
            'tty-guard',
            Status.FAIL,
            f'{", ".join(unguarded[:MAX_LISTED])} prompts with no `isatty` '
            'or `[ -t 0 ]` check. Off a TTY that blocks or reads EOF; '
            'route every prompt through one guarded helper that names the '
            'flag the caller should have passed.',
        )
    return Check(
        'tty-guard',
        Status.PASS,
        'prompts are TTY-guarded. Confirm with `<cli> < /dev/null`.',
    )


def lint_cli(name: str, path: Path) -> CliReport:
    """Every rule against one entrypoint. Reads only; never executes."""
    sources = sources_for(path)
    return CliReport(
        name=name,
        path=path,
        checks=[
            check_version(sources),
            check_no_args_help(sources),
            check_tty_guard(sources),
        ],
    )


def lint(root: Path, *, include_helpers: bool = False) -> list[CliReport]:
    """Every discovered entrypoint, linted, in a stable order."""
    if not root.is_dir():
        message = f'{root} is not a directory'
        raise CliErgonomicsError(message)
    clis = find_clis(root, include_helpers=include_helpers)
    # A module reached through a wrapper is linted as part of it; listing
    # it again as its own entrypoint reports every finding twice.
    wrapped = {
        source
        for name in sorted(clis)
        for source in sources_for(clis[name])[1:]
    }
    return [
        lint_cli(name, clis[name])
        for name in sorted(clis)
        if clis[name] not in wrapped
    ]


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


def summary(reports: Sequence[CliReport]) -> str:
    """The one line a reader takes away."""
    failing = sum(1 for report in reports if report.failed)
    manual = sum(
        1
        for report in reports
        for check in report.checks
        if check.status is Status.MANUAL
    )
    return (
        f'{len(reports)} entrypoint(s), {failing} with violations, '
        f'{manual} rule(s) need a human run'
    )


def render(reports: Sequence[CliReport]) -> str:
    """Human-readable report, worst entrypoint first."""
    if not reports:
        return 'no CLI entrypoints found.\n'
    lines: list[str] = []
    for report in sorted(reports, key=lambda item: not item.failed):
        lines.append(f'{report.name}  ({report.path})')
        for check in report.checks:
            lines.append(f'  [{check.status.value.upper()}] {check.rule}')
            lines.append(f'      {check.detail}')
        lines.append('')
    lines.append(summary(reports))
    return '\n'.join(lines).rstrip() + '\n'


def as_json(reports: Sequence[CliReport]) -> str:
    """The same report, for a caller that wants to branch on it."""
    return json.dumps(
        {
            'clis': [
                {
                    'name': report.name,
                    'path': str(report.path),
                    'checks': [
                        {
                            'rule': check.rule,
                            'status': check.status.value,
                            'detail': check.detail,
                        }
                        for check in report.checks
                    ],
                }
                for report in reports
            ],
            'summary': summary(reports),
        },
        indent=2,
    )


def with_default_command(argv: list[str]) -> list[str]:
    """`lint` is implied, so `cli-ergonomics .` is a full invocation."""
    if argv and (argv[0] in TOP_LEVEL_FLAGS or argv[0] == DEFAULT_COMMAND):
        return argv
    return [DEFAULT_COMMAND, *argv]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. 0 clean, 1 a rule was violated, 2 nothing to lint."""
    parser = argparse.ArgumentParser(
        prog='cli-ergonomics',
        description="The cli-ergonomics skill's binary rules, statically.",
        epilog=(
            '`lint` is implied: `cli-ergonomics .` and '
            '`cli-ergonomics lint .` are the same run, and a bare '
            '`cli-ergonomics` lints the current directory. Entrypoints '
            'are read, never executed.'
        ),
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'cli-ergonomics {version()}',
    )
    subparsers = parser.add_subparsers(dest='command')

    lint_parser = subparsers.add_parser(
        'lint',
        help='check every entrypoint under a repo root',
    )
    lint_parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        type=Path,
        help='repo root; defaults to cwd',
    )
    lint_parser.add_argument(
        '--include-helpers',
        action='store_true',
        help='also lint *.sh helpers, which are skipped as internal '
        'plumbing by default',
    )
    lint_parser.add_argument(
        '--json',
        action='store_true',
        dest='as_json',
        help='machine-readable output',
    )

    raw = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(with_default_command(raw))

    try:
        reports = lint(args.directory, include_helpers=args.include_helpers)
    except CliErgonomicsError as error:
        print(f'cli-ergonomics: {error}', file=sys.stderr)
        return EXIT_UNUSABLE

    print(as_json(reports) if args.as_json else render(reports), end='')
    failed = any(report.failed for report in reports)
    return EXIT_FAILED_CHECK if failed else EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
