"""Tests for the skill structure validator."""

from pathlib import Path

import pytest

from check_skill_structure import (
    find_skill_dirs,
    parse_frontmatter,
    validate_skill,
)

VALID_SKILL = """\
---
name: widget
description: "Invoke when doing widget things."
user-invocable: true
allowed-tools: Read, Bash
---

# Widget

Do the thing.
"""


def write_skill(
    root: Path,
    name: str,
    body: str,
    *,
    dotclaude: bool = True,
) -> Path:
    skills_parts = ('.claude', 'skills') if dotclaude else ('skills',)
    skill_dir = root.joinpath(*skills_parts, name)
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(body)
    return skill_dir


def test_valid_skill_has_no_errors(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)

    assert validate_skill(skill_dir) == []


def test_missing_skill_md_is_an_error(tmp_path: Path) -> None:
    skill_dir = tmp_path / '.claude' / 'skills' / 'widget'
    skill_dir.mkdir(parents=True)

    errors = validate_skill(skill_dir)

    assert len(errors) == 1
    assert 'SKILL.md' in errors[0]


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        ('# Widget\n\nNo frontmatter at all.\n', 'frontmatter'),
        ('---\nname: widget\n', 'frontmatter'),
        (
            '---\nname: gadget\ndescription: "x"\n---\n',
            'name',
        ),
        (
            '---\ndescription: "x"\n---\n',
            'name',
        ),
        (
            '---\nname: widget\n---\n',
            'description',
        ),
        (
            '---\nname: widget\ndescription: ""\n---\n',
            'description',
        ),
        (
            '---\nname: widget\ndescription: "   "\n---\n',
            'description',
        ),
    ],
)
def test_frontmatter_problems_are_reported(
    tmp_path: Path,
    body: str,
    expected: str,
) -> None:
    skill_dir = write_skill(tmp_path, 'widget', body)

    errors = validate_skill(skill_dir)

    assert errors, 'expected at least one error'
    assert any(expected in error for error in errors), errors


def test_bundled_script_must_be_executable(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    scripts = skill_dir / 'scripts'
    scripts.mkdir()
    helper = scripts / 'helper.sh'
    helper.write_text('#!/usr/bin/env bash\necho hi\n')
    helper.chmod(0o644)

    errors = validate_skill(skill_dir)

    assert any('executable' in error for error in errors), errors


def test_bundled_script_must_have_a_shebang(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    scripts = skill_dir / 'scripts'
    scripts.mkdir()
    helper = scripts / 'helper.sh'
    helper.write_text('echo hi\n')
    helper.chmod(0o755)

    errors = validate_skill(skill_dir)

    assert any('shebang' in error for error in errors), errors


def test_pytest_files_are_exempt_from_the_script_checks(
    tmp_path: Path,
) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    scripts = skill_dir / 'scripts'
    scripts.mkdir()
    (scripts / 'test_widget.py').write_text('def test_ok() -> None: pass\n')
    (scripts / 'conftest.py').write_text('')

    assert validate_skill(skill_dir) == []


def test_well_formed_bundled_script_passes(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    scripts = skill_dir / 'scripts'
    scripts.mkdir()
    helper = scripts / 'helper.sh'
    helper.write_text('#!/usr/bin/env bash\necho hi\n')
    helper.chmod(0o755)

    assert validate_skill(skill_dir) == []


def test_find_skill_dirs_lists_dotclaude_layout(tmp_path: Path) -> None:
    write_skill(tmp_path, 'widget', VALID_SKILL)
    write_skill(tmp_path, 'gadget', VALID_SKILL)

    found = find_skill_dirs(tmp_path)

    assert [d.name for d in found] == ['gadget', 'widget']


def test_find_skill_dirs_lists_top_level_skills_layout(
    tmp_path: Path,
) -> None:
    write_skill(tmp_path, 'widget', VALID_SKILL, dotclaude=False)
    write_skill(tmp_path, 'gadget', VALID_SKILL, dotclaude=False)

    found = find_skill_dirs(tmp_path)

    assert [d.name for d in found] == ['gadget', 'widget']


def test_find_skill_dirs_checks_both_layouts_at_once(
    tmp_path: Path,
) -> None:
    write_skill(tmp_path, 'widget', VALID_SKILL, dotclaude=True)
    write_skill(tmp_path, 'gadget', VALID_SKILL, dotclaude=False)

    found = find_skill_dirs(tmp_path)

    assert [d.name for d in found] == ['gadget', 'widget']


def test_parse_frontmatter_reads_quoted_and_bare_values() -> None:
    data = parse_frontmatter(VALID_SKILL)

    assert data['name'] == 'widget'
    assert data['description'] == 'Invoke when doing widget things.'
    assert data['user-invocable'] == 'true'


def test_real_repo_skills_all_validate() -> None:
    """The checked-in skill-tree skills must satisfy their own validator."""
    repo_root = Path(__file__).parent.parent.parent.parent

    errors = [
        error
        for skill_dir in find_skill_dirs(repo_root)
        for error in validate_skill(skill_dir)
    ]

    assert errors == []
