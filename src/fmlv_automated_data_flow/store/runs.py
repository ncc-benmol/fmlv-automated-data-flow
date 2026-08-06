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


def list_runs(connection: sqlite3.Connection, *, manufacturer_id: int | None = None) -> list[Run]:
    """List runs, most recent first, optionally scoped to one manufacturer."""
    if manufacturer_id is None:
        rows = connection.execute("SELECT * FROM run ORDER BY started_at DESC").fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM run WHERE manufacturer_id = ? ORDER BY started_at DESC",
            (manufacturer_id,),
        ).fetchall()
    return [Run.from_row(row) for row in rows]
