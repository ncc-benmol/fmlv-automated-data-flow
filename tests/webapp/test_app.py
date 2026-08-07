"""Tests for the review app: run list, change queue, per-field decisions.

Uses `fastapi.testclient.TestClient` against a throwaway SQLite file — no real
server, no browser. `diff_products` + `store.persist_diff` populate the DB the same
way a real run would (Phase 5 + the persistence layer above), so these tests exercise
the same path a reviewer actually hits.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import paths, store
from src.adapters.base import ExtractedMotorhome, Provenance
from src.diff.classify import diff_products
from src.product_model import io
from src.product_model.model import Motorhome
from src.webapp import create_app


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
                source_url="https://www.adria.co.uk/motorhomes/matrix", snippet="RRP £93,920"
            )
        },
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "runs.db"


@pytest.fixture
def client(db_path: Path) -> TestClient:
    return TestClient(create_app(db_path))


@pytest.fixture
def run_with_one_change(db_path: Path) -> tuple[int, int]:
    """A run with a single pending `rrp_pounds` proposed change. Returns (run_id, change_id)."""
    connection = store.connect(db_path)
    try:
        run = store.start_run(
            connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
        )
        baseline = make_baseline()
        extracted = make_extracted(rrp_pounds=93920)
        diffs = diff_products([extracted], [baseline])
        store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
        [entry] = store.list_change_queue(connection, run.id)
        store.finish_run(connection, run.id)
        return run.id, entry.change.id
    finally:
        connection.close()


@pytest.fixture
def run_ready_for_upload(db_path: Path) -> int:
    """A succeeded, fully-reviewed run, plus the registry/export files its manufacturer
    needs — everything `generate_upload_route` looks up besides the change queue
    itself. Returns the run id."""
    data_root = db_path.parent
    (data_root / "manufacturers.csv").write_text(
        "manufacturer_id,fmlv_manufacturer,website_url\n3,Adria Mobil,https://example.invalid/\n",
        encoding="utf-8",
    )
    connection = store.connect(db_path)
    try:
        run = store.start_run(
            connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
        )
        baseline = make_baseline()
        extracted = make_extracted(rrp_pounds=93920)
        diffs = diff_products([extracted], [baseline])
        store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
        for entry in store.list_change_queue(connection, run.id):
            store.record_decision(
                connection, proposed_change_id=entry.change.id, action="accept", decided_by="ben"
            )
        store.finish_run(connection, run.id)
    finally:
        connection.close()

    export_dir = paths.manufacturer_exports_dir(3, "Adria Mobil", root=data_root)
    io.write_csv([baseline], export_dir / "2026-08-01_Adria-Mobil_motorhome-campervans.csv")
    return run.id


def test_home_page_links_to_trigger_and_runs(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/trigger"' in response.text
    assert 'href="/runs"' in response.text


def test_run_list_is_empty_with_no_runs(client: TestClient) -> None:
    response = client.get("/runs")
    assert response.status_code == 200
    assert "No runs recorded yet" in response.text


def test_run_list_shows_recorded_runs(client: TestClient, db_path: Path) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    store.finish_run(connection, run.id)
    connection.close()

    response = client.get("/runs")

    assert response.status_code == 200
    assert "Adria Mobil" in response.text
    assert f"#{run.id}" in response.text


def test_run_list_shows_a_running_run_without_a_review_link(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    connection.close()

    response = client.get("/runs")

    assert response.status_code == 200
    assert f'href="/runs/{run.id}"' not in response.text
    assert "not yet available for review" in response.text


def test_run_list_shows_pending_count_and_a_generate_upload_button(
    client: TestClient, run_with_one_change: tuple[int, int]
) -> None:
    run_id, _change_id = run_with_one_change

    response = client.get("/runs")

    assert response.status_code == 200
    assert "1 pending" in response.text
    assert f'action="/runs/{run_id}/generate-upload"' in response.text


def test_run_list_shows_the_primary_reviewer_once_something_is_decided(
    client: TestClient, run_with_one_change: tuple[int, int]
) -> None:
    run_id, change_id = run_with_one_change
    client.post(
        f"/runs/{run_id}/changes/{change_id}/decide",
        data={"action": "accept", "reviewer_name": "ben"},
    )

    response = client.get("/runs")

    assert response.status_code == 200
    assert "ben" in response.text
    assert "none" in response.text  # nothing left pending


def test_generate_upload_route_writes_a_csv_and_reports_it_as_json(
    client: TestClient, run_ready_for_upload: int
) -> None:
    run_id = run_ready_for_upload

    response = client.post(f"/runs/{run_id}/generate-upload")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["count"] == 1
    assert data["filename"].startswith(f"run{run_id}_")
    assert data["download_url"] == f"/runs/{run_id}/uploads/{data['filename']}"
    assert "folder_url" not in data


def test_generate_upload_route_refuses_a_run_that_has_not_succeeded(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    connection.close()

    response = client.post(f"/runs/{run.id}/generate-upload")

    assert response.status_code == 409
    assert response.json()["ok"] is False


def test_downloading_a_generated_upload_serves_the_file(
    client: TestClient, run_ready_for_upload: int
) -> None:
    run_id = run_ready_for_upload
    filename = client.post(f"/runs/{run_id}/generate-upload").json()["filename"]

    response = client.get(f"/runs/{run_id}/uploads/{filename}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_downloading_an_upload_for_the_wrong_run_id_404s(
    client: TestClient, run_ready_for_upload: int
) -> None:
    run_id = run_ready_for_upload
    filename = client.post(f"/runs/{run_id}/generate-upload").json()["filename"]

    response = client.get(f"/runs/{run_id + 1}/uploads/{filename}")

    assert response.status_code == 404


def test_a_running_run_shows_the_in_progress_page_not_the_queue(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    connection.close()

    response = client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert "still fetching and diffing" in response.text
    assert "Pending (" not in response.text


def test_run_detail_404s_for_an_unknown_run(client: TestClient) -> None:
    response = client.get("/runs/999999")
    assert response.status_code == 404


def test_run_detail_shows_pending_change_with_source_and_link(
    client: TestClient, run_with_one_change: tuple[int, int]
) -> None:
    run_id, _change_id = run_with_one_change

    response = client.get(f"/runs/{run_id}")

    assert response.status_code == 200
    assert "rrp_pounds" in response.text
    assert "93950" in response.text
    assert "93920" in response.text
    assert "https://www.adria.co.uk/motorhomes/matrix" in response.text
    assert "£93,920" in response.text
    assert "Pending (1)" in response.text


def test_accept_records_a_decision_and_moves_the_change_to_decided(
    client: TestClient, db_path: Path, run_with_one_change: tuple[int, int]
) -> None:
    run_id, change_id = run_with_one_change

    response = client.post(
        f"/runs/{run_id}/changes/{change_id}/decide",
        data={"action": "accept", "reviewer_name": "ben"},
    )

    assert response.status_code == 200
    assert "decision-accept" in response.text
    assert "ben" in response.text

    connection = store.connect(db_path)
    decision = store.latest_decision(connection, change_id)
    connection.close()
    assert decision is not None
    assert decision.action == "accept"
    assert decision.decided_by == "ben"

    detail = client.get(f"/runs/{run_id}")
    assert "Pending (0)" in detail.text
    assert "Decided (1)" in detail.text


def test_reject_records_a_decision(
    client: TestClient, db_path: Path, run_with_one_change: tuple[int, int]
) -> None:
    run_id, change_id = run_with_one_change

    response = client.post(
        f"/runs/{run_id}/changes/{change_id}/decide",
        data={"action": "reject", "reviewer_name": "ben"},
    )

    assert response.status_code == 200
    assert "decision-reject" in response.text
    connection = store.connect(db_path)
    decision = store.latest_decision(connection, change_id)
    connection.close()
    assert decision is not None
    assert decision.action == "reject"


def test_correct_with_a_value_records_the_corrected_value(
    client: TestClient, db_path: Path, run_with_one_change: tuple[int, int]
) -> None:
    run_id, change_id = run_with_one_change

    response = client.post(
        f"/runs/{run_id}/changes/{change_id}/decide",
        data={"action": "correct", "corrected_value": "93900", "reviewer_name": "ben"},
    )

    assert response.status_code == 200
    assert "93900" in response.text
    connection = store.connect(db_path)
    decision = store.latest_decision(connection, change_id)
    connection.close()
    assert decision is not None
    assert decision.action == "correct"
    assert decision.corrected_value == "93900"


def test_correct_without_a_value_is_rejected_with_an_inline_error(
    client: TestClient, db_path: Path, run_with_one_change: tuple[int, int]
) -> None:
    run_id, change_id = run_with_one_change

    response = client.post(
        f"/runs/{run_id}/changes/{change_id}/decide",
        data={"action": "correct", "corrected_value": "", "reviewer_name": "ben"},
    )

    assert response.status_code == 200
    assert "Enter a corrected value" in response.text
    connection = store.connect(db_path)
    decision = store.latest_decision(connection, change_id)
    connection.close()
    assert decision is None


def test_decide_404s_for_an_unknown_change(
    client: TestClient, run_with_one_change: tuple[int, int]
) -> None:
    run_id, _change_id = run_with_one_change

    response = client.post(
        f"/runs/{run_id}/changes/999999/decide",
        data={"action": "accept"},
    )

    assert response.status_code == 404


def test_decide_rejects_an_action_outside_the_allowed_set(
    client: TestClient, run_with_one_change: tuple[int, int]
) -> None:
    run_id, change_id = run_with_one_change

    response = client.post(
        f"/runs/{run_id}/changes/{change_id}/decide",
        data={"action": "maybe"},
    )

    assert response.status_code == 422


def test_new_product_field_has_no_old_value_shown_as_an_em_dash(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    extracted = make_extracted(
        rrp_pounds=45000, manufacturer_range="Sonic", model="Axess 600 SL"
    )
    diffs = diff_products([extracted], [])
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    store.finish_run(connection, run.id)
    connection.close()

    response = client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert "new product" in response.text
    assert "45000" in response.text


def test_layout_field_change_is_marked_unusual(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    baseline = make_baseline()
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(
            manufacturer="Adria Mobil",
            manufacturer_range="Matrix",
            model="Supreme 670 DC",
            rear_garage=True,
        ),
        provenance={
            "rear_garage": Provenance(source_url="https://example.com", snippet="Garage: Yes")
        },
    )
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    store.finish_run(connection, run.id)
    connection.close()

    response = client.get(f"/runs/{run.id}")

    assert "unusual" in response.text


def test_year_rollover_proposal_is_marked_possible_rollover(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    baseline = make_baseline(year=2026)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    store.finish_run(connection, run.id)
    connection.close()

    response = client.get(f"/runs/{run.id}")

    assert "possible rollover" in response.text
    assert "2027" in response.text


def test_disappeared_product_shows_propose_to_archive(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    baseline = make_baseline()
    diffs = diff_products([], [baseline])
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    store.finish_run(connection, run.id)
    connection.close()

    response = client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert "Propose to Archive" in response.text


def test_accept_all_accepts_every_pending_change_for_one_product(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    baseline = make_baseline(mro_kilograms=3184)
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(
            manufacturer="Adria Mobil",
            manufacturer_range="Matrix",
            model="Supreme 670 DC",
            rrp_pounds=93920,
            mro_kilograms=3228,
        ),
        provenance={
            "rrp_pounds": Provenance(source_url="https://a", snippet="a"),
            "mro_kilograms": Provenance(source_url="https://a", snippet="b"),
        },
    )
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    queue = store.list_change_queue(connection, run.id)
    product_id = queue[0].product.id
    assert len(queue) == 2
    store.finish_run(connection, run.id)
    connection.close()

    response = client.post(
        f"/runs/{run.id}/products/{product_id}/accept-all",
        data={"reviewer_name": "ben"},
    )

    assert response.status_code == 200
    assert response.text.count("decision-accept") == 2
    # A single click both decides everything and hides the "Accept all" button —
    # previously the button stayed put, wrongly implying a second click was needed.
    assert "accept-all-form" not in response.text

    connection = store.connect(db_path)
    decisions = [store.latest_decision(connection, e.change.id) for e in queue]
    connection.close()
    assert all(d is not None and d.action == "accept" for d in decisions)


def test_accept_all_404s_for_an_unknown_product(
    client: TestClient, run_with_one_change: tuple[int, int]
) -> None:
    run_id, _change_id = run_with_one_change

    response = client.post(
        f"/runs/{run_id}/products/999999/accept-all",
        data={"reviewer_name": "ben"},
    )

    assert response.status_code == 404


def test_run_detail_groups_changes_by_product_not_a_single_flat_list(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    first_baseline = make_baseline(product_id=4147, model="Supreme 670 DC", mro_kilograms=3184)
    second_baseline = make_baseline(product_id=8195, model="670 SL 60Y", mro_kilograms=3134)
    first_extracted = ExtractedMotorhome(
        motorhome=Motorhome(
            manufacturer="Adria Mobil",
            manufacturer_range="Matrix",
            model="Supreme 670 DC",
            rrp_pounds=93920,
        ),
        provenance={"rrp_pounds": Provenance(source_url="https://a", snippet="a")},
    )
    second_extracted = ExtractedMotorhome(
        motorhome=Motorhome(
            manufacturer="Adria Mobil",
            manufacturer_range="Matrix",
            model="670 SL 60Y",
            rrp_pounds=94000,
        ),
        provenance={"rrp_pounds": Provenance(source_url="https://b", snippet="b")},
    )
    diffs = diff_products(
        [first_extracted, second_extracted], [first_baseline, second_baseline]
    )
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    store.finish_run(connection, run.id)
    connection.close()

    response = client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert "Supreme 670 DC" in response.text
    assert "670 SL 60Y" in response.text
    assert "93920" in response.text
    assert "94000" in response.text


def test_rejection_is_remembered_across_runs_end_to_end(
    client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    [entry] = store.list_change_queue(connection, run.id)
    store.finish_run(connection, run.id)
    connection.close()

    client.post(
        f"/runs/{run.id}/changes/{entry.change.id}/decide",
        data={"action": "reject", "reviewer_name": "ben"},
    )

    connection = store.connect(db_path)
    second_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    second_diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=second_run.id, manufacturer_id=3, diffs=second_diffs)
    store.finish_run(connection, second_run.id)
    connection.close()

    response = client.get(f"/runs/{second_run.id}")
    assert "Pending (0)" in response.text
    assert "rrp_pounds" not in response.text


# --------------------------------------------------------------------------- #
# Reviewer gating — decisions are only accepted from a name in reviewers.csv
# --------------------------------------------------------------------------- #


@pytest.fixture
def reviewers_path(tmp_path: Path) -> Path:
    path = tmp_path / "reviewers.csv"
    path.write_text(
        "reviewer_name,reviewer_email\nBen Molyneaux,ben.m@thencc.org.uk\nFran,\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def gated_client(db_path: Path, reviewers_path: Path) -> TestClient:
    return TestClient(create_app(db_path, reviewers_path=reviewers_path))


def test_decide_is_rejected_when_reviewer_is_not_in_the_known_list(
    gated_client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    [entry] = store.list_change_queue(connection, run.id)
    connection.close()

    response = gated_client.post(
        f"/runs/{run.id}/changes/{entry.change.id}/decide",
        data={"action": "accept", "reviewer_name": "Someone Unlisted"},
    )

    assert response.status_code == 200
    assert "Select your name from the reviewer list" in response.text
    connection = store.connect(db_path)
    decision = store.latest_decision(connection, entry.change.id)
    connection.close()
    assert decision is None


def test_decide_succeeds_when_reviewer_is_in_the_known_list(
    gated_client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run.id, manufacturer_id=3, diffs=diffs)
    [entry] = store.list_change_queue(connection, run.id)
    connection.close()

    response = gated_client.post(
        f"/runs/{run.id}/changes/{entry.change.id}/decide",
        data={"action": "accept", "reviewer_name": "Fran"},
    )

    assert response.status_code == 200
    assert "decision-accept" in response.text
    connection = store.connect(db_path)
    decision = store.latest_decision(connection, entry.change.id)
    connection.close()
    assert decision is not None
    assert decision.decided_by == "Fran"


def test_run_detail_offers_a_reviewer_dropdown_when_reviewers_are_configured(
    gated_client: TestClient, db_path: Path
) -> None:
    connection = store.connect(db_path)
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    store.finish_run(connection, run.id)
    connection.close()

    response = gated_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert "<select" in response.text
    assert "Ben Molyneaux" in response.text
    assert "Fran" in response.text
