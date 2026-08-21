"""Parser tests for the dynamodb-cost-audit CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dynamodb_cost_audit_cli import (
    ACCESS_PATTERNS,
    BACKUPS,
    CAPACITY_MODE,
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_UNUSABLE,
    ITEM_SIZE,
    SECONDARY_INDEXES,
    STORAGE,
    STREAMS,
    TABLE_CLASS,
    Index,
    Status,
    Table,
    as_json,
    load_iac,
    main,
    parse_cloudformation,
    parse_hcl,
    parse_terraform_json,
    render,
    run_checks,
)

CFN_PROVISIONED = {
    'Resources': {
        'OrdersTable': {
            'Type': 'AWS::DynamoDB::Table',
            'Properties': {
                'TableName': 'orders',
                'KeySchema': [
                    {'AttributeName': 'PK', 'KeyType': 'HASH'},
                    {'AttributeName': 'SK', 'KeyType': 'RANGE'},
                ],
                'ProvisionedThroughput': {
                    'ReadCapacityUnits': 100,
                    'WriteCapacityUnits': 50,
                },
                'GlobalSecondaryIndexes': [
                    {
                        'IndexName': 'GSI1',
                        'KeySchema': [
                            {'AttributeName': 'GSI1PK', 'KeyType': 'HASH'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 10,
                            'WriteCapacityUnits': 50,
                        },
                    },
                    {
                        'IndexName': 'GSI2',
                        'KeySchema': [
                            {'AttributeName': 'status', 'KeyType': 'HASH'},
                        ],
                        'Projection': {
                            'ProjectionType': 'INCLUDE',
                            'NonKeyAttributes': ['total'],
                        },
                    },
                ],
            },
        },
    },
}

CFN_ON_DEMAND = {
    'Resources': {
        'EventsTable': {
            'Type': 'AWS::DynamoDB::Table',
            'Properties': {
                'BillingMode': 'PAY_PER_REQUEST',
                'TableClass': 'STANDARD_INFREQUENT_ACCESS',
                'TimeToLiveSpecification': {
                    'AttributeName': 'expiresAt',
                    'Enabled': True,
                },
                'PointInTimeRecoverySpecification': {
                    'PointInTimeRecoveryEnabled': True,
                },
                'StreamSpecification': {
                    'StreamViewType': 'NEW_AND_OLD_IMAGES',
                },
                'LocalSecondaryIndexes': [
                    {
                        'IndexName': 'LSI1',
                        'KeySchema': [
                            {'AttributeName': 'createdAt', 'KeyType': 'RANGE'},
                        ],
                        'Projection': {'ProjectionType': 'KEYS_ONLY'},
                    },
                ],
            },
        },
    },
}


ORDERS_CAPACITY = (100, 50)
CFN_GSI1_CAPACITY = (10, 50)
TF_GSI1_CAPACITY = (5, 50)


def only(tables: list[Table]) -> Table:
    assert [table.name for table in tables] == [tables[0].name], tables
    return tables[0]


def test_cloudformation_provisioned_table() -> None:
    table = only(parse_cloudformation(CFN_PROVISIONED, 'template.json'))

    assert table.name == 'orders'
    assert table.logical_id == 'OrdersTable'
    assert table.billing_mode == 'PROVISIONED'
    assert (table.read_capacity, table.write_capacity) == ORDERS_CAPACITY
    assert table.key_attributes == ('PK', 'SK')
    assert [index.name for index in table.global_secondary_indexes] == [
        'GSI1',
        'GSI2',
    ]
    gsi1 = table.global_secondary_indexes[0]
    assert gsi1.projection_type == 'ALL'
    assert (gsi1.read_capacity, gsi1.write_capacity) == CFN_GSI1_CAPACITY
    assert table.global_secondary_indexes[1].projected_attributes == ('total',)
    assert not table.ttl_enabled
    assert not table.point_in_time_recovery
    assert table.stream_view_type is None
    assert not table.autoscaled


def test_cloudformation_on_demand_table() -> None:
    table = only(parse_cloudformation(CFN_ON_DEMAND, 'template.json'))

    assert table.name == 'EventsTable'
    assert table.billing_mode == 'PAY_PER_REQUEST'
    assert table.table_class == 'STANDARD_INFREQUENT_ACCESS'
    assert table.ttl_enabled
    assert table.point_in_time_recovery
    assert table.stream_view_type == 'NEW_AND_OLD_IMAGES'
    assert [index.name for index in table.local_secondary_indexes] == ['LSI1']
    assert table.read_capacity is None


@pytest.mark.parametrize(
    ('properties', 'expected_name'),
    [
        ({'TableName': {'Fn::Sub': '${AWS::StackName}-t'}}, 'Widgets'),
        ({'TableName': {'Ref': 'NameParam'}}, 'Widgets'),
        ({}, 'Widgets'),
        ({'TableName': 'widgets'}, 'widgets'),
    ],
)
def test_table_name_falls_back_to_logical_id(
    properties: dict[str, object],
    expected_name: str,
) -> None:
    document = {
        'Resources': {
            'Widgets': {
                'Type': 'AWS::DynamoDB::Table',
                'Properties': properties,
            },
        },
    }

    assert only(parse_cloudformation(document, 'x.json')).name == expected_name


def test_unresolvable_capacity_reads_as_unknown() -> None:
    document = {
        'Resources': {
            'Widgets': {
                'Type': 'AWS::DynamoDB::Table',
                'Properties': {
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': {'Ref': 'ReadUnits'},
                        'WriteCapacityUnits': '25',
                    },
                },
            },
        },
    }

    table = only(parse_cloudformation(document, 'x.json'))
    assert (table.read_capacity, table.write_capacity) == (None, 25)


@pytest.mark.parametrize(
    'resource_id',
    [
        'table/orders',
        {'Fn::Sub': 'table/${OrdersTable}'},
        {'Fn::Join': ['', ['table/', {'Ref': 'OrdersTable'}]]},
    ],
)
def test_autoscaling_target_marks_table_autoscaled(
    resource_id: object,
) -> None:
    document = json.loads(json.dumps(CFN_PROVISIONED))
    document['Resources']['Scaling'] = {
        'Type': 'AWS::ApplicationAutoScaling::ScalableTarget',
        'Properties': {
            'ResourceId': resource_id,
            'ScalableDimension': 'dynamodb:table:ReadCapacityUnits',
        },
    }

    assert only(parse_cloudformation(document, 'x.json')).autoscaled


def test_non_dynamodb_resources_are_ignored() -> None:
    document = {
        'Resources': {
            'Bucket': {'Type': 'AWS::S3::Bucket', 'Properties': {}},
        },
    }

    assert parse_cloudformation(document, 'x.json') == []


TF_STATE = {
    'values': {
        'root_module': {
            'resources': [
                {
                    'type': 'aws_dynamodb_table',
                    'name': 'orders',
                    'values': {
                        'name': 'orders',
                        'billing_mode': 'PROVISIONED',
                        'read_capacity': 100,
                        'write_capacity': 50,
                        'hash_key': 'PK',
                        'range_key': 'SK',
                        'table_class': 'STANDARD',
                        'stream_enabled': True,
                        'stream_view_type': 'KEYS_ONLY',
                        'ttl': [{'enabled': True, 'attribute_name': 'exp'}],
                        'point_in_time_recovery': [{'enabled': False}],
                        'global_secondary_index': [
                            {
                                'name': 'GSI1',
                                'hash_key': 'GSI1PK',
                                'projection_type': 'ALL',
                                'read_capacity': 5,
                                'write_capacity': 50,
                            },
                        ],
                    },
                },
                {'type': 'aws_s3_bucket', 'name': 'b', 'values': {}},
            ],
            'child_modules': [
                {
                    'resources': [
                        {
                            'type': 'aws_dynamodb_table',
                            'name': 'events',
                            'values': {
                                'name': 'events',
                                'billing_mode': 'PAY_PER_REQUEST',
                            },
                        },
                    ],
                },
            ],
        },
    },
}


def test_terraform_state_json() -> None:
    tables = parse_terraform_json(TF_STATE, 'state.json')

    assert [table.name for table in tables] == ['orders', 'events']
    orders, events = tables
    assert orders.billing_mode == 'PROVISIONED'
    assert (orders.read_capacity, orders.write_capacity) == ORDERS_CAPACITY
    assert orders.key_attributes == ('PK', 'SK')
    assert orders.ttl_enabled
    assert not orders.point_in_time_recovery
    assert orders.stream_view_type == 'KEYS_ONLY'
    assert orders.global_secondary_indexes[0].projection_type == 'ALL'
    assert events.billing_mode == 'PAY_PER_REQUEST'


def test_terraform_plan_json_uses_planned_values() -> None:
    plan = {'planned_values': TF_STATE['values']}

    assert [table.name for table in parse_terraform_json(plan, 'p.json')] == [
        'orders',
        'events',
    ]


def test_terraform_stream_disabled_reports_no_view_type() -> None:
    document = {
        'values': {
            'root_module': {
                'resources': [
                    {
                        'type': 'aws_dynamodb_table',
                        'name': 't',
                        'values': {
                            'name': 't',
                            'stream_enabled': False,
                            'stream_view_type': 'NEW_IMAGE',
                        },
                    },
                ],
            },
        },
    }

    assert (
        only(parse_terraform_json(document, 'x.json')).stream_view_type is None
    )


def test_terraform_autoscaling_target() -> None:
    document = json.loads(json.dumps(TF_STATE))
    document['values']['root_module']['resources'].append(
        {
            'type': 'aws_appautoscaling_target',
            'name': 'orders_read',
            'values': {
                'resource_id': 'table/orders',
                'scalable_dimension': 'dynamodb:table:ReadCapacityUnits',
            },
        },
    )

    tables = {
        table.name: table for table in parse_terraform_json(document, 'x')
    }
    assert tables['orders'].autoscaled
    assert not tables['events'].autoscaled


HCL = """
# The orders table.
resource "aws_dynamodb_table" "orders" {
  name           = "orders"
  billing_mode   = "PROVISIONED"
  read_capacity  = 100
  write_capacity = 50
  hash_key       = "PK"
  range_key      = "SK"  // composite
  table_class    = "STANDARD"
  stream_enabled = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
    read_capacity   = 5
    write_capacity  = 50
  }

  global_secondary_index {
    name               = "GSI2"
    hash_key           = "status"
    projection_type    = "INCLUDE"
    non_key_attributes = ["total", "customer"]
  }

  local_secondary_index {
    name            = "LSI1"
    range_key       = "createdAt"
    projection_type = "KEYS_ONLY"
  }

  tags = {
    Name = "not-a-table"
  }
}

resource "aws_s3_bucket" "assets" {
  bucket = "assets"
}
"""


def test_hcl_table() -> None:
    table = only(parse_hcl(HCL, 'main.tf'))

    assert table.name == 'orders'
    assert table.billing_mode == 'PROVISIONED'
    assert (table.read_capacity, table.write_capacity) == ORDERS_CAPACITY
    assert table.key_attributes == ('PK', 'SK')
    assert table.ttl_enabled
    assert table.point_in_time_recovery
    assert table.stream_view_type == 'NEW_AND_OLD_IMAGES'
    assert table.table_class == 'STANDARD'
    assert [index.name for index in table.global_secondary_indexes] == [
        'GSI1',
        'GSI2',
    ]
    assert table.global_secondary_indexes[1].projected_attributes == (
        'total',
        'customer',
    )
    assert [index.name for index in table.local_secondary_indexes] == ['LSI1']


def test_hcl_defaults_to_provisioned_when_billing_mode_absent() -> None:
    text = 'resource "aws_dynamodb_table" "t" {\n  name = "t"\n}\n'

    assert only(parse_hcl(text, 'main.tf')).billing_mode == 'PROVISIONED'


def test_hcl_autoscaling_target() -> None:
    text = (
        HCL
        + """
resource "aws_appautoscaling_target" "orders_read" {
  resource_id        = "table/${aws_dynamodb_table.orders.name}"
  scalable_dimension = "dynamodb:table:ReadCapacityUnits"
}
"""
    )

    assert only(parse_hcl(text, 'main.tf')).autoscaled


def test_hcl_ignores_interpolated_capacity() -> None:
    text = (
        'resource "aws_dynamodb_table" "t" {\n'
        '  name          = "t"\n'
        '  read_capacity = var.read_capacity\n'
        '}\n'
    )

    assert only(parse_hcl(text, 'main.tf')).read_capacity is None


def test_load_iac_walks_a_directory(tmp_path: Path) -> None:
    (tmp_path / 'cdk.out').mkdir()
    (tmp_path / 'cdk.out' / 'Stack.template.json').write_text(
        json.dumps(CFN_PROVISIONED),
    )
    (tmp_path / 'main.tf').write_text(HCL)
    (tmp_path / 'package.json').write_text('{"name": "app"}')
    (tmp_path / '.terraform').mkdir()
    (tmp_path / '.terraform' / 'x.tf').write_text(HCL)

    tables = load_iac(tmp_path)

    assert sorted(table.name for table in tables) == ['orders', 'orders']
    assert {Path(table.source).name for table in tables} == {
        'Stack.template.json',
        'main.tf',
    }


def test_load_iac_on_a_single_file(tmp_path: Path) -> None:
    path = tmp_path / 'template.json'
    path.write_text(json.dumps(CFN_ON_DEMAND))

    assert [table.name for table in load_iac(path)] == ['EventsTable']


def test_load_iac_yaml(tmp_path: Path) -> None:
    pytest.importorskip('yaml')
    path = tmp_path / 'template.yaml'
    path.write_text(
        'Resources:\n'
        '  Orders:\n'
        '    Type: AWS::DynamoDB::Table\n'
        '    Properties:\n'
        '      TableName: !Ref NameParam\n'
        '      BillingMode: PAY_PER_REQUEST\n',
    )

    table = only(load_iac(path))
    assert table.name == 'Orders'
    assert table.billing_mode == 'PAY_PER_REQUEST'


def audit_statuses(tables: list[Table]) -> dict[int, set[Status]]:
    """Section number -> the statuses that section reported."""
    grouped: dict[int, set[Status]] = {}
    for result in run_checks(tables):
        grouped.setdefault(result.number, set()).add(result.status)
    return grouped


def details_for(tables: list[Table], number: int) -> str:
    return '\n'.join(
        result.detail
        for result in run_checks(tables)
        if result.number == number
    )


def table(**overrides: object) -> Table:
    """A minimally-specified on-demand table, for one-finding tests."""
    defaults: dict[str, object] = {
        'name': 'orders',
        'source': 'main.tf',
        'billing_mode': 'PAY_PER_REQUEST',
        'ttl_enabled': True,
        'point_in_time_recovery': True,
    }
    return Table(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_a_clean_table_reports_no_findings() -> None:
    results = run_checks([table()])

    assert [result for result in results if result.status is Status.FAIL] == []


@pytest.mark.parametrize(
    ('overrides', 'number', 'expected'),
    [
        (
            {'billing_mode': 'PROVISIONED', 'read_capacity': 100},
            CAPACITY_MODE,
            'autoscaling',
        ),
        ({'ttl_enabled': False}, STORAGE, 'backfill'),
        ({'point_in_time_recovery': False}, BACKUPS, 'PITR'),
        (
            {
                'global_secondary_indexes': (
                    Index(name='GSI1', projection_type='ALL'),
                ),
            },
            SECONDARY_INDEXES,
            'GSI1',
        ),
        (
            {
                'global_secondary_indexes': (
                    Index(
                        name='GSI1',
                        projection_type='KEYS_ONLY',
                        key_attributes=('GSI1PK', 'GSI1SK'),
                    ),
                ),
            },
            SECONDARY_INDEXES,
            'GSI1PK',
        ),
    ],
)
def test_findings_land_in_the_right_section(
    overrides: dict[str, object],
    number: int,
    expected: str,
) -> None:
    tables = [table(**overrides)]

    assert Status.FAIL in audit_statuses(tables)[number]
    assert expected in details_for(tables, number)


def test_provisioned_with_autoscaling_is_manual_not_a_failure() -> None:
    tables = [
        table(
            billing_mode='PROVISIONED',
            read_capacity=100,
            write_capacity=50,
            autoscaled=True,
        ),
    ]

    statuses = audit_statuses(tables)[CAPACITY_MODE]
    assert Status.FAIL not in statuses
    assert Status.MANUAL in statuses
    assert '30%' in details_for(tables, CAPACITY_MODE)


def test_unresolved_capacity_does_not_become_a_finding() -> None:
    """A bare `.tf` checkout resolves almost nothing -- stay quiet."""
    tables = [table(billing_mode=None)]

    assert Status.FAIL not in audit_statuses(tables)[CAPACITY_MODE]


def test_keys_only_projection_passes() -> None:
    tables = [
        table(
            global_secondary_indexes=(
                Index(name='byStatus', projection_type='KEYS_ONLY'),
            ),
        ),
    ]

    assert Status.FAIL not in audit_statuses(tables)[SECONDARY_INDEXES]
    assert 'byStatus' in details_for(tables, SECONDARY_INDEXES)


def test_no_indexes_reports_not_applicable() -> None:
    assert audit_statuses([table()])[SECONDARY_INDEXES] == {Status.NA}


def test_local_secondary_index_is_reported_as_manual() -> None:
    tables = [
        table(
            local_secondary_indexes=(
                Index(name='LSI1', projection_type='KEYS_ONLY'),
            ),
        ),
    ]

    assert Status.MANUAL in audit_statuses(tables)[SECONDARY_INDEXES]
    assert 'LSI1' in details_for(tables, SECONDARY_INDEXES)


@pytest.mark.parametrize(
    ('table_class', 'expected'),
    [
        ('STANDARD', Status.MANUAL),
        (None, Status.MANUAL),
        ('STANDARD_INFREQUENT_ACCESS', Status.PASS),
    ],
)
def test_table_class(table_class: str | None, expected: Status) -> None:
    tables = [table(table_class=table_class)]

    assert audit_statuses(tables)[TABLE_CLASS] == {expected}


@pytest.mark.parametrize(
    ('view_type', 'expected'),
    [
        ('NEW_AND_OLD_IMAGES', Status.MANUAL),
        ('KEYS_ONLY', Status.PASS),
        (None, Status.NA),
    ],
)
def test_streams(view_type: str | None, expected: Status) -> None:
    tables = [table(stream_view_type=view_type)]

    assert audit_statuses(tables)[STREAMS] == {expected}


def test_every_table_is_named_in_a_finding() -> None:
    tables = [
        table(name='orders', ttl_enabled=False),
        table(name='events', ttl_enabled=False),
    ]

    detail = details_for(tables, STORAGE)
    assert 'orders' in detail
    assert 'events' in detail


def test_credentials_only_checks_are_reported_not_skipped() -> None:
    """Tier 1 cannot see item size or index reads -- say so."""
    statuses = audit_statuses([table()])

    assert statuses[ITEM_SIZE] == {Status.MANUAL}
    assert statuses[ACCESS_PATTERNS] == {Status.MANUAL}


def test_render_groups_by_status() -> None:
    output = render(run_checks([table(ttl_enabled=False)]))

    assert output.index('FAIL') < output.index('MANUAL')
    assert output.endswith('\n')


def test_as_json_round_trips() -> None:
    payload = json.loads(as_json(run_checks([table()])))

    assert {check['number'] for check in payload['checks']} == {
        ITEM_SIZE,
        ACCESS_PATTERNS,
        SECONDARY_INDEXES,
        CAPACITY_MODE,
        TABLE_CLASS,
        STORAGE,
        BACKUPS,
        STREAMS,
    }


def test_main_reports_findings_and_exits_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / 'template.json').write_text(json.dumps(CFN_PROVISIONED))

    assert main([str(tmp_path)]) == EXIT_FINDINGS
    assert 'GSI1' in capsys.readouterr().out


def test_main_json_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / 'template.json').write_text(json.dumps(CFN_ON_DEMAND))

    main([str(tmp_path), '--json'])

    assert json.loads(capsys.readouterr().out)['tables'] == ['EventsTable']


def test_main_without_any_tables_is_unusable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(tmp_path)]) == EXIT_UNUSABLE
    assert 'cdk.out' in capsys.readouterr().err


def test_main_on_a_missing_path_is_unusable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(tmp_path / 'nope')]) == EXIT_UNUSABLE
    assert 'does not exist' in capsys.readouterr().err


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['--version'])

    assert exit_info.value.code == EXIT_OK
    assert 'dynamodb-cost-audit' in capsys.readouterr().out


def test_bare_invocation_audits_the_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No required positional -- a bare run must not be an argument error."""
    (tmp_path / 'main.tf').write_text(HCL)
    monkeypatch.chdir(tmp_path)

    assert main([]) == EXIT_FINDINGS
    assert 'orders' in capsys.readouterr().out


def test_render_prints_each_section_header_once() -> None:
    tables = [
        table(
            global_secondary_indexes=(
                Index(
                    name='GSI1',
                    projection_type='ALL',
                    key_attributes=('GSI1PK',),
                ),
            ),
        ),
    ]

    output = render(run_checks(tables))

    # Once under FAIL, once under MANUAL -- not once per finding.
    assert output.count(f'{SECONDARY_INDEXES}. Secondary indexes') == len(
        {Status.FAIL, Status.MANUAL},
    )
