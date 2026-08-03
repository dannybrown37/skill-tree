"""Regression tests for scripts/dev_link.sh."""

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / 'dev_link.sh'
REPO_ROOT = SCRIPT.parent.parent
PLUGIN_ID = 'skill-tree@skill-tree'


@pytest.fixture
def install_path(tmp_path: Path) -> Path:
    """A fake installed plugin directory, as the cache would hold it."""
    path = tmp_path / 'cache' / 'skill-tree' / 'skill-tree' / '0.2.1'
    path.mkdir(parents=True)
    (path / 'marker').write_text('real install')
    return path


@pytest.fixture
def record(tmp_path: Path, install_path: Path) -> Path:
    path = tmp_path / 'installed_plugins.json'
    path.write_text(
        json.dumps(
            {
                'version': 2,
                'plugins': {
                    PLUGIN_ID: [{'installPath': str(install_path)}],
                },
            },
        ),
    )
    return path


def run(
    record: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ['bash', str(SCRIPT), *args],  # noqa: S607
        capture_output=True,
        text=True,
        env={
            'INSTALLED_PLUGINS': str(record),
            'PLUGIN_ID': PLUGIN_ID,
            'PATH': '/usr/bin:/bin',
            'HOME': str(record.parent),
        },
        check=False,
    )


class TestOn:
    def test_links_the_install_path_at_the_checkout(
        self,
        record: Path,
        install_path: Path,
    ) -> None:
        result = run(record, '--on')

        assert result.returncode == 0
        assert install_path.is_symlink()
        assert install_path.readlink() == REPO_ROOT

    def test_backs_up_rather_than_deletes_the_real_install(
        self,
        record: Path,
        install_path: Path,
    ) -> None:
        run(record, '--on')

        backup = install_path.with_name(f'{install_path.name}.real')
        assert (backup / 'marker').read_text() == 'real install'

    def test_is_idempotent(self, record: Path, install_path: Path) -> None:
        run(record, '--on')
        result = run(record, '--on')

        assert result.returncode == 0
        assert 'Already on' in result.stdout
        assert install_path.readlink() == REPO_ROOT

    def test_keeps_the_original_backup_when_rerun_after_a_reinstall(
        self,
        record: Path,
        install_path: Path,
    ) -> None:
        """A `/plugin install` while linked recreates the directory."""
        run(record, '--on')
        install_path.unlink()
        install_path.mkdir()
        (install_path / 'marker').write_text('redownloaded')

        run(record, '--on')

        backup = install_path.with_name(f'{install_path.name}.real')
        assert (backup / 'marker').read_text() == 'real install'

    def test_refuses_to_clobber_a_link_pointing_elsewhere(
        self,
        record: Path,
        install_path: Path,
        tmp_path: Path,
    ) -> None:
        other = tmp_path / 'other-checkout'
        other.mkdir()
        (install_path / 'marker').unlink()
        install_path.rmdir()
        install_path.symlink_to(other)

        result = run(record, '--on')

        assert result.returncode == 1
        assert 'already links elsewhere' in result.stderr
        assert install_path.readlink() == other

    def test_works_when_nothing_is_installed_at_the_path(
        self,
        record: Path,
        install_path: Path,
    ) -> None:
        (install_path / 'marker').unlink()
        install_path.rmdir()

        result = run(record, '--on')

        assert result.returncode == 0
        assert install_path.readlink() == REPO_ROOT


class TestOff:
    def test_restores_the_real_install(
        self,
        record: Path,
        install_path: Path,
    ) -> None:
        run(record, '--on')

        result = run(record, '--off')

        assert result.returncode == 0
        assert not install_path.is_symlink()
        assert (install_path / 'marker').read_text() == 'real install'

    def test_is_idempotent(self, record: Path, install_path: Path) -> None:
        result = run(record, '--off')

        assert result.returncode == 0
        assert 'Already off' in result.stdout
        assert (install_path / 'marker').read_text() == 'real install'

    def test_points_at_reinstall_when_there_is_no_backup(
        self,
        record: Path,
        install_path: Path,
    ) -> None:
        run(record, '--on')
        backup = install_path.with_name(f'{install_path.name}.real')
        (backup / 'marker').unlink()
        backup.rmdir()

        result = run(record, '--off')

        assert not install_path.exists()
        assert f'/plugin install {PLUGIN_ID}' in result.stderr


class TestStatus:
    def test_reports_off_for_a_real_install(
        self,
        record: Path,
    ) -> None:
        result = run(record, '--status')

        assert 'Dev mode OFF' in result.stdout

    def test_reports_on_and_the_target_once_linked(
        self,
        record: Path,
    ) -> None:
        run(record, '--on')

        result = run(record, '--status')

        assert 'Dev mode ON' in result.stdout
        assert str(REPO_ROOT) in result.stdout

    def test_defaults_to_status_with_no_arguments(
        self,
        record: Path,
    ) -> None:
        result = run(record)

        assert result.returncode == 0
        assert 'Dev mode' in result.stdout


class TestErrors:
    def test_unknown_option_exits_nonzero(self, record: Path) -> None:
        result = run(record, '--nope')

        assert result.returncode == 1
        assert 'Unknown option' in result.stderr

    def test_missing_install_record_is_a_clear_error(
        self,
        tmp_path: Path,
    ) -> None:
        result = run(tmp_path / 'absent.json', '--status')

        assert result.returncode == 1
        assert 'No plugin install record' in result.stderr

    def test_plugin_absent_from_the_record_is_a_clear_error(
        self,
        tmp_path: Path,
    ) -> None:
        record = tmp_path / 'installed_plugins.json'
        record.write_text(json.dumps({'version': 2, 'plugins': {}}))

        result = run(record, '--status')

        assert result.returncode == 1
        assert 'not installed' in result.stderr
