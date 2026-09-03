"""Working out which schedule entries are due to run.

"Due" is computed fresh every time, from two things that are already persisted
elsewhere rather than tracked separately here (see `config/schedule.README.md`):

* `schedule.csv` itself (`first_run`, `frequency_value`/`frequency_unit`) — loaded by
  `scheduling.loader`.
* The most recent matching `run` row with `trigger == "scheduled"` in the run store —
  "matching" meaning the same manufacturer and the same resolved range label
  `cli.execute_run` would have recorded for this entry's `ranges`.

That second point is why `resolved_range_label` goes through `cli.resolve_ranges`
rather than just joining `entry.ranges` with a comma: `resolve_ranges` is also what
actually runs the schedule (`webapp.scheduler`), so the label used to look up "when
did this last run" is guaranteed to match the label that run actually gets stored
under — the two never drift apart because they're the same code path.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from .. import store
from ..adapters import Adapter
from ..vehicle_class import VehicleClass
from ..cli import CommandError, resolve_ranges
from .models import ScheduleEntry


def resolved_range_label(entry: ScheduleEntry, adapter: Adapter | None) -> str | None:
    """The `run.range_label` this entry's `ranges` would be recorded under.

    `None` for a whole-manufacturer entry (no `ranges`), matching `execute_run`'s own
    convention. Raises `CommandError` if `ranges` is set but the adapter doesn't
    support named ranges, or names one it doesn't recognise — the same error
    `resolve_ranges` raises for a bad `--range` on the command line.
    """
    if not entry.ranges:
        return None
    if adapter is None:
        msg = f"no adapter available to resolve ranges {entry.ranges!r}"
        raise CommandError(msg)
    resolved = resolve_ranges(adapter, entry.ranges)
    return ", ".join(label for _path, label in resolved)


def _last_scheduled_run(
    connection: sqlite3.Connection,
    *,
    manufacturer_id: int,
    range_label: str | None,
    vehicle_class: VehicleClass,
) -> store.Run | None:
    for run in store.list_runs(
        connection, manufacturer_id=manufacturer_id, vehicle_class=vehicle_class
    ):
        if run.trigger == "scheduled" and run.range_label == range_label:
            return run
    return None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def next_due_at(
    entry: ScheduleEntry,
    *,
    range_label: str | None,
    connection: sqlite3.Connection,
) -> datetime:
    """When this entry is next due, in UTC.

    `first_run` if it has never produced a matching scheduled run yet; otherwise the
    last matching run's start time plus the entry's frequency — regardless of
    whether that run succeeded or failed, so a failure waits for the normal interval
    rather than being retried early (see the README).
    """
    last_run = _last_scheduled_run(
        connection,
        manufacturer_id=entry.manufacturer_id,
        range_label=range_label,
        vehicle_class=entry.vehicle_class,
    )
    if last_run is None:
        return entry.first_run.astimezone(UTC)
    return _as_utc(datetime.fromisoformat(last_run.started_at)) + entry.frequency


def last_triggered_at(
    entry: ScheduleEntry,
    *,
    range_label: str | None,
    connection: sqlite3.Connection,
) -> datetime | None:
    """When this entry last actually ran, or `None` if it never has."""
    last_run = _last_scheduled_run(
        connection,
        manufacturer_id=entry.manufacturer_id,
        range_label=range_label,
        vehicle_class=entry.vehicle_class,
    )
    return _as_utc(datetime.fromisoformat(last_run.started_at)) if last_run else None


def has_run_in_progress(
    connection: sqlite3.Connection,
    *,
    manufacturer_id: int,
    vehicle_class: VehicleClass | None = None,
) -> bool:
    """Whether a run (of any trigger) is already `running` for this manufacturer.

    Guards against a scheduler tick starting a second run for a manufacturer that's
    still mid-run — one browser/HTTP sweep per manufacturer at a time, same as a
    person triggering a run by hand would expect.

    `vehicle_class` defaults to `None`, meaning *any* area, which keeps the guard
    deliberately conservative: Bailey's caravan and motorhome sweeps hit the same web
    server, so letting them overlap because they are nominally different runs would
    double the load on a site we are a guest on.
    """
    return bool(
        store.list_runs(
            connection,
            manufacturer_id=manufacturer_id,
            status="running",
            vehicle_class=vehicle_class,
        )
    )


def is_due(
    entry: ScheduleEntry,
    *,
    range_label: str | None,
    connection: sqlite3.Connection,
    now: datetime | None = None,
) -> bool:
    if not entry.enabled:
        return False
    now = now or datetime.now(UTC)
    return now >= next_due_at(entry, range_label=range_label, connection=connection)


@dataclass(frozen=True)
class ScheduleStatus:
    """Everything the `/schedules` page shows for one row of `schedule.csv`."""

    entry: ScheduleEntry
    range_label: str | None
    last_triggered_at: datetime | None
    next_due_at: datetime | None
    is_due: bool
    error: str | None  # e.g. an unresolvable range — never runs until fixed in the CSV


def describe(
    entry: ScheduleEntry,
    *,
    adapter: Adapter | None,
    connection: sqlite3.Connection,
    now: datetime | None = None,
) -> ScheduleStatus:
    """The full display/decision state for one schedule entry, resolved once."""
    try:
        range_label = resolved_range_label(entry, adapter)
    except CommandError as exc:
        return ScheduleStatus(
            entry=entry,
            range_label=None,
            last_triggered_at=None,
            next_due_at=None,
            is_due=False,
            error=str(exc),
        )

    return ScheduleStatus(
        entry=entry,
        range_label=range_label,
        last_triggered_at=last_triggered_at(entry, range_label=range_label, connection=connection),
        next_due_at=next_due_at(entry, range_label=range_label, connection=connection),
        is_due=is_due(entry, range_label=range_label, connection=connection, now=now),
        error=None,
    )
