#!/usr/bin/env bash
set -euo pipefail

cat >billing.py <<'PY'
from decimal import Decimal


def total(items: list[Decimal]) -> Decimal:
    return sum(items, Decimal("0"))


def legacy_total(items: list[Decimal]) -> Decimal:
    return sum((item for item in items if item > 0), Decimal("0"))
PY

cat >reports.json <<'JSON'
{
  "monthly": {"kind": "total", "items": ["10.00", "-2.50", "4.25"]}
}
JSON

cat >reports.py <<'PY'
import json
import sys
from decimal import Decimal
from pathlib import Path

import billing


def run(name: str) -> Decimal:
    report = json.loads(Path("reports.json").read_text())[name]
    compute = getattr(billing, f"legacy_{report['kind']}")
    return compute([Decimal(item) for item in report["items"]])


if __name__ == "__main__":
    print(run(sys.argv[1]))
PY

cat >test_billing.py <<'PY'
import unittest
from decimal import Decimal

from billing import total


class TotalTest(unittest.TestCase):
    def test_sums_items(self) -> None:
        self.assertEqual(total([Decimal("1.50"), Decimal("2.50")]), Decimal("4.00"))


if __name__ == "__main__":
    unittest.main()
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
