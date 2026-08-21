"""Tests for the skill structure validator and its drift checks."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# By path, not by name: scripts/check_skill_structure.py is a shim with
# the same module name, and whichever test module imports first wins the
# `check_skill_structure` entry in sys.modules.
_spec = importlib.util.spec_from_file_location(
    'audit_skills_checker_under_test',
    Path(__file__).parent / 'check_skill_structure.py',
)
assert _spec is not None
assert _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

from audit_skills_checker_under_test import (  # noqa: E402
    EXIT_FAILED_CHECK,
    EXIT_NOTHING_TO_CHECK,
    EXIT_OK,
    MAX_SKILL_LINES,
    Severity,
    audit_skill,
    find_skill_dirs,
    main,
    parse_frontmatter,
    run_audit,
    validate_skill,
    version,
)

DESCRIPTION = 'Invoke when doing widget things, or reviewing one.'
VALID_SKILL = f"""\
---
name: widget
description: "{DESCRIPTION}"
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


def messages(findings: list, severity: Severity | None = None) -> list[str]:
    return [
        finding.message
        for finding in findings
        if severity is None or finding.severity is severity
    ]


def warnings(skill_dir: Path, root: Path | None = None) -> list[str]:
    return messages(audit_skill(skill_dir, root), Severity.WARN)


# --- the hard contract (errors) ---------------------------------------


def test_valid_skill_has_no_findings(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)

    assert audit_skill(skill_dir, tmp_path) == []


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
        ('---\nname: gadget\ndescription: "x"\n---\n', 'name'),
        ('---\ndescription: "x"\n---\n', 'name'),
        ('---\nname: widget\n---\n', 'description'),
        ('---\nname: widget\ndescription: ""\n---\n', 'description'),
        ('---\nname: widget\ndescription: "   "\n---\n', 'description'),
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


def test_an_overlong_description_is_an_error(tmp_path: Path) -> None:
    body = VALID_SKILL.replace(DESCRIPTION, 'x' * 1100)
    skill_dir = write_skill(tmp_path, 'widget', body)

    errors = validate_skill(skill_dir)

    assert any('too long' in error for error in errors), errors


# --- drift checks (warnings) ------------------------------------------


def test_a_long_skill_md_warns_about_bloat(tmp_path: Path) -> None:
    body = VALID_SKILL + '\nfiller line\n' * (MAX_SKILL_LINES + 1)
    skill_dir = write_skill(tmp_path, 'widget', body)

    found = warnings(skill_dir, tmp_path)

    assert any('lines' in message for message in found), found
    assert validate_skill(skill_dir) == []


def test_a_short_skill_md_does_not_warn(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)

    assert warnings(skill_dir, tmp_path) == []


def test_a_loose_markdown_file_belongs_in_references(
    tmp_path: Path,
) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    (skill_dir / 'background.md').write_text('# Theory\n')

    found = warnings(skill_dir, tmp_path)

    assert any('references/' in message for message in found), found
    assert any('background.md' in message for message in found), found


def test_a_reference_in_references_is_fine(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    (skill_dir / 'references').mkdir()
    (skill_dir / 'references' / 'background.md').write_text('# Theory\n')

    assert warnings(skill_dir, tmp_path) == []


def test_a_loose_non_markdown_file_is_flagged_for_relocation(
    tmp_path: Path,
) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    (skill_dir / 'helper.py').write_text('print("hi")\n')

    found = warnings(skill_dir, tmp_path)

    assert any('scripts/' in message for message in found), found


@pytest.mark.parametrize(
    'name',
    ['README.md', 'LICENSE', '.gitignore'],
)
def test_conventional_top_level_files_are_not_flagged(
    tmp_path: Path,
    name: str,
) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    (skill_dir / name).write_text('x\n')

    assert warnings(skill_dir, tmp_path) == []


def test_an_unknown_frontmatter_field_warns(tmp_path: Path) -> None:
    body = VALID_SKILL.replace('user-invocable:', 'user_invokable:')
    skill_dir = write_skill(tmp_path, 'widget', body)

    found = warnings(skill_dir, tmp_path)

    assert any('user_invokable' in message for message in found), found


def test_a_terse_description_warns(tmp_path: Path) -> None:
    body = VALID_SKILL.replace(DESCRIPTION, 'Widgets.')
    skill_dir = write_skill(tmp_path, 'widget', body)

    found = warnings(skill_dir, tmp_path)

    assert any('description' in message for message in found), found


def test_a_referenced_path_that_is_gone_warns(tmp_path: Path) -> None:
    body = VALID_SKILL + '\nRun `scripts/missing_helper.py` first.\n'
    skill_dir = write_skill(tmp_path, 'widget', body)

    found = warnings(skill_dir, tmp_path)

    assert any('missing_helper.py' in message for message in found), found


def test_a_referenced_path_that_exists_does_not_warn(
    tmp_path: Path,
) -> None:
    body = VALID_SKILL + '\nRead `references/background.md` first.\n'
    skill_dir = write_skill(tmp_path, 'widget', body)
    (skill_dir / 'references').mkdir()
    (skill_dir / 'references' / 'background.md').write_text('# Theory\n')

    assert warnings(skill_dir, tmp_path) == []


def test_a_repo_relative_referenced_path_resolves_against_the_root(
    tmp_path: Path,
) -> None:
    body = VALID_SKILL + '\nSee `scripts/install.sh`.\n'
    skill_dir = write_skill(tmp_path, 'widget', body)
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts' / 'install.sh').write_text('#!/bin/sh\n')

    assert warnings(skill_dir, tmp_path) == []


@pytest.mark.parametrize(
    'token',
    [
        '$SKILL_TREE_DIR/skills/widget/SKILL.md',
        '${CLAUDE_PLUGIN_ROOT}/skills/widget/SKILL.md',
        '~/.claude/skills/widget/SKILL.md',
        '/usr/bin/env',
        'skills/<name>/SKILL.md',
        'https://example.com/a/b.md',
        'some phrase with spaces/and.md',
    ],
)
def test_unresolvable_pathish_tokens_are_not_staleness(
    tmp_path: Path,
    token: str,
) -> None:
    body = VALID_SKILL + f'\nSee `{token}`.\n'
    skill_dir = write_skill(tmp_path, 'widget', body)

    assert warnings(skill_dir, tmp_path) == []


def test_a_long_reference_file_warns(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'widget', VALID_SKILL)
    (skill_dir / 'references').mkdir()
    (skill_dir / 'references' / 'big.md').write_text('line\n' * 900)

    found = warnings(skill_dir, tmp_path)

    assert any('big.md' in message for message in found), found


# --- discovery --------------------------------------------------------


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
    assert data['description'] == DESCRIPTION
    assert data['user-invocable'] == 'true'


# --- CLI --------------------------------------------------------------


def test_run_audit_covers_every_skill(tmp_path: Path) -> None:
    write_skill(tmp_path, 'widget', VALID_SKILL)
    write_skill(tmp_path, 'gadget', '# no frontmatter\n')

    findings = run_audit(tmp_path)

    assert [finding.skill for finding in findings] == ['gadget']


def test_main_is_clean_on_a_sound_tree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_skill(tmp_path, 'widget', VALID_SKILL)

    assert main([str(tmp_path)]) == EXIT_OK
    assert 'no findings' in capsys.readouterr().out


def test_main_fails_on_an_error(tmp_path: Path) -> None:
    write_skill(tmp_path, 'widget', '# nothing\n')

    assert main(['check', str(tmp_path)]) == EXIT_FAILED_CHECK


def test_warnings_alone_pass_unless_strict(tmp_path: Path) -> None:
    body = VALID_SKILL + '\nfiller line\n' * (MAX_SKILL_LINES + 1)
    write_skill(tmp_path, 'widget', body)

    assert main([str(tmp_path)]) == EXIT_OK
    assert main([str(tmp_path), '--strict']) == EXIT_FAILED_CHECK


def test_main_reports_a_tree_with_no_skills(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == EXIT_NOTHING_TO_CHECK


def test_json_output_is_machine_readable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_skill(tmp_path, 'widget', '# nothing\n')

    main([str(tmp_path), '--json'])
    payload = json.loads(capsys.readouterr().out)

    assert payload['findings'][0]['severity'] == 'error'
    assert payload['summary']


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['--version'])

    assert exit_info.value.code == 0
    assert version() in capsys.readouterr().out


def test_real_repo_skills_all_validate() -> None:
    """The checked-in skill-tree skills must satisfy their own validator."""
    repo_root = Path(__file__).parent.parent.parent.parent

    errors = [
        error
        for skill_dir in find_skill_dirs(repo_root)
        for error in validate_skill(skill_dir)
    ]

    assert errors == []
