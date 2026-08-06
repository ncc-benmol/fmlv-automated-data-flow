"""Tests for the run store: schema creation and the run lifecycle."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import store


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = store.connect(tmp_path / "runs.db")
    try:
        yield conn
    finally:
        conn.close()


def test_connect_creates_every_table(connection: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert tables >= {
        "run",
        "source_snapshot",
        "product",
        "proposed_change",
        "decision",
        "verification",
    }


def test_connect_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "runs.db"
    first = store.connect(db_path)
    store.start_run(first, manufacturer_id=1, fmlv_manufacturer="Adria Mobil", trigger="manual")
    first.close()

    # Reconnecting must not wipe or fail on the existing schema/data.
    second = store.connect(db_path)
    try:
        assert len(store.list_runs(second)) == 1
    finally:
        second.close()


def test_start_run_records_running_status(connection: sqlite3.Connection) -> None:
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    assert run.status == "running"
    assert run.finished_at is None
    assert run.error_message is None
    assert run.trigger == "manual"


def test_finish_run_marks_succeeded(connection: sqlite3.Connection) -> None:
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    finished = store.finish_run(connection, run.id)
    assert finished.status == "succeeded"
    assert finished.finished_at is not None


def test_fail_run_records_error_message(connection: sqlite3.Connection) -> None:
    run = store.start_run(
        connection, manufacturer_id=46, fmlv_manufacturer="Morelo", trigger="scheduled"
    )
    failed = store.fail_run(connection, run.id, "site returned 503")
    assert failed.status == "failed"
    assert failed.error_message == "site returned 503"
    assert failed.finished_at is not None


def test_get_run_raises_for_unknown_id(connection: sqlite3.Connection) -> None:
    with pytest.raises(KeyError):
        store.get_run(connection, 999)


def test_list_runs_orders_most_recent_first(connection: sqlite3.Connection) -> None:
    first = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    second = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="scheduled"
    )
    runs = store.list_runs(connection, manufacturer_id=3)
    assert [run.id for run in runs] == [second.id, first.id]


def test_list_runs_filters_by_manufacturer(connection: sqlite3.Connection) -> None:
    store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    store.start_run(connection, manufacturer_id=46, fmlv_manufacturer="Morelo", trigger="manual")

    adria_runs = store.list_runs(connection, manufacturer_id=3)
    assert len(adria_runs) == 1
    assert adria_runs[0].fmlv_manufacturer == "Adria Mobil"


def test_invalid_trigger_is_rejected_by_the_schema(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO run (manufacturer_id, fmlv_manufacturer, trigger, status, started_at)
            VALUES (1, 'Adria Mobil', 'not_a_real_trigger', 'running', '2026-01-01T00:00:00')
            """
        )
