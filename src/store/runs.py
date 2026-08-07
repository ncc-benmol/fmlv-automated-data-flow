"""Run lifecycle: start, finish, fail — the `run` table.

Every fetch/diff/review phase attaches its records to a run via `run_id`, but this
module only covers the run record itself; snapshots, proposed changes, decisions and
verifications are scaffolded in `schema.sql` for the phases that populate them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Trigger = Literal["manual", "scheduled"]
RunStatus = Literal["running", "succeeded", "failed"]


@dataclass(frozen=True)
class Run:
    """A single run: one manufacturer, one trigger, one outcome."""

    id: int
    manufacturer_id: int
    fmlv_manufacturer: str
    trigger: Trigger
    status: RunStatus
    started_at: str
    finished_at: str | None
    error_message: str | None
    range_label: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Run:
        return cls(
            id=row["id"],
            manufacturer_id=row["manufacturer_id"],
            fmlv_manufacturer=row["fmlv_manufacturer"],
            trigger=row["trigger"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error_message=row["error_message"],
            range_label=row["range_label"],
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def start_run(
    connection: sqlite3.Connection,
    *,
    manufacturer_id: int,
    fmlv_manufacturer: str,
    trigger: Trigger,
    range_label: str | None = None,
) -> Run:
    """Record the start of a run. Status is 'running' until `finish_run`/`fail_run`.

    `range_label` is the human label of any `--range`/range-box restriction (e.g.
    "Matrix", or "Supersonic, Sonic" for more than one) — `None` for an unrestricted
    full-manufacturer run, which is what most of DESIGN.md's scheduled sweeps will be.
    """
    cursor = connection.execute(
        """
        INSERT INTO run (manufacturer_id, fmlv_manufacturer, trigger, status, started_at, range_label)
        VALUES (?, ?, ?, 'running', ?, ?)
        """,
        (manufacturer_id, fmlv_manufacturer, trigger, _now(), range_label),
    )
    connection.commit()
    assert cursor.lastrowid is not None
    return get_run(connection, cursor.lastrowid)


def finish_run(connection: sqlite3.Connection, run_id: int) -> Run:
    """Mark a run as succeeded."""
    connection.execute(
        "UPDATE run SET status = 'succeeded', finished_at = ? WHERE id = ?",
        (_now(), run_id),
    )
    connection.commit()
    return get_run(connection, run_id)


def fail_run(connection: sqlite3.Connection, run_id: int, error_message: str) -> Run:
    """Mark a run as failed, recording why."""
    connection.execute(
        "UPDATE run SET status = 'failed', finished_at = ?, error_message = ? WHERE id = ?",
        (_now(), error_message, run_id),
    )
    connection.commit()
    return get_run(connection, run_id)


def get_run(connection: sqlite3.Connection, run_id: int) -> Run:
    """Fetch a run by id. Raises `KeyError` if it doesn't exist."""
    row = connection.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        msg = f"no run with id {run_id}"
        raise KeyError(msg)
    return Run.from_row(row)


def list_runs(
    connection: sqlite3.Connection,
    *,
    manufacturer_id: int | None = None,
    status: RunStatus | None = None,
) -> list[Run]:
    """List runs, most recent first, optionally scoped to one manufacturer and/or status."""
    clauses: list[str] = []
    params: list[object] = []
    if manufacturer_id is not None:
        clauses.append("manufacturer_id = ?")
        params.append(manufacturer_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)

    query = "SELECT * FROM run"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY started_at DESC"

    rows = connection.execute(query, params).fetchall()
    return [Run.from_row(row) for row in rows]


def list_run_manufacturers(connection: sqlite3.Connection) -> list[tuple[int, str]]:
    """Distinct `(manufacturer_id, fmlv_manufacturer)` pairs that have at least one run.

    For the runs page's manufacturer filter — drawn from run history rather than the
    registry, so it only ever offers manufacturers there's actually something to filter
    to, and stays correct even if the registry changes later.
    """
    rows = connection.execute(
        "SELECT DISTINCT manufacturer_id, fmlv_manufacturer FROM run ORDER BY fmlv_manufacturer"
    ).fetchall()
    return [(row["manufacturer_id"], row["fmlv_manufacturer"]) for row in rows]
