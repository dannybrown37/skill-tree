#!/usr/bin/env python3
"""Regenerate the Skill table in README.md from each skill's frontmatter.

Keeps the README table as a projection of skills/*/SKILL.md rather than a
hand-maintained copy that drifts. Run by the `regen-file` pre-commit hook
from git-a-grip, which re-stages README.md when this rewrites it.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_skill_structure import find_skill_dirs, parse_frontmatter

START_MARKER = '<!-- skills:start -->'
END_MARKER = '<!-- skills:end -->'


def build_table(root: Path) -> str:
    rows = ['| Skill | What it does |', '| --- | --- |']
    for skill_dir in find_skill_dirs(root):
        skill_md = skill_dir / 'SKILL.md'
        if not skill_md.is_file():
            continue
        fields = parse_frontmatter(skill_md.read_text())
        description = fields.get('description', '').strip()
        if not description or description.upper().startswith('TODO'):
            msg = (
                f'ERROR: {skill_dir.name}: SKILL.md description is missing '
                f'or a TODO placeholder — fill it in before regenerating '
                f'the README table'
            )
            raise SystemExit(msg)
        rows.append(f'| `{skill_dir.name}` | {description} |')
    return '\n'.join(rows)


def version(root: Path) -> str:
    """This checkout's plugin version, or `unknown` outside one.

    `--version` has to work with no config, so a missing or unreadable
    manifest is an answer rather than a crash.
    """
    try:
        manifest = (root / '.claude-plugin' / 'plugin.json').read_text()
        return str(json.loads(manifest)['version'])
    except (OSError, ValueError, KeyError):
        return 'unknown'


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(__file__).parent.parent if root is None else root

    if args and args[0] in {'-V', '--version'}:
        print(f'gen-readme-skills-table {version(root)}')
        return 0

    readme = root / 'README.md'
    text = readme.read_text()

    try:
        start = text.index(START_MARKER) + len(START_MARKER)
        end = text.index(END_MARKER)
    except ValueError:
        print(
            f'ERROR: README.md is missing {START_MARKER} / {END_MARKER} '
            f'markers around the Skill table',
            file=sys.stderr,
        )
        return 1

    table = build_table(root)
    new_text = f'{text[:start]}\n{table}\n{text[end:]}'
    if new_text != text:
        readme.write_text(new_text)

    return 0


if __name__ == '__main__':
    sys.exit(main())
