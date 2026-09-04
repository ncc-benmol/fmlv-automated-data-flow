"""Loading `config/schedule.csv`.

Mirrors `registry.loader`'s approach: a bad row is reported as an `Issue`, not
raised, so one malformed schedule entry doesn't stop every other one from loading.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..vehicle_class import DEFAULT as DEFAULT_VEHICLE_CLASS
from ..vehicle_class import VehicleClass
from .models import FrequencyUnit, LOCAL_TZ, ScheduleEntry

Severity = Literal["error", "warning"]

#: `first_run` is written by hand as a UK wall-clock time, no timezone offset.
_FIRST_RUN_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M")


@dataclass(frozen=True)
class Issue:
    """One problem found while loading the schedule."""

    severity: Severity
    code: str
    message: str
    row_number: int  # 1-indexed; row 1 is the header, so data starts at 2
    schedule_id: str | None = None


@dataclass
class LoadResult:
    entries: list[ScheduleEntry] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _split_ranges(value: str | None) -> tuple[str, ...]:
    text = _clean(value)
    if text is None:
        return ()
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _parse_first_run(text: str) -> datetime | None:
    for fmt in _FIRST_RUN_FORMATS:
        try:
            naive = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=LOCAL_TZ)
    return None


def _row_to_entry(row: dict[str, str], row_number: int) -> tuple[ScheduleEntry | None, list[Issue]]:
    schedule_id = _clean(row.get("schedule_id"))
    if schedule_id is None and not any(_clean(v) for v in row.values()):
        return None, []  # a fully blank row — skip silently, same as manufacturers.csv

    issues: list[Issue] = []

    if schedule_id is None:
        issues.append(
            Issue(
                severity="error",
                code="missing_schedule_id",
                message="schedule_id is required",
                row_number=row_number,
            )
        )

    manufacturer_id_text = _clean(row.get("manufacturer_id"))
    manufacturer_id: int | None = None
    if manufacturer_id_text is None:
        issues.append(
            Issue(
                severity="error",
                code="missing_manufacturer_id",
                message="manufacturer_id is required",
                row_number=row_number,
                schedule_id=schedule_id,
            )
        )
    else:
        try:
            manufacturer_id = int(manufacturer_id_text)
        except ValueError:
            issues.append(
                Issue(
                    severity="error",
                    code="invalid_manufacturer_id",
                    message=f"manufacturer_id {manufacturer_id_text!r} is not an integer",
                    row_number=row_number,
                    schedule_id=schedule_id,
                )
            )

    first_run_text = _clean(row.get("first_run"))
    first_run: datetime | None = None
    if first_run_text is None:
        issues.append(
            Issue(
                severity="error",
                code="missing_first_run",
                message="first_run is required",
                row_number=row_number,
                schedule_id=schedule_id,
            )
        )
    else:
        first_run = _parse_first_run(first_run_text)
        if first_run is None:
            issues.append(
                Issue(
                    severity="error",
                    code="invalid_first_run",
                    message=(
                        f"first_run {first_run_text!r} doesn't match YYYY-MM-DD HH:MM"
                    ),
                    row_number=row_number,
                    schedule_id=schedule_id,
                )
            )

    frequency_value_text = _clean(row.get("frequency_value"))
    frequency_value: int | None = None
    if frequency_value_text is None:
        issues.append(
            Issue(
                severity="error",
                code="missing_frequency_value",
                message="frequency_value is required",
                row_number=row_number,
                schedule_id=schedule_id,
            )
        )
    else:
        try:
            frequency_value = int(frequency_value_text)
        except ValueError:
            frequency_value = None
        if frequency_value is None or frequency_value <= 0:
            issues.append(
                Issue(
                    severity="error",
                    code="invalid_frequency_value",
                    message=f"frequency_value {frequency_value_text!r} must be a positive integer",
                    row_number=row_number,
                    schedule_id=schedule_id,
                )
            )
            frequency_value = None

    frequency_unit_text = (_clean(row.get("frequency_unit")) or "").lower()
    frequency_unit: FrequencyUnit | None = None
    try:
        frequency_unit = FrequencyUnit(frequency_unit_text) if frequency_unit_text else None
    except ValueError:
        frequency_unit = None
    if frequency_unit is None:
        known = ", ".join(unit.value for unit in FrequencyUnit)
        issues.append(
            Issue(
                severity="error",
                code="invalid_frequency_unit",
                message=f"frequency_unit {frequency_unit_text!r} must be one of: {known}",
                row_number=row_number,
                schedule_id=schedule_id,
            )
        )

    enabled_text = (_clean(row.get("enabled")) or "").lower()
    if enabled_text in {"true", "yes", "1"}:
        enabled = True
    elif enabled_text in {"false", "no", "0"}:
        enabled = False
    else:
        issues.append(
            Issue(
                severity="warning",
                code="unknown_enabled",
                message=f"enabled {enabled_text!r} not recognised, treating as false",
                row_number=row_number,
                schedule_id=schedule_id,
            )
        )
        enabled = False

    vehicle_class_text = (_clean(row.get("vehicle_class")) or "").lower()
    if not vehicle_class_text:
        vehicle_class = DEFAULT_VEHICLE_CLASS
    else:
        try:
            vehicle_class = VehicleClass(vehicle_class_text)
        except ValueError:
            issues.append(
                Issue(
                    severity="warning",
                    code="unknown_vehicle_class",
                    message=(
                        f"vehicle_class {vehicle_class_text!r} not recognised, treating as "
                        f"{DEFAULT_VEHICLE_CLASS.value!r}"
                    ),
                    row_number=row_number,
                    schedule_id=schedule_id,
                )
            )
            vehicle_class = DEFAULT_VEHICLE_CLASS

    if (
        schedule_id is None
        or manufacturer_id is None
        or first_run is None
        or frequency_value is None
        or frequency_unit is None
    ):
        return None, issues

    entry = ScheduleEntry(
        schedule_id=schedule_id,
        manufacturer_id=manufacturer_id,
        ranges=_split_ranges(row.get("ranges")),
        first_run=first_run,
        frequency_value=frequency_value,
        frequency_unit=frequency_unit,
        enabled=enabled,
        vehicle_class=vehicle_class,
        notes=_clean(row.get("notes")),
    )
    return entry, issues


def load(path: Path | str) -> LoadResult:
    """Load and validate the run schedule CSV."""
    result = LoadResult()
    seen_ids: dict[str, int] = {}

    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):  # header occupies row 1
            entry, issues = _row_to_entry(row, row_number)
            result.issues.extend(issues)
            if entry is None:
                continue

            if entry.schedule_id in seen_ids:
                result.issues.append(
                    Issue(
                        severity="error",
                        code="duplicate_schedule_id",
                        message=(
                            f"schedule_id {entry.schedule_id!r} is also used on row "
                            f"{seen_ids[entry.schedule_id]}"
                        ),
                        row_number=row_number,
                        schedule_id=entry.schedule_id,
                    )
                )
                continue
            seen_ids[entry.schedule_id] = row_number
            result.entries.append(entry)

    return result
