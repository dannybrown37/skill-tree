#!/usr/bin/env bash
set -euo pipefail

commit() {
	git -c user.name=eval -c user.email=eval@example.invalid add -A
	git -c user.name=eval -c user.email=eval@example.invalid commit -qm "$1"
}

write_tax() {
	cat >tax.py <<PY
from decimal import $1, Decimal

RATE = Decimal("0.05")


def tax(amount: Decimal) -> Decimal:
    return (amount * RATE).quantize(Decimal("0.01"), rounding=$1)
PY
}

write_tax ROUND_HALF_UP

cat >invoice.py <<'PY'
from decimal import Decimal

from tax import tax


def invoice_total(items: list[Decimal]) -> Decimal:
    subtotal = sum(items, Decimal("0"))
    return subtotal + tax(subtotal)
PY

cat >test_tax.py <<'PY'
import unittest
from decimal import Decimal

from tax import tax


class TaxTest(unittest.TestCase):
    def test_round_amount(self) -> None:
        self.assertEqual(tax(Decimal("10.00")), Decimal("0.50"))

    def test_rounds_up_past_half(self) -> None:
        self.assertEqual(tax(Decimal("19.99")), Decimal("1.00"))
PY

cat >test_invoice.py <<'PY'
import unittest
from decimal import Decimal

from invoice import invoice_total


class InvoiceTest(unittest.TestCase):
    def test_small_invoice(self) -> None:
        self.assertEqual(invoice_total([Decimal("0.25"), Decimal("0.25")]), Decimal("0.53"))
PY

git init -q -b main
commit 'chore: init'

write_tax ROUND_HALF_EVEN
commit "refactor: use banker's rounding for tax"
