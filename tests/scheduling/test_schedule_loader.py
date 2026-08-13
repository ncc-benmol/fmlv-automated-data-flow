"""Tests for the schedule CSV loader."""

from __future__ import annotations

import csv
from pathlib import Path

from src import scheduling

_COLUMNS = (
    "schedule_id",
    "manufacturer_id",
    "ranges",
    "first_run",
    "frequency_value",
    "frequency_unit",
    "enabled",
    "notes",
)

REAL_SCHEDULE = Path(__file__).parents[2] / "config" / "schedule.csv"


def write_schedule(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "schedule.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in _COLUMNS})
    return path


def minimal_row(**overrides: str) -> dict[str, str]:
    row = {
        "schedule_id": "adria-weekly",
        "manufacturer_id": "3",
        "first_run": "2026-08-15 03:00",
        "frequency_value": "7",
        "frequency_unit": "days",
        "enabled": "true",
    }
    row.update(overrides)
    return row


def test_loads_a_minimal_valid_row(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row()])
    result = scheduling.load(path)

    assert result.issues == []
    [entry] = result.entries
    assert entry.schedule_id == "adria-weekly"
    assert entry.manufacturer_id == 3
    assert entry.ranges == ()
    assert entry.enabled is True
    assert entry.frequency_value == 7
    assert entry.frequency_unit == scheduling.FrequencyUnit.DAYS


def test_ranges_split_on_comma(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row(ranges="Matrix, Sonic")])
    [entry] = scheduling.load(path).entries
    assert entry.ranges == ("Matrix", "Sonic")


def test_disabled_row_still_loads(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row(enabled="false")])
    [entry] = scheduling.load(path).entries
    assert entry.enabled is False


def test_missing_manufacturer_id_is_an_error(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row(manufacturer_id="")])
    result = scheduling.load(path)
    assert result.entries == []
    assert any(issue.code == "missing_manufacturer_id" for issue in result.issues)


def test_invalid_first_run_is_an_error(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row(first_run="not-a-date")])
    result = scheduling.load(path)
    assert result.entries == []
    assert any(issue.code == "invalid_first_run" for issue in result.issues)


def test_non_positive_frequency_value_is_an_error(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row(frequency_value="0")])
    result = scheduling.load(path)
    assert result.entries == []
    assert any(issue.code == "invalid_frequency_value" for issue in result.issues)


def test_unknown_frequency_unit_is_an_error(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row(frequency_unit="fortnights")])
    result = scheduling.load(path)
    assert result.entries == []
    assert any(issue.code == "invalid_frequency_unit" for issue in result.issues)


def test_duplicate_schedule_id_is_an_error(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [minimal_row(), minimal_row()])
    result = scheduling.load(path)
    assert len(result.entries) == 1
    assert any(issue.code == "duplicate_schedule_id" for issue in result.issues)


def test_blank_row_is_silently_skipped(tmp_path: Path) -> None:
    path = write_schedule(tmp_path, [{}])
    result = scheduling.load(path)
    assert result.entries == []
    assert result.issues == []


def test_real_schedule_csv_loads_cleanly() -> None:
    result = scheduling.load(REAL_SCHEDULE)
    errors = [issue for issue in result.issues if issue.severity == "error"]
    assert errors == []
    assert result.entries
