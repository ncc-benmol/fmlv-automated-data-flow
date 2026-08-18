"""Tests for persisting a run's diff into `proposed_change`/`verification` rows."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from src import store
from src.adapters.base import ExtractedMotorhome, Provenance
from src.diff.classify import diff_products
from src.product_model.model import Motorhome


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = store.connect(tmp_path / "runs.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def run_id(connection: sqlite3.Connection) -> int:
    return store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    ).id


def make_baseline(**overrides: object) -> Motorhome:
    fields: dict[str, object] = {
        "product_id": 4147,
        "manufacturer": "Adria Mobil",
        "manufacturer_range": "Matrix",
        "model": "Supreme 670 DC",
        "rrp_pounds": 93950,
    }
    fields.update(overrides)
    return Motorhome(**fields)


def make_extracted(*, rrp_pounds: int, **overrides: object) -> ExtractedMotorhome:
    fields: dict[str, object] = {
        "manufacturer": "Adria Mobil",
        "manufacturer_range": "Matrix",
        "model": "Supreme 670 DC",
        "rrp_pounds": rrp_pounds,
    }
    fields.update(overrides)
    return ExtractedMotorhome(
        motorhome=Motorhome(**fields),
        provenance={
            "rrp_pounds": Provenance(
                source_url="https://www.adria.co.uk/motorhomes/matrix", snippet="£93,920"
            )
        },
    )


def test_changed_field_is_persisted_as_a_proposed_change(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])

    result = store.persist_diff(
        connection, run_id=run_id, manufacturer_id=3, diffs=diffs
    )

    assert result.proposed == 1
    assert result.verified == 0
    queue = store.list_change_queue(connection, run_id)
    assert len(queue) == 1
    entry = queue[0]
    assert entry.change.field == "rrp_pounds"
    assert entry.change.old_value == "93950"
    assert entry.change.new_value == "93920"
    assert entry.change.source_url == "https://www.adria.co.uk/motorhomes/matrix"
    assert entry.product.fmlv_product_id == 4147
    assert entry.decision is None


def test_unchanged_confirmed_is_persisted_as_a_verification_not_a_change(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline(rrp_pounds=93920)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])

    result = store.persist_diff(
        connection, run_id=run_id, manufacturer_id=3, diffs=diffs
    )

    assert result.proposed == 0
    assert result.verified == 1
    assert store.list_change_queue(connection, run_id) == []


def test_new_product_persists_every_extracted_field_with_no_old_value(
    connection: sqlite3.Connection, run_id: int
) -> None:
    extracted = make_extracted(
        rrp_pounds=45000, manufacturer_range="Sonic", model="Axess 600 SL"
    )
    diffs = diff_products([extracted], [])

    result = store.persist_diff(
        connection, run_id=run_id, manufacturer_id=3, diffs=diffs
    )

    assert result.proposed == 1
    queue = store.list_change_queue(connection, run_id)
    assert queue[0].change.old_value is None
    assert queue[0].change.new_value == "45000"
    assert queue[0].product.fmlv_product_id is None


def test_disappeared_product_gets_a_disappearance_notice_not_a_proposed_change(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    diffs = diff_products([], [baseline])

    result = store.persist_diff(
        connection, run_id=run_id, manufacturer_id=3, diffs=diffs
    )

    assert result.proposed == 0
    assert result.disappeared_noted == 1
    assert result.verified == 0
    assert store.list_change_queue(connection, run_id) == []
    [entry] = store.list_disappearance_notices(connection, run_id)
    assert entry.product.fmlv_product_id == 4147
    assert "not found" in entry.notice.note.lower()


def test_disappearance_notice_is_recorded_again_every_run_it_recurs(
    connection: sqlite3.Connection, run_id: int
) -> None:
    """Unlike a proposed change, there's no accept/reject to remember — a still-missing
    product gets a fresh notice on the run detail page each run it stays missing."""
    baseline = make_baseline()
    first_diffs = diff_products([], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=first_diffs)

    second_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    second_diffs = diff_products([], [baseline])
    result = store.persist_diff(
        connection, run_id=second_run.id, manufacturer_id=3, diffs=second_diffs
    )

    assert result.disappeared_noted == 1
    assert len(store.list_disappearance_notices(connection, second_run.id)) == 1


def test_rejected_change_is_not_re_proposed_next_run(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    first_diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=first_diffs)

    [entry] = store.list_change_queue(connection, run_id)
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="reject", decided_by="ben"
    )

    second_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    # Same baseline, same scraped value again — the manufacturer's site hasn't changed.
    second_diffs = diff_products([extracted], [baseline])
    result = store.persist_diff(
        connection, run_id=second_run.id, manufacturer_id=3, diffs=second_diffs
    )

    assert result.proposed == 0
    assert result.suppressed_rejections == 1
    assert store.list_change_queue(connection, second_run.id) == []


def test_a_different_new_value_is_still_proposed_after_a_rejection(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    first_extracted = make_extracted(rrp_pounds=93920)
    first_diffs = diff_products([first_extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=first_diffs)

    [entry] = store.list_change_queue(connection, run_id)
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="reject", decided_by="ben"
    )

    second_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    # The manufacturer corrected their site to a different figure — must still surface.
    second_extracted = make_extracted(rrp_pounds=94500)
    second_diffs = diff_products([second_extracted], [baseline])
    result = store.persist_diff(
        connection, run_id=second_run.id, manufacturer_id=3, diffs=second_diffs
    )

    assert result.proposed == 1
    assert result.suppressed_rejections == 0


def test_year_rollover_eligible_product_gets_a_year_proposed_change(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline(year=2026)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))
    assert diffs[0].year_rollover_eligible is True

    result = store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    assert result.year_rollover_proposed == 1
    queue = store.list_change_queue(connection, run_id)
    year_change = next(entry for entry in queue if entry.change.field == "year")
    assert year_change.change.old_value == "2026"
    assert year_change.change.new_value == "2027"
    assert year_change.change.source_url is None
    assert year_change.change.source_snippet is not None


def test_year_rollover_not_proposed_outside_the_window(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline(year=2026)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline], today=date(2026, 1, 15))

    result = store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    assert result.year_rollover_proposed == 0
    queue = store.list_change_queue(connection, run_id)
    assert not any(entry.change.field == "year" for entry in queue)


def test_year_rollover_not_proposed_when_baseline_is_already_at_the_cap(
    connection: sqlite3.Connection, run_id: int
) -> None:
    # Already one year ahead of "today" — bumping again would overshoot the cap.
    baseline = make_baseline(year=2027)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))

    result = store.persist_diff(
        connection, run_id=run_id, manufacturer_id=3, diffs=diffs, today=date(2026, 7, 15)
    )

    assert result.year_rollover_proposed == 0
    queue = store.list_change_queue(connection, run_id)
    assert not any(entry.change.field == "year" for entry in queue)


def test_year_rollover_not_proposed_when_baseline_year_is_stale(
    connection: sqlite3.Connection, run_id: int
) -> None:
    # Baseline is two years behind "today" — not a plausible rollover, just stale data.
    baseline = make_baseline(year=2024)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))

    result = store.persist_diff(
        connection, run_id=run_id, manufacturer_id=3, diffs=diffs, today=date(2026, 7, 15)
    )

    assert result.year_rollover_proposed == 0
    queue = store.list_change_queue(connection, run_id)
    assert not any(entry.change.field == "year" for entry in queue)


def test_bump_year_all_also_respects_the_cap(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline(year=2027)
    extracted = make_extracted(rrp_pounds=93950)  # identical to baseline, no other change
    diffs = diff_products([extracted], [baseline], today=date(2026, 1, 15))

    result = store.persist_diff(
        connection,
        run_id=run_id,
        manufacturer_id=3,
        diffs=diffs,
        bump_year_all=True,
        today=date(2026, 1, 15),
    )

    assert result.year_rollover_proposed == 0
    assert result.proposed == 0


def test_rejected_year_rollover_is_not_re_proposed(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline(year=2026)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    queue = store.list_change_queue(connection, run_id)
    year_change = next(entry for entry in queue if entry.change.field == "year")
    store.record_decision(
        connection, proposed_change_id=year_change.change.id, action="reject", decided_by="ben"
    )

    second_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    second_diffs = diff_products([extracted], [baseline], today=date(2026, 8, 1))
    result = store.persist_diff(
        connection, run_id=second_run.id, manufacturer_id=3, diffs=second_diffs
    )

    assert result.year_rollover_proposed == 0
    assert result.suppressed_rejections == 1


def test_change_queue_reflects_a_decision_once_made(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    [entry] = store.list_change_queue(connection, run_id)
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="accept", decided_by="ben"
    )

    [updated] = store.list_change_queue(connection, run_id)
    assert updated.decision is not None
    assert updated.decision.action == "accept"


def test_run_review_summary_before_anything_is_decided(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    summary = store.run_review_summary(connection, run_id)

    assert summary.pending_count == 1
    assert summary.primary_reviewer is None


def test_run_review_summary_counts_pending_and_finds_the_busiest_reviewer(
    connection: sqlite3.Connection, run_id: int
) -> None:
    first_baseline = make_baseline(product_id=4147, model="Supreme 670 DC")
    second_baseline = make_baseline(product_id=8195, model="670 SL 60Y")
    first_extracted = make_extracted(rrp_pounds=93920, model="Supreme 670 DC")
    second_extracted = make_extracted(rrp_pounds=81000, model="670 SL 60Y")
    diffs = diff_products(
        [first_extracted, second_extracted], [first_baseline, second_baseline]
    )
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    [first_entry, second_entry] = store.list_change_queue(connection, run_id)
    store.record_decision(
        connection, proposed_change_id=first_entry.change.id, action="accept", decided_by="ben"
    )
    store.record_decision(
        connection, proposed_change_id=second_entry.change.id, action="accept", decided_by="ben"
    )

    summary = store.run_review_summary(connection, run_id)

    assert summary.pending_count == 0
    assert summary.primary_reviewer == "ben"
