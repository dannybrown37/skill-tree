"""Tests for the cli-ergonomics entrypoint linter."""

import json
from pathlib import Path

import pytest

from cli_ergonomics_cli import (
    EXIT_FAILED_CHECK,
    EXIT_OK,
    EXIT_UNUSABLE,
    CliErgonomicsError,
    Status,
    check_no_args_help,
    check_tty_guard,
    check_version,
    find_clis,
    lint,
    lint_cli,
    main,
    sources_for,
)

ARGPARSE_OK = """\
import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog='mine')
    parser.add_argument('--version', action='version', version='mine 1.0')
    parser.add_argument('directory', nargs='?', default='.')
    parser.parse_args()
    return 0
"""

ARGPARSE_REQUIRED_POSITIONAL = """\
import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog='mine')
    parser.add_argument('--version', action='version', version='mine 1.0')
    parser.add_argument('directory')
    parser.parse_args()
    return 0
"""


def write(
    root: Path,
    rel: str,
    text: str,
    *,
    executable: bool = False,
) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if executable:
        path.chmod(0o755)
    return path


def wrapper(root: Path, name: str, module: str) -> Path:
    write(root, f'scripts/{module}', ARGPARSE_OK)
    return write(
        root,
        f'scripts/{name}',
        f'#!/usr/bin/env bash\nexec python3 "${{_here}}/{module}" "$@"\n',
        executable=True,
    )


class TestFindClis:
    def test_finds_executable_scripts(self, tmp_path: Path) -> None:
        write(tmp_path, 'scripts/mine', '#!/bin/sh\n', executable=True)
        assert 'mine' in find_clis(tmp_path)

    def test_finds_pyproject_scripts(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'pyproject.toml',
            '[project.scripts]\nmine = "pkg:main"\n',
        )
        write(tmp_path, 'scripts/mine', '#!/bin/sh\n')
        assert 'mine' in find_clis(tmp_path)

    def test_finds_package_json_bin(self, tmp_path: Path) -> None:
        write(tmp_path, 'package.json', '{"bin": {"mine": "./cli.js"}}')
        write(tmp_path, 'cli.js', '#!/usr/bin/env node\n')
        assert 'mine' in find_clis(tmp_path)

    def test_ignores_non_executable_undeclared_scripts(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'scripts/mine', '#!/bin/sh\n')
        assert find_clis(tmp_path) == {}

    def test_ignores_test_files(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'scripts/test_mine.py',
            '#!/usr/bin/env python3\n',
            executable=True,
        )
        assert find_clis(tmp_path) == {}

    def test_shell_helpers_are_skipped_by_default(
        self,
        tmp_path: Path,
    ) -> None:
        write(
            tmp_path,
            'scripts/bootstrap.sh',
            '#!/bin/bash\n',
            executable=True,
        )
        assert find_clis(tmp_path) == {}

    def test_shell_helpers_opt_in(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'scripts/bootstrap.sh',
            '#!/bin/bash\n',
            executable=True,
        )
        assert 'bootstrap.sh' in find_clis(tmp_path, include_helpers=True)


class TestSourcesFor:
    def test_follows_a_wrapper_to_its_module(self, tmp_path: Path) -> None:
        path = wrapper(tmp_path, 'mine', 'mine_cli.py')
        assert sources_for(path) == [
            path,
            tmp_path / 'scripts' / 'mine_cli.py',
        ]

    def test_standalone_script_is_its_own_source(self, tmp_path: Path) -> None:
        path = write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        assert sources_for(path) == [path]

    def test_missing_entrypoint_has_no_sources(self, tmp_path: Path) -> None:
        assert sources_for(tmp_path / 'scripts' / 'gone') == []


class TestCheckVersion:
    def test_argparse_version_action_passes(self, tmp_path: Path) -> None:
        path = write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        assert check_version(sources_for(path)).status is Status.PASS

    def test_bash_case_branch_passes(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            '#!/usr/bin/env bash\ncase "$1" in\n'
            '--version) echo 1.0 ;;\nesac\n',
            executable=True,
        )
        assert check_version(sources_for(path)).status is Status.PASS

    def test_missing_version_fails(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            '#!/usr/bin/env bash\necho hi\n',
            executable=True,
        )
        result = check_version(sources_for(path))
        assert result.status is Status.FAIL
        assert '--version' in result.detail

    def test_wrapper_inherits_its_modules_version(
        self,
        tmp_path: Path,
    ) -> None:
        path = wrapper(tmp_path, 'mine', 'mine_cli.py')
        assert check_version(sources_for(path)).status is Status.PASS

    def test_declared_but_missing_entrypoint_fails(self) -> None:
        result = check_version([])
        assert result.status is Status.FAIL
        assert 'not readable' in result.detail


class TestCheckNoArgsHelp:
    def test_optional_positional_passes(self, tmp_path: Path) -> None:
        path = write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        assert check_no_args_help(sources_for(path)).status is Status.PASS

    def test_required_positional_fails(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            ARGPARSE_REQUIRED_POSITIONAL,
            executable=True,
        )
        result = check_no_args_help(sources_for(path))
        assert result.status is Status.FAIL
        assert 'directory' in result.detail

    def test_required_positional_with_explicit_help_passes(
        self,
        tmp_path: Path,
    ) -> None:
        source = ARGPARSE_REQUIRED_POSITIONAL.replace(
            '    parser.parse_args()',
            '    if len(sys.argv) == 1:\n'
            '        parser.print_help()\n'
            '        return 0\n'
            '    parser.parse_args()',
        )
        path = write(tmp_path, 'scripts/mine', source, executable=True)
        assert check_no_args_help(sources_for(path)).status is Status.PASS

    def test_non_python_is_manual(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            '#!/usr/bin/env bash\necho "$1"\n',
            executable=True,
        )
        result = check_no_args_help(sources_for(path))
        assert result.status is Status.MANUAL

    def test_unparseable_python_is_manual(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            'import argparse\ndef (:\n',
            executable=True,
        )
        assert check_no_args_help(sources_for(path)).status is Status.MANUAL


class TestCheckTtyGuard:
    def test_no_prompts_passes(self, tmp_path: Path) -> None:
        path = write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        result = check_tty_guard(sources_for(path))
        assert result.status is Status.PASS
        assert 'no prompt' in result.detail

    def test_guarded_input_passes(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            'import sys\n\n\ndef ask() -> str:\n'
            '    if not sys.stdin.isatty():\n'
            "        raise RuntimeError('no tty')\n"
            "    return input('name: ')\n",
            executable=True,
        )
        assert check_tty_guard(sources_for(path)).status is Status.PASS

    def test_unguarded_input_fails(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            "name = input('name: ')\n",
            executable=True,
        )
        result = check_tty_guard(sources_for(path))
        assert result.status is Status.FAIL
        assert 'isatty' in result.detail

    def test_unguarded_bash_read_fails(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            '#!/usr/bin/env bash\nread -r -p "name: " name\n',
            executable=True,
        )
        assert check_tty_guard(sources_for(path)).status is Status.FAIL

    def test_guarded_bash_read_passes(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/mine',
            '#!/usr/bin/env bash\n'
            'if [ -t 0 ]; then read -r -p "name: " name; fi\n',
            executable=True,
        )
        assert check_tty_guard(sources_for(path)).status is Status.PASS

    @pytest.mark.parametrize(
        'source',
        [
            'with path.open() as handle:\n    data = handle.read()\n',
            'text = sys.stdin.read()\n',
        ],
    )
    def test_reading_a_file_is_not_a_prompt(
        self,
        tmp_path: Path,
        source: str,
    ) -> None:
        path = write(tmp_path, 'scripts/mine', source, executable=True)
        assert check_tty_guard(sources_for(path)).status is Status.PASS


class TestLintCli:
    def test_reports_every_rule(self, tmp_path: Path) -> None:
        path = write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        report = lint_cli('mine', path)
        assert [check.rule for check in report.checks] == [
            'version',
            'no-args-help',
            'tty-guard',
        ]

    def test_nothing_is_executed(self, tmp_path: Path) -> None:
        canary = tmp_path / 'ran'
        path = write(
            tmp_path,
            'scripts/mine',
            f'#!/bin/sh\ntouch {canary}\n',
            executable=True,
        )
        lint_cli('mine', path)
        assert not canary.exists()


class TestMain:
    def test_clean_repo_exits_zero(self, tmp_path: Path, capsys) -> None:  # noqa: ANN001
        write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        assert main([str(tmp_path)]) == EXIT_OK
        assert 'mine' in capsys.readouterr().out

    def test_violation_exits_one(self, tmp_path: Path, capsys) -> None:  # noqa: ANN001
        write(
            tmp_path,
            'scripts/mine',
            '#!/bin/sh\necho hi\n',
            executable=True,
        )
        assert main([str(tmp_path)]) == EXIT_FAILED_CHECK
        assert '--version' in capsys.readouterr().out

    def test_no_clis_exits_zero(self, tmp_path: Path, capsys) -> None:  # noqa: ANN001
        write(tmp_path, 'notes.md', 'x')
        assert main([str(tmp_path)]) == EXIT_OK
        assert 'no CLI entrypoints' in capsys.readouterr().out

    def test_missing_directory_is_unusable(
        self,
        tmp_path: Path,
        capsys,  # noqa: ANN001
    ) -> None:
        assert main([str(tmp_path / 'gone')]) == EXIT_UNUSABLE
        assert 'cli-ergonomics:' in capsys.readouterr().err

    def test_lint_subcommand_is_implied(self, tmp_path: Path) -> None:
        write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        assert main(['lint', str(tmp_path)]) == main([str(tmp_path)])

    def test_json_output_parses(self, tmp_path: Path, capsys) -> None:  # noqa: ANN001
        write(tmp_path, 'scripts/mine', ARGPARSE_OK, executable=True)
        main([str(tmp_path), '--json'])
        payload = json.loads(capsys.readouterr().out)
        assert payload['clis'][0]['name'] == 'mine'
        assert payload['summary']

    def test_version_exits_zero(self, capsys) -> None:  # noqa: ANN001
        with pytest.raises(SystemExit) as exit_info:
            main(['--version'])
        assert exit_info.value.code == 0
        assert 'cli-ergonomics' in capsys.readouterr().out

    def test_include_helpers_widens_the_sweep(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'scripts/b.sh',
            '#!/bin/bash\necho hi\n',
            executable=True,
        )
        assert main([str(tmp_path)]) == EXIT_OK
        assert main([str(tmp_path), '--include-helpers']) == EXIT_FAILED_CHECK


def test_error_type_is_public() -> None:
    assert issubclass(CliErgonomicsError, Exception)


class TestLintDeduplication:
    def test_a_wrapped_module_is_not_listed_twice(
        self,
        tmp_path: Path,
    ) -> None:
        wrapper(tmp_path, 'mine', 'mine_cli.py')
        (tmp_path / 'scripts' / 'mine_cli.py').chmod(0o755)
        assert [report.name for report in lint(tmp_path)] == ['mine']

    def test_hooks_are_not_entrypoints(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'scripts/thing_hook.py',
            'print("hi")\n',
            executable=True,
        )
        assert find_clis(tmp_path) == {}
