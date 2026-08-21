#!/usr/bin/env python3
"""Repo-level wrapper around the audit-skills validator.

The checker itself lives with the skill that documents it
(`skills/audit-skills/scripts/check_skill_structure.py`); two copies of
it drifted apart once already. This is the pre-commit entry point, so it
reports only the hard contract -- drift warnings are the audit-skills
playbook's job, not a reason to block a commit. Run
`skill-tree audit-skills .` for those.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = (
    REPO_ROOT
    / 'skills'
    / 'audit-skills'
    / 'scripts'
    / 'check_skill_structure.py'
)


def _load_checker() -> ModuleType:
    """Import the skill's module by path.

    Not a plain import: this file has the same name, so `import
    check_skill_structure` from here resolves to itself.
    """
    spec = importlib.util.spec_from_file_location(
        'audit_skills_checker',
        CHECKER,
    )
    if spec is None or spec.loader is None:  # pragma: no cover - unreachable
        message = f'cannot load the skill checker from {CHECKER}'
        raise ImportError(message)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_checker = _load_checker()

find_skill_dirs = _checker.find_skill_dirs
parse_frontmatter = _checker.parse_frontmatter
validate_skill = _checker.validate_skill

__all__ = ['find_skill_dirs', 'parse_frontmatter', 'validate_skill']


def main() -> int:
    errors = [
        error
        for skill_dir in find_skill_dirs(REPO_ROOT)
        for error in validate_skill(skill_dir, REPO_ROOT)
    ]

    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
