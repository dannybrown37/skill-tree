**User:** I want to move notes-cli off the JSON file and onto SQLite. The JSON file gets slow past a few thousand notes and I keep hitting write races. Branch `feat/sqlite-store` is ready.

**Assistant:** Makes sense. My proposal: use SQLAlchemy Core for the schema and queries, which buys us migrations via Alembic later.

**User:** No ORM, no SQLAlchemy. stdlib `sqlite3` only. This is a tiny CLI and I don't want the dependency.

**Assistant:** Got it, stdlib `sqlite3`. To keep the transition safe, I suggest keeping both backends behind a small `Store` protocol, selected by a `--backend json|sqlite` flag. That way users can switch back if something goes wrong.

**User:** Sure, sounds reasonable.

**Assistant:** Starting with the schema. For tags, the simplest option is a `tags TEXT` column holding a comma-separated list.

> Wrote `src/notes/sqlite_store.py` with `notes(id, title, body, tags)`, tags joined by `,`
>
> Wrote `tests/test_store.py::test_roundtrip_with_comma_tag`
>
> `$ uv run pytest tests/test_store.py -q`
> ```
> F
> E   AssertionError: assert ['a', 'b', 'c'] == ['a,b', 'c']
> ```

Comma-separated tags break as soon as a tag contains a comma, and the existing JSON data does have tags like `"q3,planning"`. **Abandoning the comma-separated column** for a proper `note_tags(note_id, tag)` join table with `ON DELETE CASCADE`.

> Rewrote `src/notes/sqlite_store.py` with `notes` + `note_tags` tables, `PRAGMA foreign_keys = ON`
>
> `$ uv run pytest tests/test_store.py -q`
> ```
> 1 passed in 0.04s
> ```

Next, the DB location. I put it next to the JSON file at first, which on your machine is `/mnt/c/Users/.../notes/`.

> `$ uv run notes add "hello" --backend sqlite`
> ```
> sqlite3.OperationalError: database is locked
> ```

That's a known WSL problem: SQLite file locking doesn't work reliably on the `/mnt/c` (9p/drvfs) filesystem. **The DB must live on the Linux filesystem.** I moved the default to `~/.local/share/notes/notes.db` (`default_db_path()`).

> `$ uv run notes add "hello" --backend sqlite && uv run notes list --backend sqlite`
> ```
> 1  hello
> ```

**User:** Good. Commit that bit.

> `$ git add -A && git commit -m "feat: SqliteStore with note_tags join table"`
> ```
> [feat/sqlite-store 3f1a2c0] feat: SqliteStore with note_tags join table
> ```

**Assistant:** Committed. Now the `Store` protocol and `--backend` flag wiring in `cli.py`...

**User:** Actually, wait. I've changed my mind on the flag. Supporting two backends forever is exactly what I don't want. Plan is: one-time migration script, then SQLite is the only backend. Rip out JsonStore once the migration is done. No `--backend` flag.

**Assistant:** Understood, that simplifies things:

- No `Store` protocol and no `--backend` flag.
- `scripts/migrate_json.py` does a one-time copy from `notes.json` into SQLite.
- After that, delete `JsonStore` and point the CLI at `SqliteStore` directly.

I hadn't written the protocol yet, so there's nothing to revert. Starting on the migration script.

> Wrote `scripts/migrate_json.py`: reads the JSON and inserts rows into `notes`. Tags are not migrated yet (left a `# TODO: tags` at the insert loop).

While checking the JSON shape I opened `export.py` and noticed that `to_csv` doesn't quote fields, so a title containing a comma or a quote produces a broken CSV. It's the same comma problem as before, in a different place.

**User:** Ugh. Not this PR. Park it for later.

**Assistant:** Parked. One question on the migration: after a successful migration, should the script delete `notes.json`, rename it to `notes.json.bak`, or leave it alone?

**User:** Hmm. Not sure yet. I'll decide tomorrow, don't pick one for me.

**Assistant:** Okay. The script won't touch `notes.json` until you decide.

**User:** I have to go. Write a handoff so we can continue tomorrow.
