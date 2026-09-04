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

Constraints need more than that — SQLite can't alter a CHECK or UNIQUE clause at all, so
changing one means rebuilding the table. `_migrate_decision_undo_action` and
`_migrate_product_vehicle_class_unique_key` are those rebuilds, and both matter because
real review history already exists on the deployed VM.
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

_SCHEMA_SQL = resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")

#: (table, column, type) added to `schema.sql` after the table itself already shipped.
_ADDED_COLUMNS = [
    ("run", "range_label", "TEXT"),
    ("run", "vehicle_class", "TEXT NOT NULL DEFAULT 'motorhome'"),
    ("product", "vehicle_class", "TEXT NOT NULL DEFAULT 'motorhome'"),
]


def _apply_column_migrations(connection: sqlite3.Connection) -> None:
    for table, column, column_type in _ADDED_COLUMNS:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _migrate_decision_undo_action(connection: sqlite3.Connection) -> None:
    """Rebuild `decision` if its CHECK constraint predates the "undo" action.

    SQLite has no `ALTER TABLE` for CHECK constraints, so widening one means
    rebuilding the table — done idempotently by checking its current
    `CREATE TABLE` text first, and done at all (rather than leaving it to a
    fresh `schema.sql`) because real run history already exists in it.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'decision'"
    ).fetchone()
    if row is None or "'undo'" in row["sql"]:
        return
    connection.executescript(
        """
        ALTER TABLE decision RENAME TO decision_old;
        CREATE TABLE decision (
            id INTEGER PRIMARY KEY,
            proposed_change_id INTEGER NOT NULL REFERENCES proposed_change (id),
            action TEXT NOT NULL CHECK (action IN ('accept', 'reject', 'correct', 'undo')),
            corrected_value TEXT,
            decided_by TEXT,
            decided_at TEXT NOT NULL
        );
        INSERT INTO decision SELECT * FROM decision_old;
        DROP TABLE decision_old;
        CREATE INDEX IF NOT EXISTS idx_decision_proposed_change ON decision (proposed_change_id);
        """
    )


def _migrate_decision_blank_action(connection: sqlite3.Connection) -> None:
    """Rebuild `decision` if its CHECK constraint predates the "blank" action.

    Same shape and same reason as `_migrate_decision_undo_action` — SQLite has no
    `ALTER TABLE` for a CHECK constraint, so widening one means rebuilding the table,
    and it has to be done here rather than left to a fresh `schema.sql` because the
    deployed run store holds real review history.

    Kept as a second function rather than folded into the "undo" one so each migration
    stays idempotent on its own marker: a store created after "undo" shipped but before
    "blank" did needs exactly this one and not that one.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'decision'"
    ).fetchone()
    if row is None or "'blank'" in row["sql"]:
        return
    connection.executescript(
        """
        ALTER TABLE decision RENAME TO decision_old;
        CREATE TABLE decision (
            id INTEGER PRIMARY KEY,
            proposed_change_id INTEGER NOT NULL REFERENCES proposed_change (id),
            action TEXT NOT NULL
                CHECK (action IN ('accept', 'reject', 'correct', 'blank', 'undo')),
            corrected_value TEXT,
            decided_by TEXT,
            decided_at TEXT NOT NULL
        );
        INSERT INTO decision SELECT * FROM decision_old;
        DROP TABLE decision_old;
        CREATE INDEX IF NOT EXISTS idx_decision_proposed_change ON decision (proposed_change_id);
        """
    )


def _migrate_product_vehicle_class_unique_key(connection: sqlite3.Connection) -> None:
    """Widen `product`'s unique key to include `vehicle_class`.

    `_apply_column_migrations` can add the column but not change the constraint, and
    SQLite has no `ALTER TABLE` for one — so this rebuilds the table, idempotently, by
    checking the current `CREATE TABLE` text first.

    The rebuild goes via a new table rather than `ALTER TABLE ... RENAME TO product_old`
    the way `_migrate_decision_undo_action` does. That shortcut is safe for `decision`
    because nothing references it; `product` is referenced by `proposed_change`,
    `verification` and `disappearance_notice`, and a modern SQLite rewrites those
    `REFERENCES` clauses to follow a rename — which would silently re-point every child
    table at `product_old` and then leave them dangling when it was dropped.

    Foreign keys must be off for the drop-and-rename, which `connect` arranges by running
    every migration before enabling them.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'product'"
    ).fetchone()
    if row is None or "vehicle_class, manufacturer_range" in row["sql"]:
        return

    connection.executescript(
        """
        CREATE TABLE product_new (
            id INTEGER PRIMARY KEY,
            manufacturer_id INTEGER NOT NULL,
            fmlv_product_id INTEGER,
            manufacturer_range TEXT,
            model TEXT,
            first_seen_run_id INTEGER REFERENCES run (id),
            last_seen_run_id INTEGER REFERENCES run (id),
            vehicle_class TEXT NOT NULL DEFAULT 'motorhome',
            UNIQUE (manufacturer_id, vehicle_class, manufacturer_range, model)
        );
        INSERT INTO product_new
            (id, manufacturer_id, fmlv_product_id, manufacturer_range, model,
             first_seen_run_id, last_seen_run_id, vehicle_class)
        SELECT id, manufacturer_id, fmlv_product_id, manufacturer_range, model,
               first_seen_run_id, last_seen_run_id, vehicle_class
        FROM product;
        DROP TABLE product;
        ALTER TABLE product_new RENAME TO product;
        CREATE INDEX IF NOT EXISTS idx_product_fmlv_id ON product (fmlv_product_id);
        """
    )


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the run store, creating the schema if it doesn't exist yet."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    # Migrations run with foreign keys still off (SQLite's default), because
    # `_migrate_product_vehicle_class_unique_key` drops and replaces a table three others
    # reference. Enabled immediately afterwards, before the connection is handed out.
    connection.executescript(_SCHEMA_SQL)
    _apply_column_migrations(connection)
    _migrate_decision_undo_action(connection)
    _migrate_decision_blank_action(connection)
    _migrate_product_vehicle_class_unique_key(connection)
    connection.commit()
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
