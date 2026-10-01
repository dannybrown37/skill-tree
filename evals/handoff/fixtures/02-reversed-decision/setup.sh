#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../_lib.sh
source "$(dirname "$0")/../_lib.sh"

repo="$1/notes-cli"
init_repo "${repo}" "feat/sqlite-store"
mkdir -p "${repo}/src/notes" "${repo}/tests" "${repo}/scripts"

cat >"${repo}/pyproject.toml" <<'EOF'
[project]
name = "notes-cli"
version = "1.2.0"
requires-python = ">=3.11"
dependencies = ["click==8.1.7"]
EOF

cat >"${repo}/src/notes/store.py" <<'EOF'
import json
from pathlib import Path


class JsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def add(self, note: dict) -> None:
        notes = self.all()
        notes.append(note)
        self.path.write_text(json.dumps(notes, indent=2))
EOF

cat >"${repo}/src/notes/export.py" <<'EOF'
def to_csv(notes: list[dict]) -> str:
    lines = ["id,title,tags"]
    for n in notes:
        lines.append(f'{n["id"]},{n["title"]},{";".join(n["tags"])}')
    return "\n".join(lines)
EOF

commit "${repo}" "2026-09-22T14:00:00Z" "feat: json store and csv export"

cat >"${repo}/src/notes/sqlite_store.py" <<'EOF'
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS note_tags (
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (note_id, tag)
);
"""


def default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "notes" / "notes.db"


class SqliteStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def all(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, title, body FROM notes").fetchall()
        out = []
        for note_id, title, body in rows:
            tags = [
                t
                for (t,) in self.conn.execute(
                    "SELECT tag FROM note_tags WHERE note_id = ?", (note_id,)
                )
            ]
            out.append({"id": note_id, "title": title, "body": body, "tags": tags})
        return out

    def add(self, note: dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO notes (id, title, body) VALUES (?, ?, ?)",
                (note["id"], note["title"], note.get("body", "")),
            )
            self.conn.executemany(
                "INSERT INTO note_tags (note_id, tag) VALUES (?, ?)",
                [(note["id"], t) for t in note.get("tags", [])],
            )
EOF

cat >"${repo}/tests/test_store.py" <<'EOF'
from pathlib import Path

from notes.sqlite_store import SqliteStore


def test_roundtrip_with_comma_tag(tmp_path: Path) -> None:
    s = SqliteStore(tmp_path / "n.db")
    s.add({"id": "1", "title": "t", "tags": ["a,b", "c"]})
    assert sorted(s.all()[0]["tags"]) == ["a,b", "c"]
EOF

commit "${repo}" "2026-09-23T16:30:00Z" "feat: SqliteStore with note_tags join table"

cat >"${repo}/scripts/migrate_json.py" <<'EOF'
import json
import sys
from pathlib import Path

from notes.sqlite_store import SqliteStore, default_db_path


def main(json_path: Path) -> None:
    notes = json.loads(json_path.read_text())
    store = SqliteStore(default_db_path())
    with store.conn:
        for n in notes:
            store.conn.execute(
                "INSERT INTO notes (id, title, body) VALUES (?, ?, ?)",
                (n["id"], n["title"], n.get("body", "")),
            )
            # TODO: tags


if __name__ == "__main__":
    main(Path(sys.argv[1]))
EOF
