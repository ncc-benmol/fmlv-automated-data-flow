"""SQLite connection management for the run store.

One file, opened with foreign keys enforced and rows returned as `sqlite3.Row` so
callers can access columns by name. The schema (`schema.sql`) is applied idempotently
on every connect via `CREATE TABLE IF NOT EXISTS` — there is no separate migration
step yet. That's fine while the schema is still settling; once real run history
exists, evolving it will need a proper migration (see TODO.md).

`_ADDED_COLUMNS` is the one exception: `CREATE TABLE IF NOT EXISTS` doesn't add columns
to a table that already exists, so a column added to `schema.sql` after a database was
first created needs its own `ALTER TABLE`, applied idempotently by checking
`PRAGMA table_info` first (SQLite has no `ADD COLUMN IF NOT EXISTS`).
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

_SCHEMA_SQL = resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")

#: (table, column, type) added to `schema.sql` after the table itself already shipped.
_ADDED_COLUMNS = [
    ("run", "range_label", "TEXT"),
]


def _apply_column_migrations(connection: sqlite3.Connection) -> None:
    for table, column, column_type in _ADDED_COLUMNS:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the run store, creating the schema if it doesn't exist yet."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA_SQL)
    _apply_column_migrations(connection)
    connection.commit()
    return connection
