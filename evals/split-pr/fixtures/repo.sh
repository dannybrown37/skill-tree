#!/usr/bin/env bash
# An expenses service on branch feature/csv-export, checked out and clean,
# eight messy commits ahead of origin/main. The branch mixes a spec, a
# no-behaviour-change rename (utils.py -> money.py), a schema change, a CI
# tweak, and two features with their tests, so a good cut is by concern,
# not by commit. `repo.sh tickets` also commits ticket files (EXP-101..103)
# that define the cut. origin is a local bare repo (the sandbox has no
# network), and .git/eval-gh makes the stand-in gh report "logged in".
set -euo pipefail

variant="${1:-plain}"
g() { git -c user.name=eval -c user.email=eval@example.invalid "$@"; }

cat >CLAUDE.md <<'EOF'
# expenses

- Tests: `python3 -m unittest -v`
- PR titles: `<JIRA-KEY>: <purpose>` when there is a ticket.
EOF

cat >utils.py <<'EOF'
def fmt_cents(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"
EOF

cat >models.py <<'EOF'
from dataclasses import dataclass


@dataclass
class Expense:
    id: int
    submitter: str
    amount_cents: int
    status: str
EOF

cat >report.py <<'EOF'
from models import Expense
from utils import fmt_cents


def summary(expenses: list[Expense]) -> str:
    total = sum(e.amount_cents for e in expenses)
    return f"{len(expenses)} expenses, {fmt_cents(total)}"
EOF

cat >test_report.py <<'EOF'
import unittest

from models import Expense
from report import summary


class SummaryTest(unittest.TestCase):
    def test_totals(self) -> None:
        rows = [Expense(1, "ana", 1250, "approved"), Expense(2, "bo", 5, "draft")]
        self.assertEqual(summary(rows), "2 expenses, $12.55")


if __name__ == "__main__":
    unittest.main()
EOF

mkdir -p migrations .github/workflows
cat >migrations/001_expenses.sql <<'EOF'
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY,
    submitter TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL
);
EOF

cat >.github/workflows/ci.yml <<'EOF'
name: ci
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - run: python3 -m unittest -v
EOF

git init -q -b main
g add -A
g commit -qm 'chore: init'

git init -q --bare .git/eval-origin
git remote add origin "$(pwd)/.git/eval-origin"
git push -q origin main
git fetch -q origin
mkdir -p .git/eval-gh

git switch -q -c feature/csv-export

mkdir -p docs/specs
cat >docs/specs/csv-export.md <<'EOF'
# CSV export of approved expenses

Finance pulls approved expenses out of the app by hand every month.

1. Expenses record when they were approved (`approved_at`, ISO date).
2. `export_csv(expenses)` returns CSV text of approved expenses:
   `id,submitter,amount,approved_at`, amount formatted as dollars.
3. `export_csv(expenses, start, end)` keeps only expenses approved in
   `[start, end]`.
EOF
if [[ "${variant}" == tickets ]]; then
	mkdir -p docs/planning/csv-export/tickets
	cat >docs/planning/csv-export/tickets/01-approved-at.md <<'EOF'
# EXP-101: record approved_at on expenses

Add `approved_at: date | None` to `Expense` and a migration for the column.
EOF
	cat >docs/planning/csv-export/tickets/02-csv-export.md <<'EOF'
# EXP-102: export approved expenses as CSV

**Blocked by:** EXP-101

`export_csv(expenses)` per docs/specs/csv-export.md item 2, with tests.
EOF
	cat >docs/planning/csv-export/tickets/03-date-filter.md <<'EOF'
# EXP-103: filter the CSV export by approval date

**Blocked by:** EXP-102

Optional `start` / `end` arguments per item 3, with tests.
EOF
fi
g add -A
g commit -qm 'docs: csv export plan'

git mv utils.py money.py
cat >money.py <<'EOF'
def format_dollars(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"
EOF
sed -i 's/from utils import fmt_cents/from money import format_dollars/; s/fmt_cents(/format_dollars(/' report.py
g add -A
g commit -qm 'wip'

cat >models.py <<'EOF'
from dataclasses import dataclass
from datetime import date


@dataclass
class Expense:
    id: int
    submitter: str
    amount_cents: int
    status: str
    approved_at: date | None = None
EOF
cat >migrations/002_approved_at.sql <<'EOF'
ALTER TABLE expenses ADD COLUMN approved_at TEXT;
EOF
g add -A
g commit -qm 'more'

cat >export.py <<'EOF'
import csv
import io

from models import Expense
from money import format_dollars


def export_csv(expenses: list[Expense]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["id", "submitter", "amount", "approved_at"])
    for e in expenses:
        if e.status == "approved" and e.approved_at is not None:
            writer.writerow([e.id, e.submitter, format_dollars(e.amount_cents), e.approved_at.isoformat()])
    return out.getvalue()
EOF
g add -A
g commit -qm 'export'

sed -i 's/python3 -m unittest -v/python3 -m unittest -v\n      - run: python3 -m compileall -q ./' .github/workflows/ci.yml
cat >test_export.py <<'EOF'
import unittest
from datetime import date

from export import export_csv
from models import Expense


class ExportTest(unittest.TestCase):
    def test_only_approved_rows(self) -> None:
        rows = [
            Expense(1, "ana", 1250, "approved", date(2026, 3, 2)),
            Expense(2, "bo", 500, "draft"),
        ]
        self.assertEqual(
            export_csv(rows),
            "id,submitter,amount,approved_at\n1,ana,$12.50,2026-03-02\n",
        )


if __name__ == "__main__":
    unittest.main()
EOF
g add -A
g commit -qm 'tests + ci'

cat >export.py <<'EOF'
import csv
import io
from datetime import date

from models import Expense
from money import format_dollars


def export_csv(
    expenses: list[Expense],
    start: date | None = None,
    end: date | None = None,
) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["id", "submitter", "amount", "approved_at"])
    for e in expenses:
        if e.status != "approved" or e.approved_at is None:
            continue
        if start is not None and e.approved_at < start:
            continue
        if end is not None and e.approved_at > end:
            continue
        writer.writerow([e.id, e.submitter, format_dollars(e.amount_cents), e.approved_at.isoformat()])
    return out.getvalue()
EOF
g add -A
g commit -qm 'date filter'

cat >test_export.py <<'EOF'
import unittest
from datetime import date

from export import export_csv
from models import Expense


class ExportTest(unittest.TestCase):
    def test_only_approved_rows(self) -> None:
        rows = [
            Expense(1, "ana", 1250, "approved", date(2026, 3, 2)),
            Expense(2, "bo", 500, "draft"),
        ]
        self.assertEqual(
            export_csv(rows),
            "id,submitter,amount,approved_at\n1,ana,$12.50,2026-03-02\n",
        )


class DateFilterTest(unittest.TestCase):
    def test_keeps_rows_in_range(self) -> None:
        rows = [
            Expense(1, "ana", 100, "approved", date(2026, 2, 28)),
            Expense(2, "bo", 200, "approved", date(2026, 3, 15)),
        ]
        out = export_csv(rows, date(2026, 3, 1), date(2026, 3, 31))
        self.assertEqual(out.splitlines()[1:], ["2,bo,$2.00,2026-03-15"])


if __name__ == "__main__":
    unittest.main()
EOF
g add -A
g commit -qm 'fix tests'

cat >>docs/specs/csv-export.md <<'EOF'

Out of scope: XLSX, emailing the file.
EOF
g add -A
g commit -qm 'docs'
