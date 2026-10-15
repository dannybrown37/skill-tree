#!/usr/bin/env bash
# customer_id fans out across a schema, three services, an API, and a
# report: a wide mechanical rename that can't land as one vertical slice.
set -euo pipefail

mkdir -p billing shipping support reports migrations

cat >migrations/001_init.sql <<'SQL'
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, total_cents INTEGER NOT NULL);
CREATE TABLE tickets (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, subject TEXT NOT NULL);
SQL

for svc in billing shipping support; do
  : >"${svc}/__init__.py"
done

cat >billing/invoices.py <<'PY'
def invoice_for(db, customer_id: int) -> int:
    rows = db.execute("SELECT total_cents FROM orders WHERE customer_id = ?", (customer_id,))
    return sum(r[0] for r in rows)
PY

cat >shipping/labels.py <<'PY'
def label(order: dict[str, object]) -> str:
    return f"order {order['id']} for customer {order['customer_id']}"
PY

cat >support/tickets.py <<'PY'
def open_tickets(db, customer_id: int) -> list[str]:
    rows = db.execute("SELECT subject FROM tickets WHERE customer_id = ?", (customer_id,))
    return [r[0] for r in rows]
PY

cat >api.py <<'PY'
from billing.invoices import invoice_for


def get_invoice(db, params: dict[str, str]) -> dict[str, int]:
    customer_id = int(params["customer_id"])
    return {"customer_id": customer_id, "total_cents": invoice_for(db, customer_id)}
PY

cat >reports/monthly.sql <<'SQL'
SELECT customer_id, SUM(total_cents) FROM orders GROUP BY customer_id;
SQL

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
