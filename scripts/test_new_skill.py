"""Tests for the scaffolding scripts' argument handling.

Both scripts take a name that becomes a path, so what they refuse to
accept is the interesting half.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
NEW_SKILL = REPO_ROOT / 'scripts' / 'new-skill.sh'
NEW_OUTPUT_STYLE = REPO_ROOT / 'scripts' / 'new-output-style.sh'


def run(
    script: Path,
    *args: str,
    root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke a scaffolding script with its editor step disabled."""
    env = {
        'PATH': os.environ['PATH'],
        'HOME': str(root) if root else os.environ['HOME'],
        # open_in_editor is interactive and not what these tests are about.
        'EDITOR': 'true',
        'VISUAL': 'true',
    }
    if root is not None:
        env['SKILL_TREE_ROOT'] = str(root)
    return subprocess.run(  # noqa: S603
        ['bash', str(script), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        env=env,
    )


SCRIPTS = [
    pytest.param(NEW_SKILL, id='new-skill'),
    pytest.param(NEW_OUTPUT_STYLE, id='new-output-style'),
]


@pytest.mark.parametrize('script', SCRIPTS)
class TestRejectedNames:
    @pytest.mark.parametrize(
        'name',
        ['--version', '-h', '--force', '-'],
        ids=['long-flag', 'short-flag', 'unknown-flag', 'bare-dash'],
    )
    def test_a_flag_is_never_treated_as_a_name(
        self,
        script: Path,
        name: str,
        tmp_path: Path,
    ) -> None:
        run(script, name, root=tmp_path)

        # Either it's a flag the script knows, or it's an error -- what it
        # must never be is a directory named after the flag.
        assert not (tmp_path / 'skills' / name).exists()
        assert not (tmp_path / 'output-styles' / f'{name}.md').exists()

    @pytest.mark.parametrize(
        'name',
        ['../escape', 'a/b', 'Capitalized', 'has space', 'under_score', ''],
        ids=[
            'traversal',
            'slash',
            'capitals',
            'space',
            'underscore',
            'empty',
        ],
    )
    def test_a_non_kebab_case_name_is_refused(
        self,
        script: Path,
        name: str,
        tmp_path: Path,
    ) -> None:
        result = run(script, name, root=tmp_path)

        assert result.returncode != 0
        # An empty name with no TTY fails at the prompt instead.
        assert any(
            reason in result.stderr
            for reason in ('kebab-case', 'required', 'no TTY')
        )

    def test_version_prints_and_exits_zero(
        self,
        script: Path,
    ) -> None:
        # No SKILL_TREE_ROOT: the version comes from this checkout's
        # manifest.
        result = run(script, '--version')

        assert result.returncode == 0, result.stderr
        assert 'unknown' not in result.stdout
        assert any(char.isdigit() for char in result.stdout)

    def test_help_prints_usage_and_exits_zero(
        self,
        script: Path,
        tmp_path: Path,
    ) -> None:
        result = run(script, '--help', root=tmp_path)

        assert result.returncode == 0, result.stderr
        assert 'Usage:' in result.stdout


class TestNewSkill:
    def test_creates_the_skill_from_a_valid_name(self, tmp_path: Path) -> None:
        result = run(NEW_SKILL, 'widget-thing', root=tmp_path)

        skill_md = tmp_path / 'skills' / 'widget-thing' / 'SKILL.md'
        assert result.returncode == 0, result.stderr
        assert skill_md.is_file()
        assert 'name: widget-thing' in skill_md.read_text()
        assert '# Widget Thing' in skill_md.read_text()

    def test_refuses_to_clobber_an_existing_skill(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / 'skills' / 'widget-thing').mkdir(parents=True)

        result = run(NEW_SKILL, 'widget-thing', root=tmp_path)

        assert result.returncode != 0
        assert 'already exists' in result.stderr


class TestNewOutputStyle:
    def test_creates_the_style_from_a_valid_name(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / 'output-styles').mkdir(parents=True)

        result = run(NEW_OUTPUT_STYLE, 'terse-mode', root=tmp_path)

        style = tmp_path / 'output-styles' / 'terse-mode.md'
        assert result.returncode == 0, result.stderr
        assert style.is_file()
        assert 'name: Terse Mode' in style.read_text()
