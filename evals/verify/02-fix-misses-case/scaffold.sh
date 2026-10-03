#!/usr/bin/env bash
set -euo pipefail

commit() {
	git -c user.name=eval -c user.email=eval@example.invalid add -A
	git -c user.name=eval -c user.email=eval@example.invalid commit -qm "$1"
}

cat >prices.py <<'PY'
from decimal import Decimal


def parse_price(text: str) -> Decimal:
    return Decimal(text.strip().lstrip("$"))
PY

cat >test_prices.py <<'PY'
import unittest
from decimal import Decimal

from prices import parse_price


class ParsePriceTest(unittest.TestCase):
    def test_plain(self) -> None:
        self.assertEqual(parse_price("$12.50"), Decimal("12.50"))
PY

git init -q -b main
commit 'chore: init'

cat >prices.py <<'PY'
from decimal import Decimal


def parse_price(text: str) -> Decimal:
    return Decimal(text.strip().lstrip("$").replace(",", "", 1))
PY

cat >test_prices.py <<'PY'
import unittest
from decimal import Decimal

from prices import parse_price


class ParsePriceTest(unittest.TestCase):
    def test_plain(self) -> None:
        self.assertEqual(parse_price("$12.50"), Decimal("12.50"))

    def test_thousands(self) -> None:
        self.assertEqual(parse_price("$1,234.50"), Decimal("1234.50"))

    def test_millions(self) -> None:
        self.assertEqual(parse_price("$1,234,567.00"), Decimal("1234567.00"))
PY

commit 'fix: parse_price handles thousands separators'
