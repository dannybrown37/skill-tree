#!/usr/bin/env bash
# A Textual todo app whose README screenshots predate the Calendar tab.
# Textual isn't installed (the sandbox has no network), so this tests the
# plan, not a capture run.
set -euo pipefail

mkdir -p tasker docs/screenshots

cat >pyproject.toml <<'TOML'
[project]
name = "tasker"
version = "0.3.0"
requires-python = ">=3.13"
dependencies = ["textual==0.86.2"]
TOML

: >tasker/__init__.py

cat >tasker/store.py <<'PY'
import os
import sqlite3
from pathlib import Path


def db_path() -> Path:
    return Path(os.environ.get("TASKER_DB", Path.home() / ".tasker.db"))


def connect() -> sqlite3.Connection:
    return sqlite3.connect(db_path())
PY

cat >tasker/app.py <<'PY'
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, TabbedContent, TabPane

from tasker.store import connect


class Tasker(App[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Today", id="today"):
                yield DataTable(id="today-table")
            with TabPane("Upcoming", id="upcoming"):
                yield DataTable(id="upcoming-table")
            with TabPane("Calendar", id="calendar"):
                yield DataTable(id="calendar-table")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.load, thread=True)

    def load(self) -> None:
        with connect() as db:
            rows = db.execute("SELECT title, due FROM tasks").fetchall()
        self.call_from_thread(self.query_one("#today-table", DataTable).add_rows, rows)
PY

printf '<svg xmlns="http://www.w3.org/2000/svg"><text>Today</text></svg>\n' >docs/screenshots/today.svg
printf '<svg xmlns="http://www.w3.org/2000/svg"><text>Upcoming</text></svg>\n' >docs/screenshots/upcoming.svg

cat >README.md <<'MD'
# tasker

A terminal todo list.

![Today](docs/screenshots/today.svg)
![Upcoming](docs/screenshots/upcoming.svg)
MD

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
