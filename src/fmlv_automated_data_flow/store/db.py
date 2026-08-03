"""SQLite connection management for the run store.

One file, opened with foreign keys enforced and rows returned as `sqlite3.Row` so
callers can access columns by name. The schema (`schema.sql`) is applied idempotently
on every connect via `CREATE TABLE IF NOT EXISTS` — there is no separate migration
step yet. That's fine while the schema is still settling; once real run history
exists, evolving it will need a proper migration (see TODO.md).
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

_SCHEMA_SQL = resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the run store, creating the schema if it doesn't exist yet."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA_SQL)
    connection.commit()
    return connection
