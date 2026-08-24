"""Tests for the repo-audit CLI's filesystem checks."""

import json
from pathlib import Path

import pytest

from repo_audit_cli import (
    EXIT_FAILED_CHECK,
    EXIT_OK,
    EXIT_UNUSABLE,
    RepoAuditError,
    Stack,
    Status,
    check_docs_freshness,
    check_entrypoints,
    check_tests,
    check_workflows,
    find_entrypoints,
    referenced_paths,
    untested_modules,
    check_lint_config,
    check_pinning,
    check_precommit,
    check_readme,
    check_secrets,
    check_typecheck_config,
    detect_stack,
    main,
    run_checks,
)

PRECOMMIT_FULL = """\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff-check
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    hooks:
      - id: mypy
  - repo: local
    hooks:
      - id: pytest
  - repo: https://github.com/gitleaks/gitleaks
    hooks:
      - id: gitleaks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    hooks:
      - id: end-of-file-fixer
"""

GITIGNORE_FULL = """\
.env
*.pem
credentials.json
__pycache__/
node_modules/
dist/
"""


def write(root: Path, rel: str, text: str = '') -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def clean_python_repo(tmp_path: Path) -> Path:
    write(
        tmp_path,
        'pyproject.toml',
        '[project]\nname = "x"\ndependencies = ["requests==2.31.0"]\n',
    )
    write(tmp_path, 'uv.lock', 'version = 1\n')
    write(tmp_path, '.pre-commit-config.yaml', PRECOMMIT_FULL)
    write(tmp_path, 'mypy.ini', '[mypy]\nstrict = true\n')
    write(tmp_path, '.ruff.toml', 'line-length = 79\n')
    write(tmp_path, '.gitignore', GITIGNORE_FULL)
    write(
        tmp_path,
        'README.md',
        '# x\n\nA small tool that turns widgets into gadgets.\n',
    )
    write(tmp_path, 'src/app.py', 'def go() -> None: ...\n')
    write(tmp_path, 'tests/test_app.py', 'def test_go() -> None: ...\n')
    return tmp_path


class TestDetectStack:
    @pytest.mark.parametrize(
        ('marker', 'expected'),
        [
            ('pyproject.toml', 'python'),
            ('setup.py', 'python'),
            ('requirements.txt', 'python'),
            ('package.json', 'node'),
        ],
    )
    def test_marker_files(
        self,
        tmp_path: Path,
        marker: str,
        expected: str,
    ) -> None:
        write(tmp_path, marker)
        assert getattr(detect_stack(tmp_path), expected) is True

    def test_typescript_needs_tsconfig(self, tmp_path: Path) -> None:
        write(tmp_path, 'package.json', '{}')
        assert detect_stack(tmp_path).typescript is False
        write(tmp_path, 'tsconfig.json', '{}')
        assert detect_stack(tmp_path).typescript is True

    def test_python_from_sources_without_a_manifest(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'scripts/thing.py', 'x = 1\n')
        assert detect_stack(tmp_path).python is True

    def test_node_from_sources_without_a_manifest(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'src/app.ts', 'export const x = 1;\n')
        assert detect_stack(tmp_path).node is True

    def test_shell_from_scripts(self, tmp_path: Path) -> None:
        write(tmp_path, 'scripts/go.sh', '#!/usr/bin/env bash\n')
        assert detect_stack(tmp_path).shell is True

    def test_git_dir_is_not_scanned_for_shell(self, tmp_path: Path) -> None:
        write(tmp_path, '.git/hooks/pre-commit.sh', '#!/bin/sh\n')
        assert detect_stack(tmp_path).shell is False

    def test_empty_repo_detects_nothing(self, tmp_path: Path) -> None:
        assert detect_stack(tmp_path) == Stack()


class TestPrecommit:
    def test_passes_when_all_hooks_present(
        self,
        clean_python_repo: Path,
    ) -> None:
        stack = detect_stack(clean_python_repo)
        result = check_precommit(clean_python_repo, stack)
        assert result.status is Status.PASS

    def test_fails_when_config_missing(self, tmp_path: Path) -> None:
        write(tmp_path, 'pyproject.toml')
        result = check_precommit(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.FAIL
        assert 'pre-commit-config' in result.detail

    @pytest.mark.parametrize(
        'hook',
        ['gitleaks', 'end-of-file-fixer', 'ruff-check', 'mypy', 'pytest'],
    )
    def test_names_each_missing_hook(
        self,
        clean_python_repo: Path,
        hook: str,
    ) -> None:
        config = clean_python_repo / '.pre-commit-config.yaml'
        config.write_text(
            config.read_text().replace(f'- id: {hook}\n', ''),
        )
        result = check_precommit(
            clean_python_repo,
            detect_stack(clean_python_repo),
        )
        assert result.status is Status.FAIL
        assert hook in result.detail

    def test_python_hooks_not_required_without_python(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'package.json', '{}')
        write(
            tmp_path,
            '.pre-commit-config.yaml',
            'repos:\n  - hooks:\n      - id: gitleaks\n'
            '      - id: end-of-file-fixer\n',
        )
        result = check_precommit(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.PASS

    def test_shell_repo_requires_shellcheck(self, tmp_path: Path) -> None:
        write(tmp_path, 'go.sh', '#!/usr/bin/env bash\n')
        write(
            tmp_path,
            '.pre-commit-config.yaml',
            'repos:\n  - hooks:\n      - id: gitleaks\n'
            '      - id: end-of-file-fixer\n',
        )
        result = check_precommit(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.FAIL
        assert 'shellcheck' in result.detail


class TestTypecheckConfig:
    def test_na_without_a_typed_stack(self, tmp_path: Path) -> None:
        result = check_typecheck_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.NA

    def test_python_accepts_mypy_ini(self, clean_python_repo: Path) -> None:
        result = check_typecheck_config(
            clean_python_repo,
            detect_stack(clean_python_repo),
        )
        assert result.status is Status.PASS

    def test_python_accepts_pyproject_section(self, tmp_path: Path) -> None:
        write(tmp_path, 'pyproject.toml', '[tool.mypy]\nstrict = true\n')
        result = check_typecheck_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.PASS

    def test_python_fails_without_config(self, tmp_path: Path) -> None:
        write(tmp_path, 'pyproject.toml', '[project]\nname = "x"\n')
        result = check_typecheck_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.FAIL
        assert 'mypy' in result.detail

    def test_typescript_requires_strict(self, tmp_path: Path) -> None:
        write(tmp_path, 'package.json', '{}')
        write(tmp_path, 'tsconfig.json', '{"compilerOptions": {}}')
        result = check_typecheck_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.FAIL
        assert 'strict' in result.detail

    def test_typescript_strict_passes(self, tmp_path: Path) -> None:
        write(tmp_path, 'package.json', '{}')
        write(
            tmp_path,
            'tsconfig.json',
            '{"compilerOptions": {"strict": true}}',
        )
        result = check_typecheck_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.PASS

    def test_unparseable_tsconfig_is_not_a_crash(self, tmp_path: Path) -> None:
        write(tmp_path, 'package.json', '{}')
        write(tmp_path, 'tsconfig.json', '{ not json,, }')
        result = check_typecheck_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.FAIL


class TestLintConfig:
    def test_na_without_a_lintable_stack(self, tmp_path: Path) -> None:
        assert (
            check_lint_config(tmp_path, detect_stack(tmp_path)).status
            is Status.NA
        )

    def test_python_ruff_toml(self, clean_python_repo: Path) -> None:
        result = check_lint_config(
            clean_python_repo,
            detect_stack(clean_python_repo),
        )
        assert result.status is Status.PASS

    def test_python_missing_ruff(self, tmp_path: Path) -> None:
        write(tmp_path, 'pyproject.toml', '[project]\nname = "x"\n')
        result = check_lint_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.FAIL
        assert 'ruff' in result.detail

    @pytest.mark.parametrize(
        'name',
        ['eslint.config.js', '.eslintrc.json', '.eslintrc.cjs'],
    )
    def test_node_eslint_configs(self, tmp_path: Path, name: str) -> None:
        write(tmp_path, 'package.json', '{}')
        write(tmp_path, name, '')
        result = check_lint_config(tmp_path, detect_stack(tmp_path))
        assert result.status is Status.PASS


class TestSecrets:
    def test_clean_repo_passes(self, clean_python_repo: Path) -> None:
        result = check_secrets(clean_python_repo)
        assert result.status is Status.PASS

    @pytest.mark.parametrize('pattern', ['.env', '*.pem', 'credentials'])
    def test_names_missing_gitignore_pattern(
        self,
        clean_python_repo: Path,
        pattern: str,
    ) -> None:
        path = clean_python_repo / '.gitignore'
        path.write_text(
            '\n'.join(
                line
                for line in path.read_text().splitlines()
                if pattern.strip('*') not in line
            ),
        )
        result = check_secrets(clean_python_repo)
        assert result.status is Status.FAIL
        assert pattern in result.detail

    def test_missing_gitignore_fails(self, tmp_path: Path) -> None:
        result = check_secrets(tmp_path)
        assert result.status is Status.FAIL

    def test_hardcoded_secret_is_flagged(
        self,
        clean_python_repo: Path,
    ) -> None:
        write(
            clean_python_repo,
            'src/conf.py',
            'api_key = "not-a-real-secret"\n',
        )
        result = check_secrets(clean_python_repo)
        assert result.status is Status.FAIL
        assert 'src/conf.py' in result.detail

    def test_env_var_read_is_not_flagged(
        self,
        clean_python_repo: Path,
    ) -> None:
        write(
            clean_python_repo,
            'src/conf.py',
            'import os\napi_key = os.environ["API_KEY"]\n',
        )
        result = check_secrets(clean_python_repo)
        assert result.status is Status.PASS

    def test_test_files_are_not_flagged(
        self,
        clean_python_repo: Path,
    ) -> None:
        write(
            clean_python_repo,
            'src/test_conf.py',
            'password = "hunter2"\n',
        )
        result = check_secrets(clean_python_repo)
        assert result.status is Status.PASS


class TestPinning:
    def test_na_without_dependencies(self, tmp_path: Path) -> None:
        assert check_pinning(tmp_path).status is Status.NA

    def test_uv_lock_passes(self, clean_python_repo: Path) -> None:
        result = check_pinning(clean_python_repo)
        assert result.status is Status.PASS

    def test_no_lockfile_needed_without_declared_deps(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'scripts/thing.py', 'x = 1\n')
        result = check_pinning(tmp_path)
        assert result.status is Status.NA

    def test_python_without_lockfile_fails(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'pyproject.toml',
            '[project]\nname = "x"\ndependencies = ["requests==2.0"]\n',
        )
        result = check_pinning(tmp_path)
        assert result.status is Status.FAIL

    def test_node_without_lockfile_fails(self, tmp_path: Path) -> None:
        write(tmp_path, 'package.json', '{}')
        result = check_pinning(tmp_path)
        assert result.status is Status.FAIL
        assert 'lockfile' in result.detail

    def test_unbounded_dependency_is_flagged(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'pyproject.toml',
            '[project]\ndependencies = ["requests>=2.0"]\n',
        )
        write(tmp_path, 'uv.lock', 'version = 1\n')
        result = check_pinning(tmp_path)
        assert result.status is Status.FAIL
        assert 'requests' in result.detail


class TestReadme:
    def test_clean_readme_passes(self, clean_python_repo: Path) -> None:
        assert check_readme(clean_python_repo).status is Status.PASS

    def test_missing_readme_fails(self, tmp_path: Path) -> None:
        assert check_readme(tmp_path).status is Status.FAIL

    @pytest.mark.parametrize(
        'text',
        [
            '# Getting Started with Create React App\n',
            '# x\n\nThis project was bootstrapped with something.\n',
        ],
    )
    def test_placeholder_readme_fails(self, tmp_path: Path, text: str) -> None:
        write(tmp_path, 'README.md', text)
        result = check_readme(tmp_path)
        assert result.status is Status.FAIL
        assert 'placeholder' in result.detail.lower()

    def test_empty_readme_fails(self, tmp_path: Path) -> None:
        write(tmp_path, 'README.md', '# x\n')
        assert check_readme(tmp_path).status is Status.FAIL


class TestRunChecks:
    def test_rejects_a_file(self, tmp_path: Path) -> None:
        target = write(tmp_path, 'a.txt', 'x')
        with pytest.raises(RepoAuditError):
            run_checks(target)

    def test_rejects_an_unrecognised_tree(self, tmp_path: Path) -> None:
        write(tmp_path, 'notes.txt', 'nothing to audit here')
        with pytest.raises(RepoAuditError):
            run_checks(tmp_path)

    def test_results_are_ordered_by_section(
        self,
        clean_python_repo: Path,
    ) -> None:
        numbers = [result.number for result in run_checks(clean_python_repo)]
        assert numbers == sorted(numbers)

    def test_every_section_is_reported(
        self,
        clean_python_repo: Path,
    ) -> None:
        numbers = {result.number for result in run_checks(clean_python_repo)}
        assert numbers == {1, 2, 3, 4, 5, 6, 7, 8, 9, 11}

    def test_tool_sections_are_manual_until_run(
        self,
        clean_python_repo: Path,
    ) -> None:
        manual = {
            result.number
            for result in run_checks(clean_python_repo)
            if result.status is Status.MANUAL
        }
        assert manual == {4}


class TestMain:
    def test_version_exits_zero(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--version'])
        assert exit_info.value.code == EXIT_OK
        assert 'repo-audit' in capsys.readouterr().out

    def test_clean_repo_exits_zero(self, clean_python_repo: Path) -> None:
        assert main(['audit', str(clean_python_repo)]) == EXIT_OK

    def test_failing_repo_exits_one(self, tmp_path: Path) -> None:
        write(tmp_path, 'pyproject.toml', '[project]\nname = "x"\n')
        assert main(['audit', str(tmp_path)]) == EXIT_FAILED_CHECK

    def test_unusable_target_exits_two(self, tmp_path: Path) -> None:
        assert main(['audit', str(tmp_path / 'nope')]) == EXIT_UNUSABLE

    def test_json_is_parseable(
        self,
        clean_python_repo: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        main(['audit', str(clean_python_repo), '--json'])
        payload = json.loads(capsys.readouterr().out)
        assert {check['number'] for check in payload['checks']} >= {1, 2, 3}

    def test_summary_counts_each_status(
        self,
        clean_python_repo: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        main(['audit', str(clean_python_repo)])
        assert 'passed' in capsys.readouterr().out


@pytest.fixture
def default_target(clean_python_repo: Path) -> Path:
    return clean_python_repo


class TestDefaultCommand:
    """`repo-audit <dir>` must work without naming the only subcommand."""

    def test_bare_invocation_audits_the_current_directory(
        self,
        default_target: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(default_target)
        assert main([]) == EXIT_OK
        assert 'passed' in capsys.readouterr().out

    def test_version_still_reaches_the_parser(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--version'])
        assert exit_info.value.code == EXIT_OK

    def test_help_still_reaches_the_parser(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['--help'])
        assert exit_info.value.code == EXIT_OK

    def test_explicit_subcommand_still_works(
        self,
        default_target: Path,
    ) -> None:
        assert main(['audit', str(default_target)]) == EXIT_OK

    def test_directory_without_subcommand(
        self,
        default_target: Path,
    ) -> None:
        assert main([str(default_target)]) == EXIT_OK

    def test_flag_without_subcommand(
        self,
        default_target: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main([str(default_target), '--json']) == EXIT_OK
        assert json.loads(capsys.readouterr().out)['checks']

    def test_unknown_flag_is_still_an_error(
        self,
        default_target: Path,
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([str(default_target), '--nope'])
        assert exit_info.value.code != EXIT_OK


class TestUntestedModules:
    def test_module_with_a_sibling_test_is_covered(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'pkg/thing.py', 'def go() -> None: ...\n')
        write(tmp_path, 'pkg/test_thing.py', 'def test_go() -> None: ...\n')
        assert untested_modules(tmp_path) == []

    def test_module_tested_from_a_tests_dir_is_covered(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'src/thing.py', 'def go() -> None: ...\n')
        write(tmp_path, 'tests/test_thing.py', 'def test_go() -> None: ...\n')
        assert untested_modules(tmp_path) == []

    def test_module_covered_by_a_test_that_imports_it(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'src/thing_cli.py', 'def go() -> None: ...\n')
        write(
            tmp_path,
            'src/test_thing.py',
            'from thing_cli import go\n\ndef test_go() -> None: ...\n',
        )
        assert untested_modules(tmp_path) == []

    def test_untested_module_is_reported(self, tmp_path: Path) -> None:
        write(tmp_path, 'src/thing.py', 'def go() -> None: ...\n')
        assert untested_modules(tmp_path) == ['src/thing.py']

    @pytest.mark.parametrize(
        'name',
        ['__init__.py', 'conftest.py', 'setup.py', 'test_thing.py'],
    )
    def test_non_logic_files_are_exempt(
        self,
        tmp_path: Path,
        name: str,
    ) -> None:
        write(tmp_path, f'src/{name}', 'x = 1\n')
        assert untested_modules(tmp_path) == []

    def test_constants_only_module_is_exempt(self, tmp_path: Path) -> None:
        write(tmp_path, 'src/conf.py', 'NAME = "x"\nPORT = 8080\n')
        assert untested_modules(tmp_path) == []

    def test_typescript_module_is_covered_by_spec(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'src/thing.ts', 'export function go() {}\n')
        write(tmp_path, 'src/thing.spec.ts', 'it("go", () => {});\n')
        assert untested_modules(tmp_path) == []


class TestCheckTests:
    def test_na_without_a_runner(self, tmp_path: Path) -> None:
        write(tmp_path, 'notes.md', 'x')
        result = check_tests(tmp_path, detect_stack(tmp_path), run=False)
        assert result.status is Status.NA

    def test_manual_when_not_running(self, tmp_path: Path) -> None:
        write(tmp_path, 'src/thing.py', 'def go() -> None: ...\n')
        write(tmp_path, 'tests/test_thing.py', 'def test_go() -> None: ...\n')
        result = check_tests(tmp_path, detect_stack(tmp_path), run=False)
        assert result.status is Status.MANUAL
        assert 'pytest' in result.detail

    def test_untested_modules_fail_even_without_running(
        self,
        tmp_path: Path,
    ) -> None:
        write(tmp_path, 'src/thing.py', 'def go() -> None: ...\n')
        write(tmp_path, 'tests/test_other.py', 'def test_x() -> None: ...\n')
        result = check_tests(tmp_path, detect_stack(tmp_path), run=False)
        assert result.status is Status.FAIL
        assert 'src/thing.py' in result.detail


class TestCheckWorkflows:
    def test_na_without_workflows(self, tmp_path: Path) -> None:
        result = check_workflows(tmp_path, run=False)
        assert result.status is Status.NA

    def test_fails_when_not_wired_in(self, tmp_path: Path) -> None:
        write(tmp_path, '.github/workflows/ci.yml', 'on: push\njobs: {}\n')
        result = check_workflows(tmp_path, run=False)
        assert result.status is Status.FAIL
        assert 'zizmor' in result.detail

    def test_manual_when_wired_into_precommit(self, tmp_path: Path) -> None:
        write(tmp_path, '.github/workflows/ci.yml', 'on: push\njobs: {}\n')
        write(
            tmp_path,
            '.pre-commit-config.yaml',
            'repos:\n  - hooks:\n      - id: zizmor\n',
        )
        result = check_workflows(tmp_path, run=False)
        assert result.status is Status.MANUAL

    def test_manual_when_wired_into_a_workflow_itself(
        self,
        tmp_path: Path,
    ) -> None:
        write(
            tmp_path,
            '.github/workflows/zizmor.yml',
            'on: push\njobs:\n  audit:\n'
            '    steps:\n      - run: uvx zizmor .\n',
        )
        result = check_workflows(tmp_path, run=False)
        assert result.status is Status.MANUAL

    def test_only_yaml_files_count_as_workflows(self, tmp_path: Path) -> None:
        write(tmp_path, '.github/workflows/README.md', 'not a workflow\n')
        result = check_workflows(tmp_path, run=False)
        assert result.status is Status.NA


class TestFindEntrypoints:
    def test_finds_pyproject_scripts(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            'pyproject.toml',
            '[project.scripts]\nmine = "pkg:main"\n',
        )
        assert 'mine' in find_entrypoints(tmp_path)

    def test_finds_package_json_bin(self, tmp_path: Path) -> None:
        write(tmp_path, 'package.json', '{"bin": {"mine": "./cli.js"}}')
        assert 'mine' in find_entrypoints(tmp_path)

    def test_finds_executable_scripts(self, tmp_path: Path) -> None:
        path = write(tmp_path, 'scripts/mine', '#!/bin/sh\n')
        path.chmod(0o755)
        assert 'mine' in find_entrypoints(tmp_path)

    def test_ignores_non_executable_scripts(self, tmp_path: Path) -> None:
        write(tmp_path, 'scripts/mine', '#!/bin/sh\n')
        assert find_entrypoints(tmp_path) == {}

    def test_ignores_test_files(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            'scripts/test_mine.py',
            '#!/usr/bin/env python3\n',
        )
        path.chmod(0o755)
        assert find_entrypoints(tmp_path) == {}


class TestCheckEntrypoints:
    def test_na_without_entrypoints(self, tmp_path: Path) -> None:
        assert check_entrypoints(tmp_path).status is Status.NA

    def test_entrypoints_are_listed_not_run(self, tmp_path: Path) -> None:
        canary = tmp_path / 'ran'
        path = write(
            tmp_path,
            'scripts/mine',
            f'#!/bin/sh\ntouch {canary}\n',
        )
        path.chmod(0o755)
        result = check_entrypoints(tmp_path)
        assert result.status is Status.MANUAL
        assert 'mine' in result.detail
        assert not canary.exists()


class TestReferencedPaths:
    def test_extracts_backticked_paths(self) -> None:
        found = referenced_paths('see `src/app.py` and `docs/x.md` for more')
        assert found == {'src/app.py', 'docs/x.md'}

    def test_ignores_prose_and_commands(self) -> None:
        assert referenced_paths('run `pytest -q` then `ls`') == set()

    def test_ignores_urls(self) -> None:
        assert referenced_paths('see `https://x.test/a.py`') == set()

    @pytest.mark.parametrize(
        'token',
        [
            '/code-review',
            'origin/develop',
            'pytest.mark.parametrize',
            'skills/x/',
            '--json',
        ],
    )
    def test_ignores_things_that_are_not_files(self, token: str) -> None:
        assert referenced_paths(f'see `{token}` here') == set()

    def test_bare_filenames_in_prose_are_not_paths(self) -> None:
        assert referenced_paths('add a `__init__.py` and a `.tar.gz`') == set()

    def test_keeps_a_dotfile_directory_path(self) -> None:
        assert referenced_paths('see `.claude/CLAUDE.md`') == {
            '.claude/CLAUDE.md',
        }


class TestDocsFreshness:
    def test_na_without_docs(self, tmp_path: Path) -> None:
        assert check_docs_freshness(tmp_path).status is Status.NA

    def test_live_reference_passes(self, tmp_path: Path) -> None:
        write(tmp_path, 'src/app.py', 'x = 1\n')
        write(tmp_path, 'CLAUDE.md', 'The entry point is `src/app.py`.\n')
        assert check_docs_freshness(tmp_path).status is Status.PASS

    def test_dangling_reference_fails(self, tmp_path: Path) -> None:
        write(tmp_path, 'CLAUDE.md', 'The entry point is `src/gone.py`.\n')
        result = check_docs_freshness(tmp_path)
        assert result.status is Status.FAIL
        assert 'src/gone.py' in result.detail

    def test_skill_md_is_checked_too(self, tmp_path: Path) -> None:
        write(tmp_path, 'skills/x/SKILL.md', 'See `skills/x/nope.py`.\n')
        result = check_docs_freshness(tmp_path)
        assert result.status is Status.FAIL
        assert 'nope.py' in result.detail
