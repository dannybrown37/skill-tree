#!/usr/bin/env python3
"""Deterministic half of the dynamodb-cost-audit checklist.

Tier 1 reads infrastructure-as-code and reports what is wrong *by
construction* -- billing mode, capacity, index projections, TTL, PITR,
streams, table class. No credentials, so it runs in CI and works on a
table that does not exist yet.

Two input shapes cover almost everything. CloudFormation-shaped JSON/YAML
gets CDK (`cdk.out/*.template.json`), SAM and Serverless Framework for
free, since all three synthesize to it. Terraform is read either from
`terraform show -json` output (exact, needs state) or straight from `.tf`
source (works on a bare checkout, and so is deliberately lenient about
anything it cannot resolve).

Whatever cannot be answered from a template -- item sizes, consumed
capacity, which indexes nobody reads -- is tier 2's job and needs metrics.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

CFN_TABLE_TYPES = frozenset({'AWS::DynamoDB::Table'})
CFN_SCALABLE_TARGET = 'AWS::ApplicationAutoScaling::ScalableTarget'
TF_TABLE_TYPE = 'aws_dynamodb_table'
TF_SCALABLE_TARGET = 'aws_appautoscaling_target'

DEFAULT_BILLING_MODE = 'PROVISIONED'

IAC_SUFFIXES = frozenset({'.json', '.yaml', '.yml', '.tf'})
SKIPPED_DIRECTORIES = frozenset(
    {'.git', '.terraform', 'node_modules', '__pycache__', '.venv'},
)


class DynamoCostAuditError(Exception):
    """The input can't be audited at all, as opposed to being bad."""


@dataclass(frozen=True)
class Index:
    """A secondary index, as a template describes it."""

    name: str
    projection_type: str | None = None
    projected_attributes: tuple[str, ...] = ()
    key_attributes: tuple[str, ...] = ()
    read_capacity: int | None = None
    write_capacity: int | None = None


@dataclass(frozen=True)
class Table:
    """One DynamoDB table's cost-relevant shape.

    Every field is optional-by-construction: `.tf` source and unresolved
    intrinsics both mean "the template didn't say", which is a different
    answer from "the template said no" and has to stay distinguishable.
    """

    name: str
    source: str
    logical_id: str | None = None
    billing_mode: str | None = None
    read_capacity: int | None = None
    write_capacity: int | None = None
    key_attributes: tuple[str, ...] = ()
    global_secondary_indexes: tuple[Index, ...] = ()
    local_secondary_indexes: tuple[Index, ...] = ()
    ttl_enabled: bool = False
    point_in_time_recovery: bool = False
    stream_view_type: str | None = None
    table_class: str | None = None
    autoscaled: bool = False


def as_dict(value: object) -> dict[str, object]:
    """A nested mapping, or an empty one when the key was absent."""
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def coerce_int(value: object) -> int | None:
    """An int the template actually stated, or None for a `Ref`/expression."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def coerce_bool(value: object) -> bool:
    """CloudFormation and HCL both spell booleans as strings sometimes."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == 'true'
    return False


def coerce_str(value: object) -> str | None:
    """A literal string, or None when it is an intrinsic/interpolation."""
    return value if isinstance(value, str) else None


def intrinsic_text(value: object) -> str:
    """Flatten a value to text so a name can be matched inside intrinsics.

    `ResourceId` is routinely a `Fn::Sub` or `Fn::Join` wrapping the
    table's logical id; the reference is in there, just not addressably.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return ' '.join(intrinsic_text(item) for item in value.values())
    if isinstance(value, list):
        return ' '.join(intrinsic_text(item) for item in value)
    return ''


def key_attributes(key_schema: object) -> tuple[str, ...]:
    """HASH first, then RANGE -- template order isn't guaranteed."""
    if not isinstance(key_schema, list):
        return ()
    by_type: dict[str, str] = {}
    for element in key_schema:
        if not isinstance(element, dict):
            continue
        name = coerce_str(element.get('AttributeName'))
        if name:
            by_type[str(element.get('KeyType', 'HASH'))] = name
    return tuple(
        by_type[key_type]
        for key_type in ('HASH', 'RANGE')
        if key_type in by_type
    )


def parse_cfn_index(raw: object) -> Index | None:
    if not isinstance(raw, dict):
        return None
    projection = as_dict(raw.get('Projection'))
    non_key = projection.get('NonKeyAttributes')
    throughput = as_dict(raw.get('ProvisionedThroughput'))
    return Index(
        name=coerce_str(raw.get('IndexName')) or '<unnamed>',
        projection_type=coerce_str(projection.get('ProjectionType')),
        projected_attributes=tuple(
            item for item in non_key if isinstance(item, str)
        )
        if isinstance(non_key, list)
        else (),
        key_attributes=key_attributes(raw.get('KeySchema')),
        read_capacity=coerce_int(throughput.get('ReadCapacityUnits')),
        write_capacity=coerce_int(throughput.get('WriteCapacityUnits')),
    )


def parse_cfn_indexes(raw: object) -> tuple[Index, ...]:
    if not isinstance(raw, list):
        return ()
    parsed = (parse_cfn_index(item) for item in raw)
    return tuple(index for index in parsed if index is not None)


def cfn_autoscaled_hints(resources: dict[str, object]) -> str:
    """Everything an autoscaling target says about what it scales."""
    hints = []
    for resource in resources.values():
        if not isinstance(resource, dict):
            continue
        if resource.get('Type') != CFN_SCALABLE_TARGET:
            continue
        properties = as_dict(resource.get('Properties'))
        if 'dynamodb' not in intrinsic_text(
            properties.get('ScalableDimension'),
        ):
            continue
        hints.append(intrinsic_text(properties.get('ResourceId')))
    return ' '.join(hints)


def parse_cloudformation(document: object, source: str) -> list[Table]:
    """Every `AWS::DynamoDB::Table` in a CloudFormation-shaped document."""
    if not isinstance(document, dict):
        return []
    resources = document.get('Resources')
    if not isinstance(resources, dict):
        return []

    hints = cfn_autoscaled_hints(resources)
    tables = []
    for logical_id, resource in resources.items():
        if not isinstance(resource, dict):
            continue
        if resource.get('Type') not in CFN_TABLE_TYPES:
            continue
        properties = as_dict(resource.get('Properties'))
        tables.append(
            cfn_table(str(logical_id), properties, source, hints),
        )
    return tables


def cfn_table(
    logical_id: str,
    properties: dict[str, object],
    source: str,
    autoscaling_hints: str,
) -> Table:
    throughput = as_dict(properties.get('ProvisionedThroughput'))
    ttl = as_dict(properties.get('TimeToLiveSpecification'))
    pitr = as_dict(properties.get('PointInTimeRecoverySpecification'))
    stream = as_dict(properties.get('StreamSpecification'))

    name = coerce_str(properties.get('TableName')) or logical_id
    return Table(
        name=name,
        source=source,
        logical_id=logical_id,
        billing_mode=coerce_str(properties.get('BillingMode'))
        or DEFAULT_BILLING_MODE,
        read_capacity=coerce_int(throughput.get('ReadCapacityUnits')),
        write_capacity=coerce_int(throughput.get('WriteCapacityUnits')),
        key_attributes=key_attributes(properties.get('KeySchema')),
        global_secondary_indexes=parse_cfn_indexes(
            properties.get('GlobalSecondaryIndexes'),
        ),
        local_secondary_indexes=parse_cfn_indexes(
            properties.get('LocalSecondaryIndexes'),
        ),
        ttl_enabled=coerce_bool(ttl.get('Enabled')),
        point_in_time_recovery=coerce_bool(
            pitr.get('PointInTimeRecoveryEnabled'),
        ),
        stream_view_type=coerce_str(stream.get('StreamViewType')),
        table_class=coerce_str(properties.get('TableClass')),
        autoscaled=any(
            token and token in autoscaling_hints
            for token in (name, logical_id)
        ),
    )


def tf_resources(module: object) -> list[dict[str, object]]:
    """Flatten a `terraform show -json` module tree."""
    if not isinstance(module, dict):
        return []
    found = [
        resource
        for resource in module.get('resources', [])
        if isinstance(resource, dict)
    ]
    for child in module.get('child_modules', []):
        found.extend(tf_resources(child))
    return found


def tf_index(raw: object) -> Index | None:
    if not isinstance(raw, dict):
        return None
    non_key = raw.get('non_key_attributes') or []
    return Index(
        name=coerce_str(raw.get('name')) or '<unnamed>',
        projection_type=coerce_str(raw.get('projection_type')),
        projected_attributes=tuple(
            item for item in non_key if isinstance(item, str)
        )
        if isinstance(non_key, list)
        else (),
        key_attributes=tuple(
            attribute
            for attribute in (
                coerce_str(raw.get('hash_key')),
                coerce_str(raw.get('range_key')),
            )
            if attribute
        ),
        read_capacity=coerce_int(raw.get('read_capacity')),
        write_capacity=coerce_int(raw.get('write_capacity')),
    )


def tf_indexes(raw: object) -> tuple[Index, ...]:
    if not isinstance(raw, list):
        return ()
    parsed = (tf_index(item) for item in raw)
    return tuple(index for index in parsed if index is not None)


def tf_block_flag(raw: object, key: str, *, default: bool) -> bool:
    """A `ttl {}`/`point_in_time_recovery {}` block's enabled state.

    Absent block means off. Present block means on unless it explicitly
    says otherwise -- `enabled` is optional in recent AWS providers.
    """
    if not isinstance(raw, list) or not raw:
        return False
    first = raw[0]
    if not isinstance(first, dict) or key not in first:
        return default
    return coerce_bool(first[key])


def tf_table(
    values: dict[str, object],
    fallback_name: str,
    source: str,
) -> Table:
    stream_enabled = values.get('stream_enabled')
    return Table(
        name=coerce_str(values.get('name')) or fallback_name,
        source=source,
        logical_id=fallback_name,
        billing_mode=coerce_str(values.get('billing_mode'))
        or DEFAULT_BILLING_MODE,
        read_capacity=coerce_int(values.get('read_capacity')),
        write_capacity=coerce_int(values.get('write_capacity')),
        key_attributes=tuple(
            attribute
            for attribute in (
                coerce_str(values.get('hash_key')),
                coerce_str(values.get('range_key')),
            )
            if attribute
        ),
        global_secondary_indexes=tf_indexes(
            values.get('global_secondary_index'),
        ),
        local_secondary_indexes=tf_indexes(
            values.get('local_secondary_index'),
        ),
        ttl_enabled=tf_block_flag(values.get('ttl'), 'enabled', default=True),
        point_in_time_recovery=tf_block_flag(
            values.get('point_in_time_recovery'),
            'enabled',
            default=True,
        ),
        stream_view_type=coerce_str(values.get('stream_view_type'))
        if coerce_bool(stream_enabled)
        else None,
        table_class=coerce_str(values.get('table_class')),
    )


def parse_terraform_json(document: object, source: str) -> list[Table]:
    """Tables in `terraform show -json` state or plan output."""
    if not isinstance(document, dict):
        return []
    root = document.get('values') or document.get('planned_values')
    if not isinstance(root, dict):
        return []

    resources = tf_resources(root.get('root_module'))
    hints = ' '.join(
        intrinsic_text(as_dict(resource.get('values')).get('resource_id'))
        for resource in resources
        if resource.get('type') == TF_SCALABLE_TARGET
    )

    tables = []
    for resource in resources:
        if resource.get('type') != TF_TABLE_TYPE:
            continue
        values = as_dict(resource.get('values'))
        fallback = str(resource.get('name', 'unnamed'))
        table = tf_table(values, fallback, source)
        tables.append(
            replace_autoscaled(table, hints) if hints else table,
        )
    return tables


def replace_autoscaled(table: Table, hints: str) -> Table:
    """Mark a table autoscaled when an autoscaling target names it."""
    autoscaled = any(
        token and token in hints for token in (table.name, table.logical_id)
    )
    if not autoscaled:
        return table
    return Table(**{**vars(table), 'autoscaled': True})


HCL_RESOURCE = re.compile(
    r'resource\s+"(?P<type>[\w-]+)"\s+"(?P<name>[\w-]+)"\s*\{',
)
HCL_ATTRIBUTE = re.compile(r'^\s*(?P<key>[\w-]+)\s*=\s*(?P<value>.+?)\s*$')
HCL_BLOCK_OPEN = re.compile(r'^\s*(?P<key>[\w-]+)\s*(=\s*)?\{\s*$')
HCL_COMMENT = re.compile(r'(^|\s)(#|//).*$')


@dataclass
class HclBlock:
    """A `{ ... }` body: literal attributes plus repeated sub-blocks."""

    attributes: dict[str, object] = field(default_factory=dict)
    blocks: dict[str, list[HclBlock]] = field(default_factory=dict)
    # Interpolations parse to None, so anything that has to be matched as
    # text (an autoscaling `resource_id`) needs the source line kept.
    raw: list[str] = field(default_factory=list)


def strip_hcl_comments(line: str) -> str:
    """Drop trailing comments, leaving anything inside a string alone."""
    out = []
    in_string = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == '"' and (index == 0 or line[index - 1] != '\\'):
            in_string = not in_string
        if not in_string and (
            line.startswith('#', index) or line.startswith('//', index)
        ):
            break
        out.append(char)
        index += 1
    return ''.join(out).rstrip()


def parse_hcl_value(raw: str) -> object:
    """A literal HCL value, or None when it is a reference/expression."""
    text = raw.strip().rstrip(',')
    if len(text) > 1 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if text in {'true', 'false'}:
        return text == 'true'
    try:
        return int(text)
    except ValueError:
        pass
    if text.startswith('[') and text.endswith(']'):
        items = [
            parse_hcl_value(item)
            for item in text[1:-1].split(',')
            if item.strip()
        ]
        return [item for item in items if item is not None]
    return None


def parse_hcl_body(lines: list[str], start: int) -> tuple[HclBlock, int]:
    """Read one brace body, returning it and the line after its close."""
    block = HclBlock()
    index = start
    while index < len(lines):
        line = strip_hcl_comments(lines[index])
        stripped = line.strip()
        index += 1
        if not stripped:
            continue
        if stripped == '}':
            return block, index
        block.raw.append(stripped)

        opened = HCL_BLOCK_OPEN.match(line)
        if opened:
            child, index = parse_hcl_body(lines, index)
            block.blocks.setdefault(opened.group('key'), []).append(child)
            continue

        attribute = HCL_ATTRIBUTE.match(line)
        if attribute and not attribute.group('value').endswith('{'):
            block.attributes[attribute.group('key')] = parse_hcl_value(
                attribute.group('value'),
            )
    return block, index


def hcl_block_values(block: HclBlock, key: str) -> list[dict[str, object]]:
    """Sub-blocks flattened into the dict shape the TF-JSON path uses."""
    return [child.attributes for child in block.blocks.get(key, [])]


def hcl_table(block: HclBlock, fallback_name: str, source: str) -> Table:
    values: dict[str, object] = dict(block.attributes)
    for key in ('global_secondary_index', 'local_secondary_index'):
        values[key] = hcl_block_values(block, key)
    for key in ('ttl', 'point_in_time_recovery'):
        if key in block.blocks:
            values[key] = hcl_block_values(block, key)
    return tf_table(values, fallback_name, source)


def parse_hcl(text: str, source: str) -> list[Table]:
    """Tables declared in `.tf` source, without running Terraform.

    Deliberately lenient: anything interpolated (`var.x`,
    `aws_dynamodb_table.t.name`) reads as unknown rather than as a value,
    because a bare checkout has no way to resolve it.
    """
    lines = text.splitlines()
    tables: list[tuple[Table, str]] = []
    hints: list[str] = []

    index = 0
    while index < len(lines):
        line = strip_hcl_comments(lines[index])
        match = HCL_RESOURCE.search(line)
        if not match:
            index += 1
            continue

        block, index = parse_hcl_body(lines, index + 1)
        resource_type = match.group('type')
        if resource_type == TF_TABLE_TYPE:
            name = match.group('name')
            tables.append((hcl_table(block, name, source), name))
        elif resource_type == TF_SCALABLE_TARGET:
            hints.extend(block.raw)

    joined = ' '.join(hints)
    return [
        replace_autoscaled(table, joined) if joined else table
        for table, _ in tables
    ]


def load_yaml(text: str) -> object:
    """CloudFormation YAML, with `!Ref`-style tags tolerated.

    PyYAML is optional: JSON templates (which is what CDK, SAM and
    Serverless all synthesize) never need it.
    """
    try:
        import yaml
    except ImportError as error:
        message = (
            'YAML templates need PyYAML -- rerun under '
            '`uv run --with pyyaml`, or point this at the synthesized '
            'JSON template instead'
        )
        raise DynamoCostAuditError(message) from error

    class Loader(yaml.SafeLoader):
        """SafeLoader that keeps going when it meets a CFN short form."""

    def unknown(loader: object, tag_suffix: str, node: object) -> object:
        del loader, tag_suffix, node
        return None

    Loader.add_multi_constructor('!', unknown)
    return yaml.load(text, Loader=Loader)  # noqa: S506


def parse_document(text: str, source: str, suffix: str) -> list[Table]:
    """Dispatch one file's contents to whichever parser fits."""
    if suffix == '.tf':
        return parse_hcl(text, source)

    if suffix == '.json':
        try:
            document = json.loads(text)
        except ValueError:
            return []
    else:
        try:
            document = load_yaml(text)
        except (DynamoCostAuditError, ValueError):
            return []

    return parse_cloudformation(document, source) + parse_terraform_json(
        document,
        source,
    )


def iac_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob('*')
        if path.is_file()
        and path.suffix.lower() in IAC_SUFFIXES
        and not SKIPPED_DIRECTORIES.intersection(path.parts)
    )


def load_iac(path: Path) -> list[Table]:
    """Every table declared under `path`, whether file or directory."""
    if path.is_file():
        paths = [path]
    elif path.is_dir():
        paths = iac_files(path)
    else:
        message = f'{path} does not exist'
        raise DynamoCostAuditError(message)

    tables: list[Table] = []
    for candidate in paths:
        tables.extend(
            parse_document(
                candidate.read_text(errors='replace'),
                str(candidate),
                candidate.suffix.lower(),
            ),
        )
    return tables


class Status(Enum):
    """Outcome of one section of the audit."""

    PASS = 'pass'  # noqa: S105
    FAIL = 'fail'
    NA = 'n/a'
    MANUAL = 'manual'


@dataclass(frozen=True)
class CheckResult:
    """One finding, with what to do about it.

    A section emits several of these -- unlike a launch checklist, an audit
    of N tables has N answers per question, and collapsing them to one
    verdict loses which table to go and fix.
    """

    number: int
    title: str
    status: Status
    detail: str


ITEM_SIZE = 1
ACCESS_PATTERNS = 2
SECONDARY_INDEXES = 3
CAPACITY_MODE = 4
TABLE_CLASS = 5
STORAGE = 6
BACKUPS = 7
STREAMS = 8

SECTION_TITLES = {
    ITEM_SIZE: 'Item size and write amplification',
    ACCESS_PATTERNS: 'Access patterns',
    SECONDARY_INDEXES: 'Secondary indexes',
    CAPACITY_MODE: 'Capacity mode',
    TABLE_CLASS: 'Table class',
    STORAGE: 'Storage',
    BACKUPS: 'Backups',
    STREAMS: 'Streams',
}

# `GSI1PK`/`gsi1sk` and friends: a concatenated synthetic key, which can
# approach the size of the data it indexes.
SYNTHETIC_KEY = re.compile(r'^gsi\d*(pk|sk)$', re.IGNORECASE)

WIDE_STREAM_VIEWS = frozenset({'NEW_AND_OLD_IMAGES'})
INFREQUENT_ACCESS = 'STANDARD_INFREQUENT_ACCESS'


def label(table: Table) -> str:
    return f'{table.name} ({table.source})'


def result(number: int, status: Status, detail: str) -> CheckResult:
    return CheckResult(number, SECTION_TITLES[number], status, detail)


def check_item_size(tables: list[Table]) -> list[CheckResult]:
    """§1. The biggest lever, and invisible to a template.

    Reported rather than skipped: every update pays the size of the larger
    of the old and new item, so item shape explains most surprising bills,
    and a tier-1 report that stayed silent would read as "nothing here".
    """
    names = ', '.join(table.name for table in tables)
    return [
        result(
            ITEM_SIZE,
            Status.MANUAL,
            f'Needs data, not a template ({names}). Sample real items and '
            'look for two things: items just over a 1KB write / 4KB read '
            'boundary (4.1KB costs 2 RCUs -- 2.5% more data, 100% more '
            'cost), and any large item a small, frequent update rewrites '
            'whole.\n'
            'aws dynamodb scan --table-name <name> --max-items 200 '
            "--output json | python3 -c 'import json,sys; d=json.load"
            '(sys.stdin); print(sorted(len(json.dumps(i)) for i in '
            'd["Items"])[-10:])\'',
        ),
    ]


def check_access_patterns(tables: list[Table]) -> list[CheckResult]:
    """§2. Lives in the query code, not the table definition."""
    del tables
    return [
        result(
            ACCESS_PATTERNS,
            Status.MANUAL,
            'Read the query code, not the template. `FilterExpression` '
            'saves almost nothing -- the RCUs are already spent by the '
            'time it runs. Check for N GetItem calls where one Query over '
            'an item collection would do, low-cardinality partition keys '
            '(they concentrate heat and throttle), and transactions used '
            'where atomicity is not actually required (they cost 2x a '
            'normal write).',
        ),
    ]


def index_findings(table: Table) -> list[CheckResult]:
    findings = []
    for index in table.global_secondary_indexes:
        if index.projection_type == 'ALL':
            findings.append(
                result(
                    SECONDARY_INDEXES,
                    Status.FAIL,
                    f'{label(table)}: {index.name} projects ALL. Every '
                    'write to a projected attribute propagates to the '
                    'index, and writes cost 5-20x reads. Create a '
                    'replacement GSI with KEYS_ONLY or a tight INCLUDE '
                    'and drop this one -- cheap and reversible on any '
                    'table that is not enormous.',
                ),
            )
        synthetic = [
            attribute
            for attribute in index.key_attributes
            if SYNTHETIC_KEY.match(attribute)
        ]
        if synthetic:
            findings.append(
                result(
                    SECONDARY_INDEXES,
                    Status.FAIL,
                    f'{label(table)}: {index.name} keys on '
                    f'{", ".join(synthetic)} -- a synthetic concatenated '
                    'key, which can approach the size of the data it '
                    'indexes (92 bytes of key on a 101-byte item, in one '
                    'DeBrie example). Prefer a multi-attribute composite '
                    'key. The exception is an overloaded index serving '
                    'several entity types, which cannot use the new form.',
                ),
            )
    return findings


def check_secondary_indexes(tables: list[Table]) -> list[CheckResult]:
    """§3. The most common quick win in the whole audit."""
    findings: list[CheckResult] = []
    indexed = False

    for table in tables:
        findings.extend(index_findings(table))

        if table.global_secondary_indexes:
            indexed = True
            names = ', '.join(
                index.name for index in table.global_secondary_indexes
            )
            findings.append(
                result(
                    SECONDARY_INDEXES,
                    Status.MANUAL,
                    f'{label(table)}: {names}. An index nothing has read '
                    'in 30 days is a pure tax on every write, and is '
                    'surprisingly common. Confirm each one is still '
                    'queried:\naws cloudwatch get-metric-statistics '
                    '--namespace AWS/DynamoDB --metric-name '
                    'ConsumedReadCapacityUnits --dimensions '
                    f'Name=TableName,Value={table.name} '
                    'Name=GlobalSecondaryIndexName,Value=<index> '
                    '--start-time $(date -u -d -30days +%FT%TZ) --end-time '
                    '$(date -u +%FT%TZ) --period 86400 --statistics Sum',
                ),
            )

        if table.local_secondary_indexes:
            indexed = True
            names = ', '.join(
                index.name for index in table.local_secondary_indexes
            )
            findings.append(
                result(
                    SECONDARY_INDEXES,
                    Status.MANUAL,
                    f'{label(table)}: LSIs {names}. These consume the base '
                    "table's capacity and share the partition's 10GB "
                    'limit, and unlike a GSI they can only be added or '
                    'removed by recreating the table -- so confirm they '
                    'are still queried before the next rebuild, not after.',
                ),
            )

    if not indexed:
        return [
            result(
                SECONDARY_INDEXES,
                Status.NA,
                'No secondary indexes declared.',
            ),
        ]
    return findings


def check_capacity_mode(tables: list[Table]) -> list[CheckResult]:
    """§4. On-demand's November 2024 price cut moved the break-even."""
    findings = []
    for table in tables:
        if table.billing_mode != DEFAULT_BILLING_MODE:
            continue
        if table.autoscaled:
            findings.append(
                result(
                    CAPACITY_MODE,
                    Status.MANUAL,
                    f'{label(table)}: provisioned with autoscaling. The '
                    'rule of thumb is you must consume at least 30% of '
                    'what you provision; below that, on-demand is '
                    'cheaper. Autoscaling helps but does not settle it -- '
                    'compare consumed against provisioned over a real '
                    'month, and re-run any comparison made before the '
                    'November 2024 on-demand price cut.',
                ),
            )
            continue
        findings.append(
            result(
                CAPACITY_MODE,
                Status.FAIL,
                f'{label(table)}: provisioned with no autoscaling target. '
                'Fixed capacity is only right for throughput you can '
                'actually predict, and you pay for the peak all month. '
                'Either attach autoscaling or move to PAY_PER_REQUEST.',
            ),
        )

    findings.append(
        result(
            CAPACITY_MODE,
            Status.MANUAL,
            'Reserved capacity is a regional RCU/WCU commitment worth '
            '54-77% off hourly rates. If the org already signs long-term '
            'AWS commitments, not having one for the steady-state floor '
            'is usually an oversight rather than a decision.',
        )
        if any(table.billing_mode == DEFAULT_BILLING_MODE for table in tables)
        else result(
            CAPACITY_MODE,
            Status.PASS,
            'No provisioned-capacity tables declared.',
        ),
    )
    return findings


def check_table_class(tables: list[Table]) -> list[CheckResult]:
    """§5. Performance is identical; it is purely a cost mix."""
    standard = [
        table for table in tables if table.table_class != INFREQUENT_ACCESS
    ]
    if not standard:
        return [
            result(
                TABLE_CLASS,
                Status.PASS,
                'Every table is already Standard-IA.',
            ),
        ]
    names = ', '.join(label(table) for table in standard)
    return [
        result(
            TABLE_CLASS,
            Status.MANUAL,
            f'Standard table class: {names}. Performance is identical '
            'between Standard and Standard-IA -- the choice is only the '
            'storage-vs-throughput mix. When storage exceeds ~42% of '
            'throughput cost, Standard-IA wins. Split the line items in '
            'Cost Explorer by usage type, and talk to an AWS specialist '
            'before flipping a large table.',
        ),
    ]


def check_storage(tables: list[Table]) -> list[CheckResult]:
    """§6. TTL is free; adding it late is not."""
    without = [table for table in tables if not table.ttl_enabled]
    if not without:
        return [
            result(STORAGE, Status.PASS, 'TTL is enabled on every table.'),
        ]
    names = ', '.join(label(table) for table in without)
    return [
        result(
            STORAGE,
            Status.FAIL,
            f'No TTL: {names}. TTL costs nothing and keeps storage flat. '
            'The catch is that adding the attribute after the fact needs a '
            'backfill of every existing item, which is not free -- so add '
            'it now even if you are unsure it will be used. Writing an '
            'unused timestamp is far cheaper than a retroactive '
            'full-table update.',
        ),
    ]


def check_backups(tables: list[Table]) -> list[CheckResult]:
    """§7. PITR costs a little and replaces something dearer."""
    without = [table for table in tables if not table.point_in_time_recovery]
    if not without:
        return [
            result(BACKUPS, Status.PASS, 'PITR is enabled on every table.'),
        ]
    names = ', '.join(label(table) for table in without)
    return [
        result(
            BACKUPS,
            Status.FAIL,
            f'PITR disabled: {names}. It adds cost, but less than the '
            'backup schemes it replaces, and it buys any point in the last '
            '35 days. Note that recovering from a bad write does not need '
            'a full restore at ~$150/TB -- an incremental export across '
            'the window of the accident is the cheap path.',
        ),
    ]


def check_streams(tables: list[Table]) -> list[CheckResult]:
    """Streams are one of the six cost sources, and widen with the item."""
    streaming = [table for table in tables if table.stream_view_type]
    if not streaming:
        return [
            result(STREAMS, Status.NA, 'No table declares a stream.'),
        ]

    wide = [
        table
        for table in streaming
        if table.stream_view_type in WIDE_STREAM_VIEWS
    ]
    if not wide:
        return [
            result(
                STREAMS,
                Status.PASS,
                'Streams are on, with a view type narrower than '
                'NEW_AND_OLD_IMAGES.',
            ),
        ]
    names = ', '.join(
        f'{label(table)} -> {table.stream_view_type}' for table in wide
    )
    return [
        result(
            STREAMS,
            Status.MANUAL,
            f'{names}. A stream record carries whichever images the view '
            'type names, so the widest view pays the item size twice on '
            'every update. Narrow it to NEW_IMAGE or KEYS_ONLY unless a '
            'consumer genuinely diffs against the old image.',
        ),
    ]


def run_checks(tables: list[Table]) -> list[CheckResult]:
    """Every section, in the order the skill states them."""
    if not tables:
        message = (
            'no DynamoDB tables found -- point this at a synthesized '
            'template (cdk.out/*.template.json, `sam build` output), '
            '`terraform show -json > state.json`, or a directory of .tf '
            'sources'
        )
        raise DynamoCostAuditError(message)

    return [
        *check_item_size(tables),
        *check_access_patterns(tables),
        *check_secondary_indexes(tables),
        *check_capacity_mode(tables),
        *check_table_class(tables),
        *check_storage(tables),
        *check_backups(tables),
        *check_streams(tables),
    ]


STATUS_ORDER = (Status.FAIL, Status.MANUAL, Status.NA, Status.PASS)
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_UNUSABLE = 2


def version() -> str:
    """This checkout's plugin version, or `unknown` outside one.

    `--version` has to work with no config and no credentials, so a
    missing or unreadable manifest is an answer rather than a crash.
    """
    manifest = (
        Path(__file__).resolve().parents[3] / '.claude-plugin' / 'plugin.json'
    )
    try:
        return str(json.loads(manifest.read_text())['version'])
    except (OSError, ValueError, KeyError):
        return 'unknown'


def render(results: list[CheckResult]) -> str:
    """Human-readable report, worst first, then in checklist order."""
    lines: list[str] = []
    for status in STATUS_ORDER:
        matching = [item for item in results if item.status is status]
        if not matching:
            continue
        lines.append(status.value.upper())
        seen: set[int] = set()
        for item in matching:
            if item.number not in seen:
                seen.add(item.number)
                lines.append(f'  {item.number}. {item.title}')
            lines.extend(f'     {line}' for line in item.detail.splitlines())
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def as_json(
    results: list[CheckResult],
    tables: list[Table] | None = None,
) -> str:
    """The same report, for a caller that wants to branch on it."""
    return json.dumps(
        {
            'tables': [table.name for table in tables or []],
            'checks': [
                {
                    'number': item.number,
                    'title': item.title,
                    'status': item.status.value,
                    'detail': item.detail,
                }
                for item in results
            ],
        },
        indent=2,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='dynamodb-cost-audit',
        description=(
            "The dynamodb-cost-audit checklist's deterministic half, over "
            'infrastructure-as-code. No AWS credentials.'
        ),
        epilog=(
            'Reads CloudFormation-shaped JSON/YAML (so CDK, SAM and '
            'Serverless too), `terraform show -json` output, and .tf '
            'sources. A bare run audits the current directory. What only '
            'metrics can answer -- item size, which indexes nobody reads, '
            'consumed vs. provisioned -- is reported as MANUAL with the '
            'command to run.'
        ),
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        type=Path,
        help='IaC file or directory to audit; defaults to cwd',
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'dynamodb-cost-audit {version()}',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        dest='as_json',
        help='machine-readable output',
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. 0 clean, 1 findings to act on, 2 nothing to audit."""
    args = build_parser().parse_args(
        list(sys.argv[1:] if argv is None else argv),
    )

    try:
        tables = load_iac(args.path)
        results = run_checks(tables)
    except DynamoCostAuditError as error:
        print(f'dynamodb-cost-audit: {error}', file=sys.stderr)
        return EXIT_UNUSABLE

    print(
        as_json(results, tables) if args.as_json else render(results),
        end='',
    )

    failed = any(item.status is Status.FAIL for item in results)
    return EXIT_FINDINGS if failed else EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
