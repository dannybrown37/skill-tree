"""The wrapper is a real executable the dispatcher can find and run."""

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
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(WRAPPER), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
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
