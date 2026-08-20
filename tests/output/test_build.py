"""Tests for turning approved decisions into upload-ready `Motorhome`s and a CSV."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from src import store
from src.adapters.base import ExtractedMotorhome, Provenance
from src.diff.classify import diff_products
from src.product_model import validation
from src.product_model.io import read_csv
from src.product_model.model import Motorhome
from src.output import build_upload_motorhomes, generate_upload
from src.registry.models import Manufacturer, Status, TriState


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


def make_manufacturer(**overrides: object) -> Manufacturer:
    fields: dict[str, object] = {
        "manufacturer_id": 3,
        "fmlv_manufacturer": "Adria Mobil",
        "fmlv_display_name": "Adria",
        "categories": (),
        "status": Status.ACTIVE,
        "pilot_priority": 1,
        "country": "UK",
        "website_url": "https://www.adria-mobil.com/",
        "uk_site_url": "https://www.adria.co.uk/",
        "models_index_url": None,
        "price_list_url": None,
        "brochure_url": None,
        "ncc_supplier_name": "Adria Caravans & Motorhomes",
        "specs_format": "mixed",
        "needs_javascript": TriState.YES,
        "login_required": False,
        "ncc_member": True,
        "contact_name": None,
        "contact_email": None,
        "contact_phone": None,
        "last_verified": None,
        "notes": None,
    }
    fields.update(overrides)
    return Manufacturer(**fields)  # type: ignore[arg-type]


def make_baseline(**overrides: object) -> Motorhome:
    fields: dict[str, object] = {
        "product_id": 4147,
        "manufacturer": "Adria Mobil",
        "manufacturer_display_name": "Adria",
        "manufacturer_range": "Matrix",
        "model": "Supreme 670 DC",
        "rrp_pounds": 93950,
        "base_vehicle_manufacturer": "Fiat",
        "mh_passenger_seats_inc_driver": 4,
        "berths": 4,
        "mro_kilograms": 3200,
        "mtplm_kilograms": 4250,
        "mh_payload_kilograms": 1050,
        "mh_length_mm": 6990,
        "mh_width_mm": 2270,
        "mh_height_mm": 2900,
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


def test_accepted_change_is_applied_on_top_of_the_baseline(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    queue = store.list_change_queue(connection, run_id)
    entry = next(e for e in queue if e.change.field == "rrp_pounds")
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="accept", decided_by="ben"
    )

    [motorhome] = build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=make_manufacturer(), baseline=[baseline]
    )

    assert motorhome.product_id == 4147
    assert motorhome.rrp_pounds == 93920
    # Everything not decided carries through from the baseline untouched.
    assert motorhome.mro_kilograms == 3200
    assert motorhome.model == "Supreme 670 DC"


def test_corrected_change_uses_the_corrected_value_not_the_proposal(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    queue = store.list_change_queue(connection, run_id)
    entry = next(e for e in queue if e.change.field == "rrp_pounds")
    store.record_decision(
        connection,
        proposed_change_id=entry.change.id,
        action="correct",
        corrected_value="94100",
        decided_by="ben",
    )

    [motorhome] = build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=make_manufacturer(), baseline=[baseline]
    )

    assert motorhome.rrp_pounds == 94100


def test_rejected_change_leaves_the_baseline_value_untouched(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    queue = store.list_change_queue(connection, run_id)
    entry = next(e for e in queue if e.change.field == "rrp_pounds")
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="reject", decided_by="ben"
    )

    assert build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=make_manufacturer(), baseline=[baseline]
    ) == []


def test_undecided_change_is_not_included_in_the_output(
    connection: sqlite3.Connection, run_id: int
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    assert build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=make_manufacturer(), baseline=[baseline]
    ) == []


def test_new_product_is_built_from_scratch_using_manufacturer_and_product_identity(
    connection: sqlite3.Connection, run_id: int
) -> None:
    extracted = make_extracted(
        rrp_pounds=45000, manufacturer_range="Sonic", model="Axess 600 SL"
    )
    diffs = diff_products([extracted], [])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    [entry] = store.list_change_queue(connection, run_id)
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="accept", decided_by="ben"
    )

    [motorhome] = build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=make_manufacturer(), baseline=[]
    )

    assert motorhome.product_id is None
    assert motorhome.manufacturer == "Adria Mobil"
    assert motorhome.manufacturer_display_name == "Adria"
    assert motorhome.manufacturer_range == "Sonic"
    assert motorhome.model == "Axess 600 SL"
    assert motorhome.rrp_pounds == 45000


def test_accepted_year_rollover_bumps_only_the_year(
    connection: sqlite3.Connection, run_id: int
) -> None:
    # A real field change (rrp) is needed too — year_rollover_eligible is only ever
    # set on a CHANGED_FIELD product (diff/classify.py), never an unchanged one.
    baseline = make_baseline(year=2026)
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    queue = store.list_change_queue(connection, run_id)
    year_entry = next(entry for entry in queue if entry.change.field == "year")
    rrp_entry = next(entry for entry in queue if entry.change.field == "rrp_pounds")
    store.record_decision(
        connection, proposed_change_id=year_entry.change.id, action="accept", decided_by="ben"
    )
    store.record_decision(
        connection, proposed_change_id=rrp_entry.change.id, action="reject", decided_by="ben"
    )

    [motorhome] = build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=make_manufacturer(), baseline=[baseline]
    )

    assert motorhome.year == 2027
    assert motorhome.product_id == 4147
    # The rejected rrp change is not applied — the baseline value carries through.
    assert motorhome.rrp_pounds == 93950


def test_disappeared_product_contributes_nothing_to_the_upload(
    connection: sqlite3.Connection, run_id: int
) -> None:
    """A DISAPPEARED product gets a disappearance notice, not a proposed change — with
    nothing accepted or corrected for it, the upload CSV must carry it through
    unchanged rather than touching `archived` on the pipeline's own say-so."""
    baseline = make_baseline()
    diffs = diff_products([], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    assert store.list_change_queue(connection, run_id) == []
    [notice] = store.list_disappearance_notices(connection, run_id)
    assert notice.product.fmlv_product_id == 4147

    motorhomes = build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=make_manufacturer(), baseline=[baseline]
    )

    assert motorhomes == []


def test_generate_upload_writes_a_csv_in_fmlv_column_order_and_carries_product_id(
    connection: sqlite3.Connection, run_id: int, tmp_path: Path
) -> None:
    baseline = make_baseline()
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    queue = store.list_change_queue(connection, run_id)
    entry = next(e for e in queue if e.change.field == "rrp_pounds")
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="accept", decided_by="ben"
    )

    csv_path = tmp_path / "motorhome-campervans.csv"
    result = generate_upload(
        connection,
        run_id=run_id,
        manufacturer=make_manufacturer(),
        baseline=[baseline],
        path=csv_path,
    )

    assert result.path == csv_path
    assert csv_path.exists()
    assert not result.has_errors
    assert result.issues_path is not None
    assert result.issues_path.read_text(encoding="utf-8") == validation.format_issues(
        result.issues
    )

    # The FMLV upload site expects the header on row 3 and data from row 4, and won't
    # parse the file correctly if those two rows are genuinely empty, so the file
    # starts with two rows each holding a single `-` — `read_csv` alone can't parse
    # that layout, only the FMLV site is meant to.
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "-"
    assert lines[1] == "-"
    assert lines[2].startswith("product_id,")

    read_back = read_csv(csv_path, skip_leading_blank_rows=2)
    assert len(read_back.motorhomes) == 1
    assert read_back.motorhomes[0].product_id == 4147
    assert read_back.motorhomes[0].rrp_pounds == 93920


def test_generate_upload_surfaces_validation_issues_without_blocking_the_write(
    connection: sqlite3.Connection, run_id: int, tmp_path: Path
) -> None:
    # A baseline missing required fields (only product identity + the one change).
    baseline = Motorhome(
        product_id=4147,
        manufacturer="Adria Mobil",
        manufacturer_range="Matrix",
        model="Supreme 670 DC",
        rrp_pounds=93950,
    )
    extracted = make_extracted(rrp_pounds=93920)
    diffs = diff_products([extracted], [baseline])
    store.persist_diff(connection, run_id=run_id, manufacturer_id=3, diffs=diffs)

    [entry] = store.list_change_queue(connection, run_id)
    store.record_decision(
        connection, proposed_change_id=entry.change.id, action="accept", decided_by="ben"
    )

    csv_path = tmp_path / "motorhome-campervans.csv"
    result = generate_upload(
        connection,
        run_id=run_id,
        manufacturer=make_manufacturer(),
        baseline=[baseline],
        path=csv_path,
    )

    assert csv_path.exists()
    assert result.has_errors
    assert any(issue.code == "missing_required" for issue in result.issues)

    assert result.issues_path is not None
    assert result.issues_path.exists()
    issues_text = result.issues_path.read_text(encoding="utf-8")
    assert "[ERROR]" in issues_text
    assert "missing" in issues_text
