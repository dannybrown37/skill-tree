#!/usr/bin/env bash
set -euo pipefail

mkdir -p orders

cat >orders/__init__.py <<'PY'
PY

cat >orders/state.py <<'PY'
from enum import StrEnum


class OrderState(StrEnum):
    PLACED = "placed"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.PLACED: {OrderState.PAID, OrderState.CANCELLED},
    OrderState.PAID: {OrderState.SHIPPED, OrderState.CANCELLED},
    OrderState.SHIPPED: {OrderState.DELIVERED, OrderState.CANCELLED},
    OrderState.DELIVERED: {OrderState.REFUNDED},
    OrderState.CANCELLED: {OrderState.REFUNDED},
    OrderState.REFUNDED: set(),
}


def advance(current: OrderState, target: OrderState) -> OrderState:
    if target not in TRANSITIONS[current]:
        msg = f"cannot go from {current} to {target}"
        raise ValueError(msg)
    return target
PY

cat >orders/test_state.py <<'PY'
import pytest

from orders.state import OrderState, advance


def test_paid_order_ships() -> None:
    assert advance(OrderState.PAID, OrderState.SHIPPED) is OrderState.SHIPPED


def test_refunded_is_final() -> None:
    with pytest.raises(ValueError):
        advance(OrderState.REFUNDED, OrderState.PAID)
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
