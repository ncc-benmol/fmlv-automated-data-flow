"""Reviewer decisions on proposed changes: accept / reject / correct / blank / undo.

DESIGN.md §6.3: "Accept / reject / correct is per field, and the reviewer can type a
corrected value." A proposed change can be decided more than once — a reviewer
overriding an earlier decision inserts a new row rather than editing the old one, so
the full history survives (DESIGN.md §6.7: "Everything is logged"). Whichever row was
decided most recently is authoritative; `latest_decision` returns exactly that one.

"undo" is a decision like any other — inserted as a new row rather than deleting the
one it reverses, so the history stays intact. `store.changes.list_change_queue`
treats the most recent "undo" as equivalent to no decision at all, reopening the
change for review.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

#: "blank" is the third answer to a field the adapter could not find, alongside
#: "accept" (keep what FMLV holds) and "correct" (replace it with a value). It clears the
#: field outright, for the case the requester raised on 3 September 2026: a manufacturer
#: has withdrawn a spec, and FMLV showing a stale figure is worse than showing nothing.
#:
#: A distinct action rather than a "correct" carrying an empty string, because the two are
#: different editorial judgements and the history has to say which was made — DESIGN.md
#: §6.7, "Everything is logged". It also keeps `corrected_value` meaning one thing: the
#: value a reviewer typed, never the absence of one.
#:
#: **This blanking is not the silent kind `diff.compare` guards against.** That code
#: refuses to propose `None` over a good baseline value precisely so a reviewer cannot
#: blank a field by clicking "accept"; this is the same reviewer asking for it explicitly.
Action = Literal["accept", "reject", "correct", "blank", "undo"]


@dataclass(frozen=True)
class Decision:
    """One reviewer action on one proposed change."""

    id: int
    proposed_change_id: int
    action: Action
    corrected_value: str | None
    decided_by: str | None
    decided_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Decision:
        return cls(
            id=row["id"],
            proposed_change_id=row["proposed_change_id"],
            action=row["action"],
            corrected_value=row["corrected_value"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def record_decision(
    connection: sqlite3.Connection,
    *,
    proposed_change_id: int,
    action: Action,
    corrected_value: str | None = None,
    decided_by: str | None = None,
) -> Decision:
    """Record a reviewer's action on a proposed change.

    `corrected_value` is only meaningful for `action="correct"`; a "correct" decision
    with no `corrected_value` is nonsensical but not rejected here — the caller (the
    review app's form) is where that gets validated, close to the reviewer. A "blank"
    decision carries no `corrected_value` by definition: clearing the field *is* the
    value, and `output.build` writes an empty column for it.
    """
    cursor = connection.execute(
        """
        INSERT INTO decision (proposed_change_id, action, corrected_value, decided_by, decided_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (proposed_change_id, action, corrected_value, decided_by, _now()),
    )
    connection.commit()
    assert cursor.lastrowid is not None
    return get_decision(connection, cursor.lastrowid)


def get_decision(connection: sqlite3.Connection, decision_id: int) -> Decision:
    """Fetch a decision by id. Raises `KeyError` if it doesn't exist."""
    row = connection.execute("SELECT * FROM decision WHERE id = ?", (decision_id,)).fetchone()
    if row is None:
        msg = f"no decision with id {decision_id}"
        raise KeyError(msg)
    return Decision.from_row(row)


def latest_decision(connection: sqlite3.Connection, proposed_change_id: int) -> Decision | None:
    """The most recent decision for a proposed change, or `None` if never decided."""
    row = connection.execute(
        """
        SELECT * FROM decision
        WHERE proposed_change_id = ?
        ORDER BY decided_at DESC, id DESC
        LIMIT 1
        """,
        (proposed_change_id,),
    ).fetchone()
    return Decision.from_row(row) if row is not None else None
