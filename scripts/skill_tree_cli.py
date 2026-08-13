#!/usr/bin/env python3
"""One entry point for everything in this repo, from a normal shell.

Two jobs. First, the skills in here document themselves *inside* Claude
and nowhere else -- `list`/`show` put the same playbooks in a terminal, so
"what can this thing do" doesn't require starting a session. Second, the
repo's commands are scattered across scripts/ and skills/*/scripts/;
this gathers them behind one name rather than a set of paths to remember.

Sub-commands that already exist as their own script are delegated to, not
reimplemented -- this stays a dispatcher.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

FRONTMATTER_DELIMITER = '---'

# Commands that are just "run the script that already does this".
DELEGATED = {
    'install': (
        'scripts/install.sh',
        'Link skills and CLIs into ~ (--claude/--copilot; idempotent)',
    ),
    'dev': (
        'scripts/dev_link.sh',
        'Point the installed plugin at this checkout',
    ),
    'check': (
        'scripts/check_skill_structure.py',
        "Validate every skill's frontmatter and bundled scripts",
    ),
}


@dataclass(frozen=True)
class Skill:
    """A skill directory, as the CLI needs to talk about it."""

    name: str
    description: str
    path: Path
    cli: Path | None


def parse_frontmatter(text: str) -> dict[str, str]:
    """Read the leading --- block as flat key/value pairs.

    Skill frontmatter is flat, so this avoids a YAML dependency (the same
    reason check_skill_structure.py parses it by hand).
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
        key, separator, value = line.partition(':')
        if not separator or not line.strip() or line.lstrip().startswith('#'):
            continue
        parsed = value.strip()
        if parsed.startswith('"') and parsed.endswith('"'):
            # Descriptions are quoted precisely because they contain
            # quotes -- leaving the backslashes in shows them to a reader.
            parsed = parsed[1:-1].replace('\\"', '"')
        else:
            parsed = parsed.strip("'")
        fields[key.strip()] = parsed
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


def find_skills(root: Path) -> list[Skill]:
    """Every skill under `root/skills`, alphabetically."""
    skills_root = root / 'skills'
    if not skills_root.is_dir():
        return []

    skills = []
    for skill_dir in sorted(skills_root.iterdir()):
        skill_md = skill_dir / 'SKILL.md'
        if not skill_md.is_file():
            continue

        fields = parse_frontmatter(skill_md.read_text(errors='replace'))
        # A skill's own CLI is conventionally named after the skill.
        cli = skill_dir / 'scripts' / skill_dir.name
        skills.append(
            Skill(
                name=fields.get('name', skill_dir.name),
                description=fields.get('description', ''),
                path=skill_dir,
                cli=cli if os.access(cli, os.X_OK) else None,
            ),
        )
    return skills


def _first_sentence(description: str, width: int) -> str:
    """Descriptions are written for Claude, so they run long."""
    text = description.strip()
    if len(text) <= width:
        return text
    return f'{text[: width - 1].rstrip()}…'


def cmd_list(root: Path, args: list[str]) -> int:
    skills = find_skills(root)

    if '--json' in args:
        print(
            json.dumps(
                [
                    {
                        'name': skill.name,
                        'description': skill.description,
                        'path': str(skill.path),
                        'cli': str(skill.cli) if skill.cli else None,
                    }
                    for skill in skills
                ],
                indent=2,
            ),
        )
        return 0

    _print_skills(skills)
    return 0


def _print_skills(skills: list[Skill]) -> None:
    width = max((len(skill.name) for skill in skills), default=0)
    for skill in skills:
        invoke = '  [has a CLI]' if skill.cli else ''
        summary = _first_sentence(skill.description, 96 - width)
        print(f'  {skill.name.ljust(width)}  {summary}{invoke}')


def cmd_show(root: Path, args: list[str]) -> int:
    raw = '--raw' in args
    names = [arg for arg in args if not arg.startswith('-')]
    skills = {skill.name: skill for skill in find_skills(root)}

    if not names:
        print(
            f'skill-tree show: which skill? ({", ".join(skills)})',
            file=sys.stderr,
        )
        return 1

    skill = skills.get(names[0])
    if skill is None:
        print(
            f'skill-tree: no skill named "{names[0]}" '
            f'(have: {", ".join(skills)})',
            file=sys.stderr,
        )
        return 1

    text = (skill.path / 'SKILL.md').read_text()
    print(text if raw else split_frontmatter(text), end='')
    return 0


def _dev_mode(root: Path) -> str:
    """Dev-link state, best effort -- it needs a real plugin install."""
    script = root / 'scripts' / 'dev_link.sh'
    if not script.is_file():
        return 'unknown (no dev_link.sh)'

    result = subprocess.run(  # noqa: S603
        [str(script), '--status'],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or result.stderr.strip() or 'unknown'


def _dev_mode_flag(root: Path) -> str:
    """`[dev mode ON]`-style tag for the overview, '' when unknowable.

    Dev mode silently changes which copy of the repo Claude loads, so
    leaving it to `doctor` means noticing far too late.
    """
    if not (root / 'scripts' / 'dev_link.sh').is_file():
        return ''

    status = _dev_mode(root)
    for state in ('ON', 'OFF'):
        if status.startswith(f'Dev mode {state}'):
            return f'  [dev mode {state}]'
    return '  [dev mode ?]'


def _copilot_state(root: Path, skills: list[Skill]) -> str:
    """How much of the Copilot-side install is actually in place.

    Copilot has no plugin manifest to inspect, so "is this wired up" is
    only answerable by looking at the symlinks install.sh would make.
    """
    home = Path.home()
    skills_dir = home / '.copilot' / 'skills'
    if not (home / '.copilot').is_dir():
        return 'not installed (no ~/.copilot)'

    linked = sum(
        1
        for skill in skills
        if (skills_dir / skill.name).is_symlink()
        and (skills_dir / skill.name).resolve()
        == (root / 'skills' / skill.name).resolve()
    )
    hooks = home / '.copilot' / 'hooks' / 'skill-tree.json'
    hook_state = 'hooks on' if hooks.is_file() else 'hooks missing'
    return f'{linked}/{len(skills)} skills linked, {hook_state}'


def cmd_doctor(root: Path, _args: list[str]) -> int:
    skills = find_skills(root)
    print(f'Checkout   {root}')
    print(f'Dev link   {_dev_mode(root)}')
    print(f'Skills     {len(skills)}')
    print(f'Copilot    {_copilot_state(root, skills)}')
    print()

    for skill in skills:
        on_path = (
            ' (also on PATH)' if skill.cli and shutil.which(skill.name) else ''
        )
        marker = 'CLI ' if skill.cli else '    '
        print(f'  {marker}{skill.name}{on_path}')
    return 0


def cmd_test(root: Path, args: list[str]) -> int:
    # `uv` off PATH deliberately: which one is right depends on how the
    # user installed it, same as every other entry point here.
    return subprocess.run(  # noqa: S603
        [  # noqa: S607
            'uv',
            'run',
            '--with',
            'pytest',
            'pytest',
            'scripts/',
            'skills/',
            '-q',
            *args,
        ],
        cwd=root,
        check=False,
    ).returncode


def cmd_help(root: Path, _args: list[str]) -> int:
    """Everything this repo can do, on one screen.

    This is what a bare `skill-tree` prints. Keeping track of the whole
    surface is the entire point of the CLI existing, so the default
    invocation shows the commands *and* the skills -- a bare run that
    listed only skills would hide half of what's here.
    """
    skills = find_skills(root)

    print('Usage: skill-tree <command> [args]\n')
    print('Commands:')
    print('  list [--json]     Every skill in this repo, one line each')
    print("  show <skill>      A skill's playbook (--raw keeps frontmatter)")
    print('  doctor            Where this checkout is and what it wired up')
    for name, (_, blurb) in DELEGATED.items():
        tag = _dev_mode_flag(root) if name == 'dev' else ''
        print(f'  {name.ljust(16)}  {blurb}{tag}')
    print('  test [args]       Run the test suite')
    print('  help              This screen (also the bare `skill-tree`)')

    with_cli = [skill.name for skill in skills if skill.cli]
    if with_cli:
        print('\nSkill CLIs, reachable by name — args pass straight through:')
        for name in with_cli:
            print(f'  skill-tree {name} [args]')

    if skills:
        print('\nSkills:')
        _print_skills(skills)
        print("\nFull playbook: skill-tree show <name>   In Claude: '/<name>'")
    return 0


def _delegate(root: Path, script: str, args: list[str]) -> int:
    return subprocess.run(  # noqa: S603
        [str(root / script), *args],
        check=False,
    ).returncode


def resolve_root(root: Path | None) -> Path:
    if root is not None:
        return root
    override = os.environ.get('SKILL_TREE_ROOT')
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = resolve_root(root)

    # Only a *leading* -h means us. Everything after the command belongs to
    # the command -- `skill-tree screenshot --help` is the screenshot CLI's
    # help, not ours, and swallowing it would make delegation a lie.
    if args and args[0] in {'-h', '--help'}:
        return cmd_help(root, args[1:])

    # Bare `skill-tree` is "what's in here?" -- which means the commands
    # too, not just the skills, so it maps to help rather than list. A
    # leading flag is still a flag for `list` (`skill-tree --json`).
    command, rest = (args[0], args[1:]) if args else ('help', [])
    if command.startswith('-'):
        command, rest = 'list', args

    builtins = {
        'list': cmd_list,
        'show': cmd_show,
        'doctor': cmd_doctor,
        'test': cmd_test,
        'help': cmd_help,
    }
    if command in builtins:
        return builtins[command](root, rest)

    if command in DELEGATED:
        return _delegate(root, DELEGATED[command][0], rest)

    # Anything else is either a skill's own CLI or a typo.
    skills = {skill.name: skill for skill in find_skills(root)}
    skill = skills.get(command)
    if skill is None:
        print(
            f'skill-tree: unknown command "{command}" (try: skill-tree help)',
            file=sys.stderr,
        )
        return 1
    if skill.cli is None:
        print(
            f'skill-tree: the {command} skill has no CLI -- it is a playbook '
            f'Claude follows. Read it with: skill-tree show {command}',
            file=sys.stderr,
        )
        return 1

    return subprocess.run([str(skill.cli), *rest], check=False).returncode  # noqa: S603


if __name__ == '__main__':
    sys.exit(main())
