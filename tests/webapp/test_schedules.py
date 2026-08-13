"""Tests for the `/schedules` page and the scheduler's due-run check."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import paths, store
from src.webapp import create_app
from src.webapp.app import check_schedule


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    # Must be `paths.db_path(root=...)`'s own filename, not an arbitrary one:
    # `execute_run` (called by `check_schedule`) always connects to
    # `paths.db_path(root=data_root)`, where `data_root = db_path.parent` — so this
    # is the one path `execute_run` will actually write runs to.
    return paths.db_path(root=tmp_path)


def write_registry(db_path: Path) -> None:
    (db_path.parent / "manufacturers.csv").write_text(
        "manufacturer_id,fmlv_manufacturer,website_url\n3,Adria Mobil,https://example.invalid/\n",
        encoding="utf-8",
    )


def write_schedule(db_path: Path, rows_csv: str) -> None:
    header = "schedule_id,manufacturer_id,ranges,first_run,frequency_value,frequency_unit,enabled,notes\n"
    (db_path.parent / "schedule.csv").write_text(header + rows_csv, encoding="utf-8")


@pytest.fixture
def client(db_path: Path) -> TestClient:
    write_registry(db_path)
    return TestClient(
        create_app(
            db_path,
            registry_path=db_path.parent / "manufacturers.csv",
            reviewers_path=db_path.parent / "reviewers.csv",
            schedule_path=db_path.parent / "schedule.csv",
            enable_scheduler=False,
        )
    )


def test_schedules_page_empty_with_no_file(client: TestClient, db_path: Path) -> None:
    write_schedule(db_path, "")
    response = client.get("/schedules")
    assert response.status_code == 200
    assert "No schedule entries yet" in response.text


def test_schedules_page_lists_a_row(client: TestClient, db_path: Path) -> None:
    write_schedule(
        db_path,
        "adria-weekly,3,,2020-01-01 00:00,7,days,true,\n",
    )
    response = client.get("/schedules")
    assert response.status_code == 200
    assert "adria-weekly" in response.text
    assert "Adria Mobil" in response.text
    assert "All ranges" in response.text
    assert "every 7 days" in response.text


def test_schedules_page_flags_paused_row(client: TestClient, db_path: Path) -> None:
    write_schedule(
        db_path,
        "adria-weekly,3,,2020-01-01 00:00,7,days,false,\n",
    )
    response = client.get("/schedules")
    assert "paused" in response.text


def test_schedules_page_flags_unknown_manufacturer(client: TestClient, db_path: Path) -> None:
    write_schedule(
        db_path,
        "ghost,999,,2020-01-01 00:00,7,days,true,\n",
    )
    response = client.get("/schedules")
    assert "no manufacturer_id 999" in response.text


def test_check_schedule_triggers_a_due_entry(client: TestClient, db_path: Path) -> None:
    # No NCC credentials/network in this test — `execute_run`'s `refresh_export`
    # fetch will fail, but a `run` row is created and marked 'failed' *before* that
    # happens, which is enough to prove the schedule fired (the scrape/browser path
    # itself is exercised by test_cli.py, not here).
    write_schedule(
        db_path,
        "adria-weekly,3,,2020-01-01 00:00,7,days,true,\n",
    )
    app = client.app

    check_schedule(app)

    connection = store.connect(db_path)
    try:
        runs = store.list_runs(connection, manufacturer_id=3)
    finally:
        connection.close()
    assert runs
    assert runs[0].trigger == "scheduled"


def test_check_schedule_skips_disabled_entry(client: TestClient, db_path: Path) -> None:
    write_schedule(
        db_path,
        "adria-weekly,3,,2020-01-01 00:00,7,days,false,\n",
    )
    app = client.app
    triggered = check_schedule(app)
    assert triggered == []
    connection = store.connect(db_path)
    try:
        runs = store.list_runs(connection, manufacturer_id=3)
    finally:
        connection.close()
    assert runs == []


def test_check_schedule_skips_not_yet_due_entry(client: TestClient, db_path: Path) -> None:
    future = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    write_schedule(
        db_path,
        f"adria-weekly,3,,{future},7,days,true,\n",
    )
    app = client.app
    triggered = check_schedule(app)
    assert triggered == []


def test_check_schedule_skips_manufacturer_already_running(
    client: TestClient, db_path: Path
) -> None:
    write_schedule(
        db_path,
        "adria-weekly,3,,2020-01-01 00:00,7,days,true,\n",
    )
    connection = store.connect(db_path)
    store.start_run(connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual")
    connection.close()

    app = client.app
    triggered = check_schedule(app)
    assert triggered == []
