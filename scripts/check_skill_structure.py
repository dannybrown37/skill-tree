#!/usr/bin/env python3
"""Validate the structure of every skill under .claude/skills/.

Complements check-claude-symlinks.sh: that one checks the .github mirror
exists, this one checks the skill content the mirror points at is sound.

Skills are read by Claude Code in three layers -- frontmatter metadata,
the SKILL.md body, and bundled resource files. Only the first layer has a
contract strict enough to enforce mechanically, so that is what this
checks, plus the executable bit on anything under a skill's scripts/.
"""

import stat
import sys
from pathlib import Path

FRONTMATTER_DELIMITER = '---'
REQUIRED_FIELDS = ('name', 'description')


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
        key, separator, value = line.partition(':')
        if not separator:
            continue
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def validate_frontmatter(skill_dir: Path, text: str) -> list[str]:
    fields = parse_frontmatter(text)
    if not fields:
        return [f'{skill_dir.name}: SKILL.md has no parseable frontmatter']

    errors = []
    for field in REQUIRED_FIELDS:
        if not fields.get(field, '').strip():
            errors.append(
                f'{skill_dir.name}: SKILL.md frontmatter is missing a '
                f'non-empty "{field}"',
            )

    declared = fields.get('name', '').strip()
    if declared and declared != skill_dir.name:
        errors.append(
            f'{skill_dir.name}: frontmatter name "{declared}" does not '
            f'match its directory name',
        )
    return errors


def validate_bundled_scripts(skill_dir: Path) -> list[str]:
    scripts_dir = skill_dir / 'scripts'
    if not scripts_dir.is_dir():
        return []

    errors = []
    for script in sorted(scripts_dir.iterdir()):
        if not script.is_file():
            continue

        relative = f'{skill_dir.name}/scripts/{script.name}'
        if not script.stat().st_mode & stat.S_IXUSR:
            errors.append(f'{relative} is not executable (chmod +x it)')

        first_line = script.read_text(errors='replace').split('\n', 1)[0]
        if not first_line.startswith('#!'):
            errors.append(f'{relative} has no shebang')
    return errors


def validate_skill(skill_dir: Path) -> list[str]:
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.is_file():
        return [f'{skill_dir.name}: no SKILL.md']

    text = skill_md.read_text()
    return [
        *validate_frontmatter(skill_dir, text),
        *validate_bundled_scripts(skill_dir),
    ]


def find_skill_dirs(root: Path) -> list[Path]:
    skills_root = root / '.claude' / 'skills'
    if not skills_root.is_dir():
        return []
    return sorted(d for d in skills_root.iterdir() if d.is_dir())


def main() -> int:
    root = Path(__file__).parent.parent
    errors = [
        error
        for skill_dir in find_skill_dirs(root)
        for error in validate_skill(skill_dir)
    ]

    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
