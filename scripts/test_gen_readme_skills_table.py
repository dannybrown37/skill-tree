"""Tests for the README skill-table generator."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import gen_readme_skills_table as gen


def make_skill(root: Path, name: str, description: str) -> Path:
    skill_dir = root / 'skills' / name
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n',
    )
    return skill_dir


def make_readme(root: Path, table: str = '') -> Path:
    readme = root / 'README.md'
    readme.write_text(
        f'# Repo\n\n{gen.START_MARKER}\n{table}\n{gen.END_MARKER}\n\nTail.\n',
    )
    return readme


class TestBuildTable:
    def test_one_row_per_skill_with_its_description(
        self,
        tmp_path: Path,
    ) -> None:
        make_skill(tmp_path, 'verify', 'Prove the answer.')
        make_skill(tmp_path, 'handoff', 'Survive compaction.')

        table = gen.build_table(tmp_path)

        assert '| `verify` | Prove the answer. |' in table
        assert '| `handoff` | Survive compaction. |' in table

    def test_starts_with_the_header_row(self, tmp_path: Path) -> None:
        make_skill(tmp_path, 'verify', 'Prove the answer.')

        assert gen.build_table(tmp_path).startswith(
            '| Skill | What it does |\n| --- | --- |',
        )

    @pytest.mark.parametrize(
        'description',
        ['TODO', 'TODO: write this', ''],
        ids=['todo', 'todo-prefixed', 'empty'],
    )
    def test_a_placeholder_description_is_refused(
        self,
        tmp_path: Path,
        description: str,
    ) -> None:
        make_skill(tmp_path, 'verify', description)

        with pytest.raises(SystemExit, match='verify'):
            gen.build_table(tmp_path)


class TestMain:
    def test_rewrites_the_table_between_the_markers(
        self,
        tmp_path: Path,
    ) -> None:
        make_skill(tmp_path, 'verify', 'Prove the answer.')
        readme = make_readme(tmp_path, '| stale | stale |')

        assert gen.main([], root=tmp_path) == 0
        text = readme.read_text()
        assert 'stale' not in text
        assert '| `verify` | Prove the answer. |' in text

    def test_leaves_the_text_outside_the_markers_alone(
        self,
        tmp_path: Path,
    ) -> None:
        make_skill(tmp_path, 'verify', 'Prove the answer.')
        readme = make_readme(tmp_path)

        gen.main([], root=tmp_path)
        text = readme.read_text()

        assert text.startswith('# Repo\n')
        assert text.endswith('Tail.\n')

    def test_is_idempotent(self, tmp_path: Path) -> None:
        make_skill(tmp_path, 'verify', 'Prove the answer.')
        readme = make_readme(tmp_path)

        gen.main([], root=tmp_path)
        once = readme.read_text()
        gen.main([], root=tmp_path)

        assert readme.read_text() == once

    def test_missing_markers_is_an_error_that_names_them(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_skill(tmp_path, 'verify', 'Prove the answer.')
        (tmp_path / 'README.md').write_text('# Repo\n\nNo markers here.\n')

        assert gen.main([], root=tmp_path) == 1
        assert gen.START_MARKER in capsys.readouterr().err


class TestVersion:
    def test_reads_the_version_from_the_plugin_manifest(
        self,
        tmp_path: Path,
    ) -> None:
        manifest = tmp_path / '.claude-plugin'
        manifest.mkdir()
        (manifest / 'plugin.json').write_text('{"version": "9.9.9"}')

        assert gen.version(tmp_path) == '9.9.9'

    @pytest.mark.parametrize(
        'contents',
        [None, 'not json', '{}'],
        ids=['missing', 'unparseable', 'no-version-key'],
    )
    def test_an_unreadable_manifest_is_unknown_not_a_crash(
        self,
        tmp_path: Path,
        contents: str | None,
    ) -> None:
        if contents is not None:
            manifest = tmp_path / '.claude-plugin'
            manifest.mkdir()
            (manifest / 'plugin.json').write_text(contents)

        assert gen.version(tmp_path) == 'unknown'

    @pytest.mark.parametrize('flag', ['--version', '-V'])
    def test_the_flag_prints_a_version_and_exits_zero(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        flag: str,
    ) -> None:
        manifest = tmp_path / '.claude-plugin'
        manifest.mkdir()
        (manifest / 'plugin.json').write_text('{"version": "9.9.9"}')

        assert gen.main([flag], root=tmp_path) == 0
        assert capsys.readouterr().out == 'gen-readme-skills-table 9.9.9\n'

    def test_the_flag_does_not_need_a_readme(self, tmp_path: Path) -> None:
        assert gen.main(['--version'], root=tmp_path) == 0
