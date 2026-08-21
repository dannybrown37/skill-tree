"""Tests for the top-level `skill-tree` CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import skill_tree_cli as cli

REPO_ROOT = Path(__file__).parent.parent
WRAPPER = REPO_ROOT / 'scripts' / 'skill-tree'


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A miniature skill-tree checkout: two skills, one with a CLI."""
    skills = tmp_path / 'skills'

    plain = skills / 'verify'
    plain.mkdir(parents=True)
    (plain / 'SKILL.md').write_text(
        '---\n'
        'name: verify\n'
        'description: "Invoke before answering whether something works."\n'
        'user-invocable: true\n'
        '---\n'
        '\n'
        '# Verify\n'
        '\n'
        'Answer, then prove the answer.\n',
    )

    with_cli = skills / 'backlog'
    (with_cli / 'scripts').mkdir(parents=True)
    (with_cli / 'SKILL.md').write_text(
        '---\nname: backlog\ndescription: Shared work items.\n---\n'
        '\n# Backlog\n',
    )
    wrapper = with_cli / 'scripts' / 'backlog'
    wrapper.write_text('#!/usr/bin/env bash\necho "backlog ran: $*"\n')
    wrapper.chmod(0o755)

    return tmp_path


def run_cli(*args: str, root: Path | None = None) -> tuple[int, str, str]:
    """Invoke main() in-process, capturing what it wrote."""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = cli.main(list(args), root=root)
    return code, out.getvalue(), err.getvalue()


class TestFindSkills:
    def test_reads_name_and_description_from_frontmatter(
        self,
        fake_root: Path,
    ) -> None:
        skills = cli.find_skills(fake_root)

        assert [s.name for s in skills] == ['backlog', 'verify']
        assert skills[1].description.startswith('Invoke before answering')

    def test_flags_which_skills_ship_an_executable_cli(
        self,
        fake_root: Path,
    ) -> None:
        by_name = {s.name: s for s in cli.find_skills(fake_root)}

        assert by_name['backlog'].cli is not None
        assert by_name['verify'].cli is None

    def test_unescapes_quotes_inside_a_quoted_description(
        self,
        fake_root: Path,
    ) -> None:
        skill_md = fake_root / 'skills' / 'verify' / 'SKILL.md'
        skill_md.write_text(
            skill_md.read_text().replace(
                'something works.',
                'something \\"works\\".',
            ),
        )

        by_name = {s.name: s for s in cli.find_skills(fake_root)}

        assert by_name['verify'].description.endswith('"works".')

    def test_no_skills_directory_is_not_an_error(self, tmp_path: Path) -> None:
        assert cli.find_skills(tmp_path) == []

    def test_skips_directories_without_a_skill_md(
        self,
        fake_root: Path,
    ) -> None:
        (fake_root / 'skills' / 'not-a-skill').mkdir()

        assert 'not-a-skill' not in {
            s.name for s in cli.find_skills(fake_root)
        }


class TestList:
    def test_lists_every_skill_with_its_description(
        self,
        fake_root: Path,
    ) -> None:
        code, out, _ = run_cli('list', root=fake_root)

        assert code == 0
        assert 'backlog' in out
        assert 'verify' in out
        assert 'Shared work items.' in out

    def test_marks_the_skills_that_have_a_cli(self, fake_root: Path) -> None:
        _, out, _ = run_cli('list', root=fake_root)

        backlog_line = next(
            line for line in out.splitlines() if 'backlog' in line
        )
        assert 'has a CLI' in backlog_line
        assert not any(
            'has a CLI' in line
            for line in out.splitlines()
            if 'verify' in line
        )

    def test_json_output_is_machine_readable(self, fake_root: Path) -> None:
        _, out, _ = run_cli('list', '--json', root=fake_root)

        payload = json.loads(out)
        assert [entry['name'] for entry in payload] == ['backlog', 'verify']
        assert payload[0]['cli'].endswith('skills/backlog/scripts/backlog')
        assert payload[1]['cli'] is None


class TestOverview:
    """A bare `skill-tree` has to show the whole surface, not half of it."""

    @pytest.mark.parametrize('args', [(), ('help',), ('--help',), ('-h',)])
    def test_names_every_command(
        self,
        fake_root: Path,
        args: tuple[str, ...],
    ) -> None:
        code, out, _ = run_cli(*args, root=fake_root)

        assert code == 0
        for command in (
            'list',
            'show',
            'doctor',
            'install',
            'dev',
            'check',
            'test',
        ):
            assert command in out

    def test_also_lists_the_skills(self, fake_root: Path) -> None:
        _, out, _ = run_cli(root=fake_root)

        assert 'verify' in out
        assert 'Shared work items.' in out

    def test_names_the_skill_clis_reachable_by_name(
        self,
        fake_root: Path,
    ) -> None:
        _, out, _ = run_cli(root=fake_root)

        assert 'skill-tree backlog [args]' in out

    def test_a_leading_flag_still_belongs_to_list(
        self,
        fake_root: Path,
    ) -> None:
        _, out, _ = run_cli('--json', root=fake_root)

        assert json.loads(out)[0]['name'] == 'backlog'


class TestShow:
    def test_prints_the_skill_md_body(self, fake_root: Path) -> None:
        code, out, _ = run_cli('show', 'verify', root=fake_root)

        assert code == 0
        assert '# Verify' in out
        assert 'Answer, then prove the answer.' in out

    def test_omits_frontmatter_by_default(self, fake_root: Path) -> None:
        _, out, _ = run_cli('show', 'verify', root=fake_root)

        assert 'user-invocable' not in out

    def test_raw_keeps_the_frontmatter(self, fake_root: Path) -> None:
        _, out, _ = run_cli('show', 'verify', '--raw', root=fake_root)

        assert 'user-invocable: true' in out

    def test_unknown_skill_is_an_error_that_names_the_real_ones(
        self,
        fake_root: Path,
    ) -> None:
        code, _, err = run_cli('show', 'nope', root=fake_root)

        assert code == 1
        assert 'nope' in err
        assert 'backlog, verify' in err


class TestRun:
    def test_delegates_to_the_skills_own_cli(self, fake_root: Path) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(cli.__file__), 'backlog', 'claim', '-a'],
            capture_output=True,
            text=True,
            env={'SKILL_TREE_ROOT': str(fake_root), 'PATH': '/usr/bin:/bin'},
            check=False,
        )

        assert result.returncode == 0
        assert 'backlog ran: claim -a' in result.stdout

    def test_propagates_the_delegated_exit_code(self, fake_root: Path) -> None:
        failure_code = 3
        wrapper = fake_root / 'skills' / 'backlog' / 'scripts' / 'backlog'
        wrapper.write_text(f'#!/usr/bin/env bash\nexit {failure_code}\n')
        wrapper.chmod(0o755)

        code, _, _ = run_cli('backlog', root=fake_root)

        assert code == failure_code

    def test_a_skill_without_a_cli_says_so(self, fake_root: Path) -> None:
        code, _, err = run_cli('verify', root=fake_root)

        assert code == 1
        assert 'no CLI' in err
        assert 'skill-tree show verify' in err

    def test_passes_help_flags_through_to_the_skills_cli(
        self,
        fake_root: Path,
    ) -> None:
        """Ours is only the *leading* -h -- the rest is the skill's."""
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(cli.__file__), 'backlog', '--help'],
            capture_output=True,
            text=True,
            env={'SKILL_TREE_ROOT': str(fake_root), 'PATH': '/usr/bin:/bin'},
            check=False,
        )

        assert result.returncode == 0
        assert 'backlog ran: --help' in result.stdout
        assert 'Usage: skill-tree' not in result.stdout

    def test_unknown_subcommand_is_an_error(self, fake_root: Path) -> None:
        code, _, err = run_cli('nonsense', root=fake_root)

        assert code == 1
        assert 'nonsense' in err


def _fake_dev_link(root: Path, status: str) -> None:
    """Stand in for dev_link.sh, which needs a real plugin install."""
    scripts = root / 'scripts'
    scripts.mkdir(exist_ok=True)
    script = scripts / 'dev_link.sh'
    script.write_text(f'#!/usr/bin/env bash\necho "{status}"\n')
    script.chmod(0o755)


class TestDevModeIndicator:
    """Dev mode changes which copy of the repo Claude runs -- say so."""

    @pytest.mark.parametrize(
        ('status', 'expected'),
        [
            ('Dev mode ON  (/x -> /y)', 'ON'),
            ('Dev mode OFF (real install at /x)', 'OFF'),
            ('something unexpected', '?'),
        ],
    )
    def test_overview_flags_the_dev_command(
        self,
        fake_root: Path,
        status: str,
        expected: str,
    ) -> None:
        _fake_dev_link(fake_root, status)

        _, out, _ = run_cli(root=fake_root)

        dev_line = next(
            line for line in out.splitlines() if line.strip().startswith('dev')
        )
        assert f'[dev mode {expected}]' in dev_line

    def test_overview_stays_quiet_without_dev_link(
        self,
        fake_root: Path,
    ) -> None:
        _, out, _ = run_cli(root=fake_root)

        assert 'dev mode' not in out


class TestDoctor:
    def test_reports_the_checkout_and_each_skill_cli(
        self,
        fake_root: Path,
    ) -> None:
        code, out, _ = run_cli('doctor', root=fake_root)

        assert code == 0
        assert str(fake_root) in out
        assert 'backlog' in out

    def test_reports_copilot_as_uninstalled(
        self,
        fake_root: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv('HOME', str(tmp_path / 'empty-home'))

        _, out, _ = run_cli('doctor', root=fake_root)

        assert 'Copilot    not installed' in out

    def test_counts_linked_copilot_skills(
        self,
        fake_root: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        home = tmp_path / 'home'
        skills_dir = home / '.copilot' / 'skills'
        skills_dir.mkdir(parents=True)
        (skills_dir / 'backlog').symlink_to(fake_root / 'skills' / 'backlog')
        monkeypatch.setenv('HOME', str(home))

        _, out, _ = run_cli('doctor', root=fake_root)

        assert '1/2 skills linked, hooks missing' in out

    def test_notices_the_hook_config(
        self,
        fake_root: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        home = tmp_path / 'home'
        hooks = home / '.copilot' / 'hooks'
        hooks.mkdir(parents=True)
        (hooks / 'skill-tree.json').write_text('{}')
        monkeypatch.setenv('HOME', str(home))

        _, out, _ = run_cli('doctor', root=fake_root)

        assert 'hooks on' in out


class TestRealRepo:
    """The CLI has to work against this checkout, not just a fixture."""

    def test_lists_this_repos_skills(self) -> None:
        names = {s.name for s in cli.find_skills(REPO_ROOT)}

        assert {'screenshot', 'verify'} <= names

    def test_wrapper_is_executable_and_lists_skills(self) -> None:
        result = subprocess.run(  # noqa: S603
            [str(WRAPPER), 'list'],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert 'verify' in result.stdout


class TestVersion:
    def test_reads_the_version_from_the_plugin_manifest(
        self,
        fake_root: Path,
    ) -> None:
        manifest = fake_root / '.claude-plugin'
        manifest.mkdir()
        (manifest / 'plugin.json').write_text('{"version": "9.9.9"}')
        assert cli.version(fake_root) == '9.9.9'

    @pytest.mark.parametrize(
        'contents',
        [None, 'not json', '{"name": "skill-tree"}'],
        ids=['missing', 'unparseable', 'no-version-key'],
    )
    def test_an_unreadable_manifest_is_unknown_not_a_crash(
        self,
        fake_root: Path,
        contents: str | None,
    ) -> None:
        if contents is not None:
            manifest = fake_root / '.claude-plugin'
            manifest.mkdir()
            (manifest / 'plugin.json').write_text(contents)
        assert cli.version(fake_root) == 'unknown'

    @pytest.mark.parametrize('flag', ['--version', '-V'])
    def test_the_flag_prints_a_version_and_exits_zero(
        self,
        fake_root: Path,
        capsys: pytest.CaptureFixture[str],
        flag: str,
    ) -> None:
        manifest = fake_root / '.claude-plugin'
        manifest.mkdir()
        (manifest / 'plugin.json').write_text('{"version": "9.9.9"}')

        assert cli.main([flag], root=fake_root) == 0
        assert capsys.readouterr().out == 'skill-tree 9.9.9\n'

    def test_the_flag_beats_the_leading_flag_route_to_list(
        self,
        fake_root: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cli.main(['--version'], root=fake_root)
        assert 'verify' not in capsys.readouterr().out

    def test_version_after_a_skill_name_belongs_to_that_skill(
        self,
        fake_root: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert cli.main(['backlog', '--version'], root=fake_root) == 0
        assert 'skill-tree' not in capsys.readouterr().out

    def test_the_wrapper_reports_a_version_with_no_config(
        self,
        tmp_path: Path,
    ) -> None:
        # An empty HOME stands in for "no config, no credentials"; PATH
        # stays real because the wrapper legitimately needs `uv`.
        env = {'PATH': os.environ['PATH'], 'HOME': str(tmp_path)}
        result = subprocess.run(  # noqa: S603
            [str(WRAPPER), '--version'],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert result.returncode == 0
        assert result.stdout.startswith('skill-tree ')
        assert 'unknown' not in result.stdout
