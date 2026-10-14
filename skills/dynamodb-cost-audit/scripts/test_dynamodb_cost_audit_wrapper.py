"""The wrapper is a real executable the dispatcher can find and run."""

import os
import subprocess
from pathlib import Path

WRAPPER = Path(__file__).parent / 'dynamodb-cost-audit'

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_UNUSABLE = 2

TERRAFORM = """\
resource "aws_dynamodb_table" "orders" {
  name         = "orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"

  ttl {
    attribute_name = "expiresAt"
  }

  point_in_time_recovery {
    enabled = true
  }
}
"""

CLOUDFORMATION_YAML = """\
Resources:
  Orders:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: !Ref NameParam
      BillingMode: PAY_PER_REQUEST
"""


def run(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(WRAPPER), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def test_wrapper_is_executable() -> None:
    assert WRAPPER.stat().st_mode & 0o111


def test_version_exits_zero_with_no_config() -> None:
    result = run('--version')

    assert result.returncode == EXIT_OK
    assert result.stdout.startswith('dynamodb-cost-audit ')


def test_no_arguments_audits_the_current_directory(tmp_path: Path) -> None:
    (tmp_path / 'main.tf').write_text(TERRAFORM)

    result = run(cwd=tmp_path)

    assert result.returncode == EXIT_OK
    assert 'MANUAL' in result.stdout


def test_nothing_to_audit_exits_unusable(tmp_path: Path) -> None:
    result = run(str(tmp_path))

    assert result.returncode == EXIT_UNUSABLE
    assert 'cdk.out' in result.stderr


def test_yaml_templates_work_through_the_wrapper(tmp_path: Path) -> None:
    """The wrapper's whole job: reach PyYAML for CloudFormation YAML."""
    (tmp_path / 'template.yaml').write_text(CLOUDFORMATION_YAML)

    result = run(str(tmp_path))

    assert result.returncode == EXIT_FINDINGS
    assert 'Orders' in result.stdout


def test_uv_that_cannot_fetch_pyyaml_falls_back_to_python3(
    tmp_path: Path,
) -> None:
    """An offline uv must not take stdlib-only inputs down with it.

    In a sandbox, `uv run --with pyyaml` fails before the CLI starts, but
    Terraform and JSON need no PyYAML, so they must still audit.
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    fake_uv = bin_dir / 'uv'
    fake_uv.write_text(
        '#!/bin/sh\necho "error: Failed to fetch: pypi.org" >&2\nexit 2\n',
    )
    fake_uv.chmod(0o755)
    (tmp_path / 'main.tf').write_text(TERRAFORM)
    env = {**os.environ, 'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}'}

    result = run(str(tmp_path), env=env)

    assert result.returncode == EXIT_OK
    assert 'MANUAL' in result.stdout
