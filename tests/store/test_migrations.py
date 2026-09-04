"""Migrating a run store that predates a schema change.

`db.connect` applies `schema.sql` with `CREATE TABLE IF NOT EXISTS`, which does nothing
to a table that already exists — so every column and constraint added after the first
release needs its own migration. These tests build a database in the *old* shape, with
real review history in it, and assert that opening it upgrades it without losing
anything.

That matters because the deployed VM carries the only copy of the review history
(`docs/deploy-app-on-server.md`): a migration that silently dropped `proposed_change`
rows would destroy work reviewers had already done, and would do it on a machine where
nobody was watching.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import store
from src.vehicle_class import VehicleClass

#: The `run`/`product` shape as it stood before `vehicle_class` — no such column, and
#: `product`'s unique key over manufacturer/range/model alone. Written out in full rather
#: than generated from an old `schema.sql`, so the test still describes the "before" state
#: once that file has moved on.
_PRE_CARAVAN_SCHEMA = """
CREATE TABLE run (
    id INTEGER PRIMARY KEY,
    manufacturer_id INTEGER NOT NULL,
    fmlv_manufacturer TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK (trigger IN ('manual', 'scheduled')),
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')) DEFAULT 'running',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT,
    range_label TEXT
);
CREATE TABLE product (
    id INTEGER PRIMARY KEY,
    manufacturer_id INTEGER NOT NULL,
    fmlv_product_id INTEGER,
    manufacturer_range TEXT,
    model TEXT,
    first_seen_run_id INTEGER REFERENCES run (id),
    last_seen_run_id INTEGER REFERENCES run (id),
    UNIQUE (manufacturer_id, manufacturer_range, model)
);
CREATE TABLE proposed_change (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    product_id INTEGER NOT NULL REFERENCES product (id),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source_url TEXT,
    source_snippet TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE decision (
    id INTEGER PRIMARY KEY,
    proposed_change_id INTEGER NOT NULL REFERENCES proposed_change (id),
    action TEXT NOT NULL CHECK (action IN ('accept', 'reject', 'correct')),
    corrected_value TEXT,
    decided_by TEXT,
    decided_at TEXT NOT NULL
);
CREATE TABLE verification (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    product_id INTEGER NOT NULL REFERENCES product (id),
    field TEXT NOT NULL,
    verified_at TEXT NOT NULL
);
CREATE TABLE disappearance_notice (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    product_id INTEGER NOT NULL REFERENCES product (id),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE source_snapshot (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT,
    status_code INTEGER
);
"""

#: One Bailey run with a reviewed change, a verification and a disappearance notice —
#: a row in every table that hangs off `product`, so the rebuild has something to lose.
_HISTORY = """
INSERT INTO run VALUES
    (7, 28, 'Bailey', 'manual', 'succeeded', '2026-08-20T09:00:00Z', '2026-08-20T09:05:00Z',
     NULL, NULL);
INSERT INTO product VALUES (11, 28, 4001, 'Adamo', '60-2', 7, 7);
INSERT INTO product VALUES (12, 28, NULL, 'Endeavour', 'B62', 7, 7);
INSERT INTO proposed_change VALUES
    (31, 7, 11, 'rrp_pounds', '61999', '62999', 'https://example.test', 'RRP 62,999',
     0.9, '2026-08-20T09:04:00Z');
INSERT INTO decision VALUES (41, 31, 'accept', NULL, 'Blanca Borbely', '2026-08-20T10:00:00Z');
INSERT INTO verification VALUES (51, 7, 11, 'mh_width_mm', '2026-08-20T09:04:00Z');
INSERT INTO disappearance_notice VALUES
    (61, 7, 12, 'not found on the site', '2026-08-20T09:04:30Z');
"""


@pytest.fixture
def legacy_db(tmp_path: Path) -> Path:
    """A run store in the pre-caravan shape, carrying review history."""
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(_PRE_CARAVAN_SCHEMA)
    connection.executescript(_HISTORY)
    connection.commit()
    connection.close()
    return path


def _table_sql(connection: sqlite3.Connection, name: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    assert row is not None, f"table {name} is missing"
    return str(row["sql"])


def test_connect_backfills_vehicle_class_as_motorhome(legacy_db: Path) -> None:
    """Everything recorded before caravans existed was a motorhome run, and reads as one."""
    connection = store.connect(legacy_db)
    try:
        run = store.get_run(connection, 7)
        products = store.list_products(connection, 28)
    finally:
        connection.close()

    assert run.vehicle_class is VehicleClass.MOTORHOME
    assert [product.vehicle_class for product in products] == [
        VehicleClass.MOTORHOME,
        VehicleClass.MOTORHOME,
    ]


def test_connect_widens_the_product_unique_key(legacy_db: Path) -> None:
    connection = store.connect(legacy_db)
    try:
        sql = _table_sql(connection, "product")
    finally:
        connection.close()

    assert "UNIQUE (manufacturer_id, vehicle_class, manufacturer_range, model)" in sql


def test_the_product_rebuild_keeps_every_child_row(legacy_db: Path) -> None:
    """The reason this migration is written the careful way round.

    `product` is referenced by three tables. Rebuilding it via
    `ALTER TABLE product RENAME TO product_old` — the shortcut the `decision` migration
    can safely use, because nothing references `decision` — would have SQLite rewrite
    those `REFERENCES` clauses to follow the rename, re-pointing all three child tables
    at `product_old` and leaving them dangling once it was dropped.
    """
    connection = store.connect(legacy_db)
    try:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("proposed_change", "decision", "verification", "disappearance_notice")
        }
        references = {
            table: "REFERENCES product " in _table_sql(connection, table)
            for table in ("proposed_change", "verification", "disappearance_notice")
        }
        leftovers = connection.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('product_old', 'product_new')"
        ).fetchall()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    assert counts == {
        "proposed_change": 1,
        "decision": 1,
        "verification": 1,
        "disappearance_notice": 1,
    }
    assert all(references.values()), references
    assert not leftovers
    assert not violations


def test_foreign_keys_are_enforced_on_the_connection_handed_out(legacy_db: Path) -> None:
    """Migrations run with foreign keys off; the caller must never see them that way."""
    connection = store.connect(legacy_db)
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_migrating_twice_changes_nothing(legacy_db: Path) -> None:
    """Every `connect` re-runs the migrations, so they have to be idempotent."""
    first = store.connect(legacy_db)
    first.close()

    connection = store.connect(legacy_db)
    try:
        sql = _table_sql(connection, "product")
        products = connection.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        changes = connection.execute("SELECT COUNT(*) FROM proposed_change").fetchone()[0]
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    assert "UNIQUE (manufacturer_id, vehicle_class, manufacturer_range, model)" in sql
    assert (products, changes) == (2, 1)
    assert not violations


def test_the_widened_key_admits_one_name_in_both_product_areas(legacy_db: Path) -> None:
    """The point of the rebuild: FMLV's two exports may reuse a range/model name."""
    connection = store.connect(legacy_db)
    try:
        connection.execute(
            """
            INSERT INTO product
                (manufacturer_id, fmlv_product_id, manufacturer_range, model, vehicle_class)
            VALUES (28, 9001, 'Adamo', '60-2', 'caravan')
            """
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO product
                    (manufacturer_id, fmlv_product_id, manufacturer_range, model, vehicle_class)
                VALUES (28, 9002, 'Adamo', '60-2', 'caravan')
                """
            )
    finally:
        connection.close()


def test_the_decision_undo_migration_still_runs_alongside(legacy_db: Path) -> None:
    """The legacy fixture predates 'undo' too, so both rebuilds happen in one connect."""
    connection = store.connect(legacy_db)
    try:
        sql = _table_sql(connection, "decision")
        decisions = connection.execute("SELECT COUNT(*) FROM decision").fetchone()[0]
    finally:
        connection.close()

    assert "'undo'" in sql
    assert decisions == 1


def test_the_decision_blank_migration_widens_the_check_and_keeps_history(
    legacy_db: Path,
) -> None:
    """'blank' joins the CHECK on a store that predates it, without losing decisions.

    Added 3 September 2026 with the "Leave blank" review action. The legacy fixture's
    CHECK is `('accept', 'reject', 'correct')`, so this rebuild and the 'undo' one both
    run in a single `connect` — the case worth asserting, since each is idempotent on
    its own marker and a store could be sitting at either point.
    """
    connection = store.connect(legacy_db)
    try:
        sql = _table_sql(connection, "decision")
        assert "'blank'" in sql
        assert "'undo'" in sql
        # The reviewer's real decision is still there, unchanged.
        row = connection.execute(
            "SELECT action, decided_by FROM decision WHERE id = 41"
        ).fetchone()
        assert (row["action"], row["decided_by"]) == ("accept", "Blanca Borbely")

        store.record_decision(
            connection, proposed_change_id=31, action="blank", decided_by="Francis Doyle"
        )
        latest = store.latest_decision(connection, 31)
        assert latest is not None
        assert latest.action == "blank"
        assert latest.corrected_value is None
    finally:
        connection.close()


def test_the_widened_check_still_refuses_an_unknown_action(legacy_db: Path) -> None:
    """Widening the constraint must not amount to removing it."""
    connection = store.connect(legacy_db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO decision (proposed_change_id, action, decided_at)"
                " VALUES (31, 'obliterate', '2026-09-03T00:00:00Z')"
            )
    finally:
        connection.close()


def test_a_store_already_carrying_blank_is_left_alone(legacy_db: Path) -> None:
    """Idempotency, asserted by rowid rather than by count.

    A rebuild that ran a second time would copy every row into a fresh table; the ids
    survive that, so this also records a `blank` decision first and checks it is the
    same row afterwards.
    """
    connection = store.connect(legacy_db)
    try:
        recorded = store.record_decision(
            connection, proposed_change_id=31, action="blank", decided_by="Francis Doyle"
        )
    finally:
        connection.close()

    connection = store.connect(legacy_db)
    try:
        again = store.get_decision(connection, recorded.id)
        assert (again.action, again.decided_by) == ("blank", "Francis Doyle")
        assert connection.execute("SELECT COUNT(*) FROM decision").fetchone()[0] == 2
    finally:
        connection.close()
