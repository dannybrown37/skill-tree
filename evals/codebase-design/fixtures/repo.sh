#!/usr/bin/env bash
# userstore.py is a pass-through: every method wraps one sqlite3 call, so
# all three callers repeat the same connect/query/parse/close dance.
set -euo pipefail

cat >userstore.py <<'EOF2'
import sqlite3


class UserStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        self.connection = sqlite3.connect(self.path)

    def build_select(self, where: str) -> str:
        return f"SELECT id, email, active FROM users WHERE {where}"

    def execute(self, sql: str, params: tuple) -> list[tuple]:
        assert self.connection is not None
        return self.connection.execute(sql, params).fetchall()

    def parse_rows(self, rows: list[tuple]) -> list[dict]:
        return [{"id": r[0], "email": r[1], "active": bool(r[2])} for r in rows]

    def close(self) -> None:
        assert self.connection is not None
        self.connection.close()
EOF2

cat >signup.py <<'EOF2'
from userstore import UserStore


def email_taken(db_path: str, email: str) -> bool:
    store = UserStore(db_path)
    store.connect()
    rows = store.execute(store.build_select("email = ?"), (email,))
    store.close()
    return bool(store.parse_rows(rows))
EOF2

cat >admin.py <<'EOF2'
from userstore import UserStore


def active_users(db_path: str) -> list[dict]:
    store = UserStore(db_path)
    store.connect()
    rows = store.execute(store.build_select("active = ?"), (1,))
    users = store.parse_rows(rows)
    store.close()
    return users
EOF2

cat >login.py <<'EOF2'
from userstore import UserStore


def find_user(db_path: str, email: str) -> dict | None:
    store = UserStore(db_path)
    store.connect()
    rows = store.execute(store.build_select("email = ? AND active = 1"), (email,))
    store.close()
    users = store.parse_rows(rows)
    return users[0] if users else None
EOF2

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
