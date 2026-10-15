#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname -- "${BASH_SOURCE[0]}")/../../to-spec/fixtures/repo.sh"

cat >docs/specs/expense-csv-export.md <<'MD'
# Expense CSV export

## Problem Statement

Approvers reconcile expenses in a spreadsheet every month and today copy
them out of the app by hand, one row at a time.

## Solution

Approvers can download a workspace's expenses as a CSV for a date range
they choose.

## User Stories

1. As an approver, I want to download my workspace's expenses as CSV, so that I can reconcile them in a spreadsheet.
2. As an approver, I want to pick a date range, so that I export only the month I am closing.
3. As an approver, I want only approved expenses by default, so that the totals match what was paid.
4. As an approver, I want an option to include pending expenses, so that I can see what is still outstanding.
5. As an approver, I want a clear error when the export is over 10,000 rows, so that I know to narrow the range.
6. As a member who is not an approver, I am refused the export, so that expense data stays with approvers.

## Implementation Decisions

- New endpoint on the workspace expenses resource returning `text/csv`.
- Columns: date, submitter, category, amount, status.
- Expenses gain a date field; the in-memory store has none today.
- Synchronous; capped at 10,000 rows with a 422 past that.
- Non-approvers get 403. Approver membership is new: the app has no
  member roles yet.

## Testing Decisions

- Test through the HTTP API with Flask's test client, like the existing
  expenses listing test.

## Out of Scope

XLSX, emailed exports, scheduled exports.
MD

git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'docs: csv export spec'
