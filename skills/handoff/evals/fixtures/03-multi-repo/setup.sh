#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../_lib.sh
source "$(dirname "$0")/../_lib.sh"

api="$1/ledger-api"
web="$1/ledger-web"

init_repo "${api}" "feat/amount-minor"
mkdir -p "${api}/app"
cat >"${api}/app/serializers.py" <<'EOF'
def serialize_invoice(inv) -> dict:
    return {
        "id": inv.id,
        "amount_cents": inv.amount_minor,
        "currency": inv.currency,
    }
EOF
commit "${api}" "2026-09-24T09:00:00Z" "feat: invoice serializer"
cat >"${api}/app/serializers.py" <<'EOF'
def serialize_invoice(inv) -> dict:
    return {
        "id": inv.id,
        "amount_minor": inv.amount_minor,
        # Deprecated alias; remove only after ledger-web ships amount_minor.
        "amount_cents": inv.amount_minor,
        "currency": inv.currency,
    }
EOF
commit "${api}" "2026-09-25T11:00:00Z" "feat: add amount_minor, keep amount_cents alias"

init_repo "${web}" "chore/amount-minor"
mkdir -p "${web}/src/api" "${web}/src/components" "${web}/src/pages"
cat >"${web}/src/api/types.ts" <<'EOF'
export interface Invoice {
  id: string;
  amount_cents: number;
  currency: string;
}
EOF
cat >"${web}/src/components/InvoiceRow.tsx" <<'EOF'
import type { Invoice } from "../api/types";
import { formatMoney } from "../money";

export function InvoiceRow({ inv }: { inv: Invoice }) {
  return <td>{formatMoney(inv.amount_cents, inv.currency)}</td>;
}
EOF
cat >"${web}/src/pages/Summary.tsx" <<'EOF'
import type { Invoice } from "../api/types";

export function total(invoices: Invoice[]): number {
  return invoices.reduce((acc, i) => acc + i.amount_cents, 0);
}
EOF
cat >"${web}/src/money.ts" <<'EOF'
export function formatMoney(minor: number, currency: string): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(minor / 100);
}
EOF
commit "${web}" "2026-09-24T09:30:00Z" "feat: invoice list"

cat >"${web}/src/api/types.ts" <<'EOF'
export interface Invoice {
  id: string;
  amount_minor: number;
  currency: string;
}
EOF
cat >"${web}/src/components/InvoiceRow.tsx" <<'EOF'
import type { Invoice } from "../api/types";
import { formatMoney } from "../money";

export function InvoiceRow({ inv }: { inv: Invoice }) {
  return <td>{formatMoney(inv.amount_minor, inv.currency)}</td>;
}
EOF
