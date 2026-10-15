#!/usr/bin/env bash
# A small expenses API with a CONTEXT.md glossary and a docs/specs/
# convention. The glossary says "workspace", never "team", so a spec built
# from a conversation that said "team" has to translate.
set -euo pipefail

mkdir -p expenses tests docs/specs

cat >CONTEXT.md <<'MD'
# Context

**Workspace**: the billing unit that owns expenses and members.
_Avoid_: team, org, account.

**Expense**: one reimbursable purchase, with an amount, a category, a
submitter, and a status.

**Approver**: a member of the workspace allowed to approve expenses.
MD

cat >docs/specs/README.md <<'MD'
# Specs

One file per feature, named `<feature-slug>.md`, in the house template
(Problem Statement, Solution, User Stories, Implementation Decisions,
Testing Decisions, Out of Scope, Further Notes).
MD

cat >expenses/__init__.py <<'PY'
PY

cat >expenses/api.py <<'PY'
from dataclasses import asdict, dataclass
from decimal import Decimal

from flask import Flask, jsonify


@dataclass
class Expense:
    id: int
    workspace_id: int
    submitter: str
    category: str
    amount: Decimal
    status: str


EXPENSES: list[Expense] = []

app = Flask(__name__)


@app.get("/workspaces/<int:workspace_id>/expenses")
def list_expenses(workspace_id: int):
    rows = [asdict(e) for e in EXPENSES if e.workspace_id == workspace_id]
    return jsonify(rows)
PY

cat >tests/test_api.py <<'PY'
from decimal import Decimal

from expenses.api import EXPENSES, Expense, app


def test_lists_only_this_workspace() -> None:
    EXPENSES[:] = [
        Expense(1, 7, "ana", "travel", Decimal("120.00"), "approved"),
        Expense(2, 8, "bo", "meals", Decimal("40.00"), "pending"),
    ]
    rows = app.test_client().get("/workspaces/7/expenses").get_json()
    assert [r["id"] for r in rows] == [1]
PY

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
