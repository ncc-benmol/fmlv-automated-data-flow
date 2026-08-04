"""Tests for reviewer decisions: accept / reject / correct on a proposed change."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fmlv_automated_data_flow import store


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = store.connect(tmp_path / "runs.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def proposed_change_id(connection: sqlite3.Connection) -> int:
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    product = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=4147,
        manufacturer_range="Matrix",
        model="Supreme 670 DC",
        run_id=run.id,
    )
    change = store.record_proposed_change(
        connection,
        run_id=run.id,
        product_id=product.id,
        field="rrp_pounds",
        old_value="93950",
        new_value="93920",
    )
    return change.id


def test_record_decision_defaults_to_accept_metadata(
    connection: sqlite3.Connection, proposed_change_id: int
) -> None:
    decision = store.record_decision(
        connection,
        proposed_change_id=proposed_change_id,
        action="accept",
        decided_by="ben",
    )
    assert decision.action == "accept"
    assert decision.decided_by == "ben"
    assert decision.corrected_value is None
    assert decision.decided_at is not None


def test_record_decision_correct_stores_corrected_value(
    connection: sqlite3.Connection, proposed_change_id: int
) -> None:
    decision = store.record_decision(
        connection,
        proposed_change_id=proposed_change_id,
        action="correct",
        corrected_value="93900",
        decided_by="ben",
    )
    assert decision.action == "correct"
    assert decision.corrected_value == "93900"


def test_invalid_action_is_rejected_by_the_schema(
    connection: sqlite3.Connection, proposed_change_id: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.record_decision(
            connection, proposed_change_id=proposed_change_id, action="maybe"
        )  # type: ignore[arg-type]


def test_get_decision_raises_for_unknown_id(connection: sqlite3.Connection) -> None:
    with pytest.raises(KeyError):
        store.get_decision(connection, 999)


def test_latest_decision_is_none_when_undecided(
    connection: sqlite3.Connection, proposed_change_id: int
) -> None:
    assert store.latest_decision(connection, proposed_change_id) is None


def test_latest_decision_returns_the_most_recent_override(
    connection: sqlite3.Connection, proposed_change_id: int
) -> None:
    store.record_decision(
        connection, proposed_change_id=proposed_change_id, action="reject", decided_by="ben"
    )
    store.record_decision(
        connection, proposed_change_id=proposed_change_id, action="accept", decided_by="ben"
    )

    latest = store.latest_decision(connection, proposed_change_id)

    assert latest is not None
    assert latest.action == "accept"
