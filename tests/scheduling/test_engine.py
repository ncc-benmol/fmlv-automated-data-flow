"""Tests for `scheduling.engine`: working out what's due to run."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src import scheduling, store
from src.adapters import adria
from src.scheduling.models import LOCAL_TZ, FrequencyUnit, ScheduleEntry


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = store.connect(tmp_path / "runs.db")
    try:
        yield conn
    finally:
        conn.close()


def make_entry(**overrides: object) -> ScheduleEntry:
    fields: dict[str, object] = {
        "schedule_id": "adria-weekly",
        "manufacturer_id": 3,
        "ranges": (),
        "first_run": datetime(2026, 8, 1, 3, 0, tzinfo=LOCAL_TZ),
        "frequency_value": 7,
        "frequency_unit": FrequencyUnit.DAYS,
        "enabled": True,
        "notes": None,
    }
    fields.update(overrides)
    return ScheduleEntry(**fields)


def test_never_run_is_due_at_first_run(connection: sqlite3.Connection) -> None:
    entry = make_entry(first_run=datetime(2026, 8, 1, 3, 0, tzinfo=LOCAL_TZ))
    due_at = scheduling.next_due_at(entry, range_label=None, connection=connection)
    assert due_at == datetime(2026, 8, 1, 3, 0, tzinfo=LOCAL_TZ).astimezone(UTC)


def test_not_due_before_first_run(connection: sqlite3.Connection) -> None:
    entry = make_entry(first_run=datetime(2099, 1, 1, 0, 0, tzinfo=LOCAL_TZ))
    assert not scheduling.is_due(entry, range_label=None, connection=connection)


def test_due_after_first_run(connection: sqlite3.Connection) -> None:
    entry = make_entry(first_run=datetime(2020, 1, 1, 0, 0, tzinfo=LOCAL_TZ))
    assert scheduling.is_due(entry, range_label=None, connection=connection)


def test_disabled_entry_is_never_due(connection: sqlite3.Connection) -> None:
    entry = make_entry(first_run=datetime(2020, 1, 1, 0, 0, tzinfo=LOCAL_TZ), enabled=False)
    assert not scheduling.is_due(entry, range_label=None, connection=connection)


def test_next_due_derives_from_last_scheduled_run(connection: sqlite3.Connection) -> None:
    entry = make_entry(
        first_run=datetime(2020, 1, 1, 0, 0, tzinfo=LOCAL_TZ),
        frequency_value=1,
        frequency_unit=FrequencyUnit.DAYS,
    )
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="scheduled"
    )
    started = datetime.fromisoformat(run.started_at)
    due_at = scheduling.next_due_at(entry, range_label=None, connection=connection)
    assert due_at == started + timedelta(days=1)
    # Not due yet — the last scheduled run was seconds ago, not a day ago.
    assert not scheduling.is_due(entry, range_label=None, connection=connection)


def test_manual_runs_do_not_count_as_the_last_scheduled_run(
    connection: sqlite3.Connection,
) -> None:
    entry = make_entry(first_run=datetime(2020, 1, 1, 0, 0, tzinfo=LOCAL_TZ))
    store.start_run(connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual")
    # A manual run doesn't satisfy the schedule — still due at first_run.
    due_at = scheduling.next_due_at(entry, range_label=None, connection=connection)
    assert due_at == entry.first_run.astimezone(UTC)


def test_range_label_matches_only_the_same_range(connection: sqlite3.Connection) -> None:
    entry = make_entry(first_run=datetime(2020, 1, 1, 0, 0, tzinfo=LOCAL_TZ))
    store.start_run(
        connection,
        manufacturer_id=3,
        fmlv_manufacturer="Adria Mobil",
        trigger="scheduled",
        range_label="Matrix",
    )
    # entry has no ranges (whole manufacturer, range_label=None) — the "Matrix" run
    # above shouldn't be picked up as satisfying it.
    due_at = scheduling.next_due_at(entry, range_label=None, connection=connection)
    assert due_at == entry.first_run.astimezone(UTC)


def test_resolved_range_label_matches_execute_run_convention() -> None:
    entry = make_entry(ranges=("Matrix",))
    assert scheduling.engine.resolved_range_label(entry, adria) == "Matrix"


def test_resolved_range_label_none_for_whole_manufacturer() -> None:
    entry = make_entry(ranges=())
    assert scheduling.engine.resolved_range_label(entry, adria) is None


def test_describe_reports_error_for_unknown_range(connection: sqlite3.Connection) -> None:
    entry = make_entry(ranges=("Not A Real Range",))
    status = scheduling.describe(entry, adapter=adria, connection=connection)
    assert status.error is not None
    assert status.is_due is False


def test_has_run_in_progress(connection: sqlite3.Connection) -> None:
    assert not scheduling.has_run_in_progress(connection, manufacturer_id=3)
    store.start_run(connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual")
    assert scheduling.has_run_in_progress(connection, manufacturer_id=3)
