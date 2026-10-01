#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../_lib.sh
source "$(dirname "$0")/../_lib.sh"

repo="$1/invoicer"
init_repo "${repo}" "fix/due-date-flake"
mkdir -p "${repo}/src/invoicer" "${repo}/tests"

cat >"${repo}/pyproject.toml" <<'EOF'
[project]
name = "invoicer"
version = "0.4.2"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = ["pytest==8.3.3"]
EOF

touch "${repo}/src/invoicer/__init__.py"

cat >"${repo}/src/invoicer/due.py" <<'EOF'
from datetime import date, datetime, timedelta

NET_TERMS = {"net15": 15, "net30": 30, "net60": 60}


def compute_due_date(issued_at: datetime, terms: str) -> date:
    days = NET_TERMS[terms]
    issued_day = issued_at.date()
    if issued_day > date.today():
        raise ValueError("invoice issued in the future")
    return issued_day + timedelta(days=days)


def days_until_due(issued_at: datetime, terms: str) -> int:
    return (compute_due_date(issued_at, terms) - date.today()).days
EOF

cat >"${repo}/src/invoicer/schedule.py" <<'EOF'
from datetime import datetime

from invoicer.due import compute_due_date, days_until_due


def reminder_plan(invoices: list[dict]) -> list[tuple[str, int]]:
    plan = []
    for inv in invoices:
        issued_at: datetime = inv["issued_at"]
        remaining = days_until_due(issued_at, inv["terms"])
        if remaining <= 3:
            plan.append((inv["id"], remaining))
    return plan


def overdue(invoices: list[dict]) -> list[str]:
    out = []
    for inv in invoices:
        due = compute_due_date(inv["issued_at"], inv["terms"])
        if due < datetime.now().date():
            out.append(inv["id"])
    return out
EOF

cat >"${repo}/src/invoicer/money.py" <<'EOF'
from decimal import ROUND_HALF_EVEN, Decimal


def format_currency(amount: Decimal) -> str:
    return f"${amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)}"
EOF

cat >"${repo}/tests/test_due.py" <<'EOF'
from datetime import UTC, datetime, timedelta

from invoicer.due import compute_due_date, days_until_due


def test_net30() -> None:
    issued = datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert compute_due_date(issued, "net30").isoformat() == "2026-01-31"


def test_due_date_rollover() -> None:
    issued = datetime.now(UTC) - timedelta(minutes=5)
    assert days_until_due(issued, "net15") == 15
EOF

commit "${repo}" "2026-09-20T10:00:00Z" "feat: due-date computation and reminders"

# The in-flight edit the session left behind: new signature, callers not yet
# updated, test not yet rewritten.
cat >"${repo}/src/invoicer/due.py" <<'EOF'
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

NET_TERMS = {"net15": 15, "net30": 30, "net60": 60}

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def compute_due_date(
    issued_at: datetime, terms: str, clock: Clock = _utc_now
) -> date:
    days = NET_TERMS[terms]
    issued_day = issued_at.astimezone(UTC).date()
    if issued_day > clock().date():
        raise ValueError("invoice issued in the future")
    return issued_day + timedelta(days=days)


def days_until_due(
    issued_at: datetime, terms: str, clock: Clock = _utc_now
) -> int:
    return (compute_due_date(issued_at, terms, clock) - clock().date()).days
EOF
