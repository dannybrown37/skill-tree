#!/usr/bin/env python3
"""Validate the structure of every skill in the current repo.

Skills are read in three layers -- frontmatter metadata, the SKILL.md
body, and bundled resource files. The first layer has a contract strict
enough to be an **error**: a skill that breaks it is loaded wrong, or not
at all. The rest is judgement, so everything this script decides about
shape and staleness is a **warning** -- a place for the audit-skills
playbook to look, not a verdict.

Run from the repo being audited, or point it at one -- it looks for
skills under both `.claude/skills/` (dotfiles-style) and `skills/`
(skill-tree-style) relative to that root, not to this script's location.
"""

import argparse
import json
import re
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

FRONTMATTER_DELIMITER = '---'
REQUIRED_FIELDS = ('name', 'description')
SKILL_ROOTS = (('.claude', 'skills'), ('skills',))

# Fields the two hosts actually read. Anything else is a typo or a
# leftover from a spec that moved -- both worth a look, neither fatal.
KNOWN_FIELDS = frozenset(
    {
        'name',
        'description',
        'user-invocable',
        'allowed-tools',
        'disable-model-invocation',
        'argument-hint',
        'model',
        'license',
        'version',
        'metadata',
    },
)

# The description is the whole of what a model sees when deciding whether
# to invoke; the ceiling is the host's, the floor is judgement.
MAX_DESCRIPTION_CHARS = 1024
MIN_DESCRIPTION_CHARS = 40

# A SKILL.md is a playbook, and a playbook that doesn't fit on a couple
# of screens has background in it that belongs in references/.
MAX_SKILL_LINES = 150
# References are allowed to be long -- but not unboundedly, since the
# model still has to load one to use it.
MAX_REFERENCE_LINES = 500

# A repo can record lengths it has already reviewed and accepted, one
# `<skill>: <lines>` per line, in `<skills-root>/.length-baseline`. It
# grandfathers, it does not exempt: growing past the pinned length warns
# again, and a skill that drops back under MAX_SKILL_LINES falls off the
# baseline on its own. The file lives with the skills it describes rather
# than in this checker, because which skills are allowed to be long is
# the audited repo's decision, not the validator's.
BASELINE_FILE = '.length-baseline'

BUNDLE_DIRS = frozenset(
    {'scripts', 'references', 'assets', 'templates', 'examples'},
)
ALLOWED_TOP_LEVEL_FILES = frozenset(
    {'SKILL.md', 'README.md', 'LICENSE', 'LICENSE.md'},
)
SKIP_DIRS = frozenset({'__pycache__', '.pytest_cache', '.ruff_cache'})

# Only a token that looks like a path *in this repo* is a staleness
# claim. Needs a slash and a short extension: a bare `foo.py` in prose is
# a generic filename, and treating it as a claim made every skill look
# stale (the same lesson repo-audit's PATHISH_RE encodes).
PATHISH_RE = re.compile(r'^[\w.][\w./@-]*/[\w.@-]+\.[A-Za-z0-9]{1,6}$')
BACKTICKED_RE = re.compile(r'`([^`\n]+)`')
# Anything that resolves somewhere else at read time isn't checkable
# here: an env var, a placeholder, a glob, a URL, an absolute or
# home-relative path outside the tree.
UNCHECKABLE_RE = re.compile(r'[$<>*\s]|://|^[~/]')

EXIT_OK = 0
EXIT_FAILED_CHECK = 1
EXIT_NOTHING_TO_CHECK = 2

TOP_LEVEL_FLAGS = ('-h', '--help', '--version')
DEFAULT_COMMAND = 'check'


class Severity(Enum):
    """How much a finding binds the reader."""

    ERROR = 'error'
    WARN = 'warn'


@dataclass(frozen=True)
class Finding:
    """One thing wrong with one skill."""

    skill: str
    severity: Severity
    category: str
    message: str


def parse_frontmatter(text: str) -> dict[str, str]:
    """Read the leading --- block as flat key/value pairs.

    Skill frontmatter is flat, so this avoids a YAML dependency. Returns
    an empty dict when there is no closing delimiter.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}

    try:
        end = lines.index(FRONTMATTER_DELIMITER, 1)
    except ValueError:
        return {}

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line[0] in ' \t':
            # A nested value under the previous key, not a field.
            continue
        key, separator, value = line.partition(':')
        if not separator:
            continue
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def split_frontmatter(text: str) -> str:
    """The SKILL.md body, with its frontmatter block removed."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return text
    try:
        end = lines.index(FRONTMATTER_DELIMITER, 1)
    except ValueError:
        return text
    return '\n'.join(lines[end + 1 :]).lstrip('\n')


def _error(skill_dir: Path, category: str, message: str) -> Finding:
    return Finding(skill_dir.name, Severity.ERROR, category, message)


def _warn(skill_dir: Path, category: str, message: str) -> Finding:
    return Finding(skill_dir.name, Severity.WARN, category, message)


def validate_frontmatter(skill_dir: Path, text: str) -> list[Finding]:
    """The part of the contract a host enforces on load."""
    fields = parse_frontmatter(text)
    if not fields:
        return [
            _error(
                skill_dir,
                'frontmatter',
                f'{skill_dir.name}: SKILL.md has no parseable frontmatter',
            ),
        ]

    findings = []
    for field in REQUIRED_FIELDS:
        if not fields.get(field, '').strip():
            findings.append(
                _error(
                    skill_dir,
                    'frontmatter',
                    f'{skill_dir.name}: SKILL.md frontmatter is missing a '
                    f'non-empty "{field}"',
                ),
            )

    declared = fields.get('name', '').strip()
    if declared and declared != skill_dir.name:
        findings.append(
            _error(
                skill_dir,
                'frontmatter',
                f'{skill_dir.name}: frontmatter name "{declared}" does not '
                f'match its directory name',
            ),
        )

    description = fields.get('description', '').strip()
    if len(description) > MAX_DESCRIPTION_CHARS:
        findings.append(
            _error(
                skill_dir,
                'frontmatter',
                f'{skill_dir.name}: description is too long '
                f'({len(description)} chars, max {MAX_DESCRIPTION_CHARS})',
            ),
        )
    return findings


def validate_bundled_scripts(skill_dir: Path) -> list[Finding]:
    """Anything under scripts/ has to be runnable as it sits."""
    scripts_dir = skill_dir / 'scripts'
    if not scripts_dir.is_dir():
        return []

    findings = []
    for script in sorted(scripts_dir.iterdir()):
        if not script.is_file():
            continue
        if script.name.startswith('test_') or script.name == 'conftest.py':
            continue

        relative = f'{skill_dir.name}/scripts/{script.name}'
        if not script.stat().st_mode & stat.S_IXUSR:
            findings.append(
                _error(
                    skill_dir,
                    'scripts',
                    f'{relative} is not executable (chmod +x it)',
                ),
            )

        first_line = script.read_text(errors='replace').split('\n', 1)[0]
        if not first_line.startswith('#!'):
            findings.append(
                _error(skill_dir, 'scripts', f'{relative} has no shebang'),
            )
    return findings


def check_frontmatter_drift(skill_dir: Path, text: str) -> list[Finding]:
    """Fields that shouldn't be there, and a trigger too thin to fire."""
    fields = parse_frontmatter(text)
    if not fields:
        return []

    findings = [
        _warn(
            skill_dir,
            'frontmatter-drift',
            f'{skill_dir.name}: unknown frontmatter field "{field}" -- '
            f'typo, or a field the spec dropped',
        )
        for field in fields
        if field not in KNOWN_FIELDS
    ]

    description = fields.get('description', '').strip()
    if 0 < len(description) < MIN_DESCRIPTION_CHARS:
        findings.append(
            _warn(
                skill_dir,
                'frontmatter-drift',
                f'{skill_dir.name}: description is {len(description)} chars '
                f'-- too thin to route on; say when to invoke it',
            ),
        )
    return findings


def read_length_baseline(skills_root: Path) -> dict[str, int]:
    """Accepted SKILL.md lengths, by skill name. Missing file means none.

    Parsed by hand for the same reason frontmatter is: this stays a
    stdlib-only checker, and the format is two fields on a line.
    """
    path = skills_root / BASELINE_FILE
    try:
        text = path.read_text(errors='replace')
    except OSError:
        return {}

    baseline: dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        name, separator, count = stripped.partition(':')
        if not separator:
            continue
        try:
            baseline[name.strip()] = int(count.strip())
        except ValueError:
            continue
    return baseline


def check_length(skill_dir: Path, text: str) -> list[Finding]:
    """Playbooks that have grown background into them."""
    findings = []
    lines = len(text.splitlines())
    accepted = read_length_baseline(skill_dir.parent).get(skill_dir.name)
    # max(), not `accepted or MAX`: the baseline grandfathers a skill that
    # is already long, and must never make the check stricter than the
    # global rule.
    allowed = max(MAX_SKILL_LINES, accepted or 0)

    if lines > allowed:
        over = (
            f'its accepted baseline of {accepted}'
            if accepted and accepted > MAX_SKILL_LINES
            else str(MAX_SKILL_LINES)
        )
        findings.append(
            _warn(
                skill_dir,
                'length',
                f'{skill_dir.name}: SKILL.md is {lines} lines (over '
                f'{over}) -- move background into references/',
            ),
        )

    references = skill_dir / 'references'
    if not references.is_dir():
        return findings

    for path in sorted(references.rglob('*')):
        if not path.is_file() or path.suffix != '.md':
            continue
        count = len(path.read_text(errors='replace').splitlines())
        if count > MAX_REFERENCE_LINES:
            findings.append(
                _warn(
                    skill_dir,
                    'length',
                    f'{skill_dir.name}: references/{path.name} is {count} '
                    f'lines (over {MAX_REFERENCE_LINES}) -- split it',
                ),
            )
    return findings


def check_placement(skill_dir: Path) -> list[Finding]:
    """Loose files at a skill's root, which belong in a bundle dir."""
    findings = []
    for path in sorted(skill_dir.iterdir()):
        if path.name.startswith('.') or path.name in SKIP_DIRS:
            continue

        if path.is_dir():
            if path.name not in BUNDLE_DIRS:
                findings.append(
                    _warn(
                        skill_dir,
                        'placement',
                        f'{skill_dir.name}: unexpected directory '
                        f'"{path.name}/" -- bundles are '
                        f'{", ".join(sorted(BUNDLE_DIRS))}',
                    ),
                )
            continue

        if path.name in ALLOWED_TOP_LEVEL_FILES:
            continue

        target = 'references/' if path.suffix == '.md' else 'scripts/'
        findings.append(
            _warn(
                skill_dir,
                'placement',
                f'{skill_dir.name}: "{path.name}" sits beside SKILL.md -- '
                f'move it into {target}',
            ),
        )
    return findings


def referenced_paths(body: str) -> list[str]:
    """Backticked tokens that claim a file exists in this repo."""
    found = []
    for raw in BACKTICKED_RE.findall(body):
        token = raw.strip().rstrip('.,:;)').lstrip('(')
        if UNCHECKABLE_RE.search(token) or not PATHISH_RE.match(token):
            continue
        found.append(token)
    return found


def check_staleness(
    skill_dir: Path,
    text: str,
    root: Path | None,
) -> list[Finding]:
    """Paths a skill names that aren't there any more.

    Resolved against the skill's own directory first and the repo root
    second, because skills write both -- `references/x.md` and
    `skills/foo/scripts/y.py` are the same claim from different anchors.
    """
    roots = [skill_dir, *([root] if root is not None else [])]
    return [
        _warn(
            skill_dir,
            'staleness',
            f'{skill_dir.name}: SKILL.md names `{token}`, which does not '
            f'exist',
        )
        for token in dict.fromkeys(referenced_paths(split_frontmatter(text)))
        if not any((base / token).exists() for base in roots)
    ]


def audit_skill(skill_dir: Path, root: Path | None = None) -> list[Finding]:
    """Every finding for one skill, errors and drift alike."""
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.is_file():
        return [_error(skill_dir, 'layout', f'{skill_dir.name}: no SKILL.md')]

    text = skill_md.read_text(errors='replace')
    return [
        *validate_frontmatter(skill_dir, text),
        *validate_bundled_scripts(skill_dir),
        *check_frontmatter_drift(skill_dir, text),
        *check_length(skill_dir, text),
        *check_placement(skill_dir),
        *check_staleness(skill_dir, text, root),
    ]


def validate_skill(skill_dir: Path, root: Path | None = None) -> list[str]:
    """Only the hard contract, as plain messages.

    The narrow half of `audit_skill`, kept separate because pre-commit
    and the README generator want a yes/no about loadability and would
    have to filter drift warnings out of it otherwise.
    """
    return [
        finding.message
        for finding in audit_skill(skill_dir, root)
        if finding.severity is Severity.ERROR
    ]


def find_skill_dirs(root: Path) -> list[Path]:
    """Find skill directories under any layout this repo might use.

    Checks `.claude/skills/` (dotfiles-style) and `skills/`
    (skill-tree-style) relative to `root`. A repo is expected to use one
    or the other, not both, but nothing stops checking both.
    """
    found: list[Path] = []
    for parts in SKILL_ROOTS:
        skills_root = root.joinpath(*parts)
        if skills_root.is_dir():
            found.extend(d for d in skills_root.iterdir() if d.is_dir())
    return sorted(found, key=lambda d: d.name)


def run_audit(root: Path) -> list[Finding]:
    """Every finding across every skill under `root`."""
    return [
        finding
        for skill_dir in find_skill_dirs(root)
        for finding in audit_skill(skill_dir, root)
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


def summary(findings: list[Finding]) -> str:
    """The one line a reader takes away."""
    errors = sum(1 for f in findings if f.severity is Severity.ERROR)
    warns = len(findings) - errors
    if not findings:
        return 'no findings'
    return f'{errors} error(s), {warns} warning(s)'


def render(findings: list[Finding]) -> str:
    """Human-readable report, errors first."""
    lines: list[str] = []
    for severity in (Severity.ERROR, Severity.WARN):
        matching = [f for f in findings if f.severity is severity]
        if not matching:
            continue
        lines.append(severity.value.upper())
        lines.extend(f'  [{f.category}] {f.message}' for f in matching)
        lines.append('')
    lines.append(summary(findings))
    return '\n'.join(lines).rstrip() + '\n'


def as_json(findings: list[Finding]) -> str:
    """The same report, for a caller that wants to branch on it."""
    return json.dumps(
        {
            'findings': [
                {
                    'skill': finding.skill,
                    'severity': finding.severity.value,
                    'category': finding.category,
                    'message': finding.message,
                }
                for finding in findings
            ],
            'summary': summary(findings),
        },
        indent=2,
    )


def with_default_command(argv: list[str]) -> list[str]:
    """Let the only subcommand be implied.

    `audit-skills .` and `audit-skills check .` are the same run. Flags
    the top-level parser owns still have to reach it, so they pass
    through untouched.
    """
    if argv and (argv[0] in TOP_LEVEL_FLAGS or argv[0] == DEFAULT_COMMAND):
        return argv
    return [DEFAULT_COMMAND, *argv]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. 0 clean, 1 a check failed, 2 no skills found."""
    parser = argparse.ArgumentParser(
        prog='audit-skills',
        description="The audit-skills playbook's deterministic half.",
        epilog=(
            '`check` is implied: `audit-skills .` and `audit-skills check .` '
            'are the same run, and a bare `audit-skills` checks the current '
            'directory.'
        ),
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'audit-skills {version()}',
    )
    subparsers = parser.add_subparsers(dest='command')

    check = subparsers.add_parser(
        DEFAULT_COMMAND,
        help='check every skill under a repo root',
    )
    check.add_argument(
        'directory',
        nargs='?',
        default='.',
        type=Path,
        help='repo root; defaults to cwd',
    )
    check.add_argument(
        '--json',
        action='store_true',
        dest='as_json',
        help='machine-readable output',
    )
    check.add_argument(
        '--strict',
        action='store_true',
        help='exit 1 on drift warnings too, not just errors',
    )

    raw = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(with_default_command(raw))

    root = args.directory
    if not find_skill_dirs(root):
        print(
            f'audit-skills: no skills under {root} '
            f'(looked in .claude/skills/ and skills/)',
            file=sys.stderr,
        )
        return EXIT_NOTHING_TO_CHECK

    findings = run_audit(root)
    print(as_json(findings) if args.as_json else render(findings), end='')

    failing = [
        finding
        for finding in findings
        if args.strict or finding.severity is Severity.ERROR
    ]
    return EXIT_FAILED_CHECK if failing else EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
