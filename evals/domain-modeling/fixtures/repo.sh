#!/usr/bin/env bash
# A shop backend whose glossary and code agree that a Cancellation is
# always a whole Order. Case 01 pushes a conflicting meaning at it.
set -euo pipefail

cat >CONTEXT.md <<'EOF2'
# Context

Domain vocabulary for the shop backend. Use these terms exactly in code, docs, specs, and
conversation. When a term here disagrees with casual usage, the term here wins.

## Terms

### Order

What a Customer submits at checkout: one or more Line Items paid in one payment.

- **Examples**: "the Order shipped", "refund the Order"
- **Not**: a Cart (unsubmitted), a Shipment (one Order can ship in several)
- **In code**: `Order` in `shop/orders.py`
- **See also**: Cancellation

### Cancellation

Withdrawing an entire Order before it ships. Every Line Item is voided and the full payment
is refunded.

- **Examples**: "the customer cancelled their Order", "Cancellations close the Order"
- **Not**: a Return (after delivery), removing a single Line Item
- **In code**: `cancel_order()` in `shop/orders.py`
- **See also**: Order
EOF2

mkdir -p shop
cat >shop/orders.py <<'EOF2'
from dataclasses import dataclass, field


@dataclass
class LineItem:
    sku: str
    cents: int
    voided: bool = False


@dataclass
class Order:
    id: str
    items: list[LineItem] = field(default_factory=list)
    status: str = "placed"


def cancel_order(order: Order) -> int:
    """Void every line item and return the cents to refund."""
    if order.status == "shipped":
        raise ValueError("cannot cancel a shipped order")
    for item in order.items:
        item.voided = True
    order.status = "cancelled"
    return sum(item.cents for item in order.items)
EOF2

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
