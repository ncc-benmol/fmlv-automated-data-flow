"""A touring-caravan run end to end: scrape -> diff -> persist -> upload CSV.

The adapter, schema, model, diff and output layers all have their own tests. This one
exists because the failure that would hurt most is none of theirs: every part working and
the *seams* between them being motorhome-shaped, so a caravan run quietly produces a
68-column motorhome CSV, or diffs caravan scrapes against a motorhome baseline and calls
every product new.

Runs against the real Bailey caravan export where it is present, and skips rather than
fails when it is not — `data/exports` is gitignored.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src import paths, store
from src.adapters import bailey_caravan
from src.cli import _dedupe_baseline, _is_current_model_year, read_baseline
from src.diff import diff_products
from src.diff.classify import ChangeKind
from src.output.build import generate_upload
from src.product_model import caravan_schema
from src.product_model.caravan import Caravan
from src.registry.models import Manufacturer, Status, TriState
from src.vehicle_class import VehicleClass

FIXTURES_DIR = Path(__file__).parent / "adapters" / "fixtures"
REAL_EXPORT = Path("data/exports/28_Bailey/2026-09-03_Bailey_touring-caravans.xlsx")

requires_real_export = pytest.mark.skipif(
    not REAL_EXPORT.exists(),
    reason="run `fmlv fetch-export Bailey` to exercise the caravan pipeline end to end",
)

_FIXTURE_PAGES = (
    "bailey_caravan_pegasus_black_messina.html",
    "bailey_caravan_discovery_d4_2.html",
    "bailey_caravan_unicorn_deluxe_cabrera.html",
    "bailey_caravan_phoenix_black_420.html",
)

BAILEY = Manufacturer(
    manufacturer_id=28,
    fmlv_manufacturer="Bailey",
    fmlv_display_name="Bailey",
    categories=("motorhome", "caravan"),
    status=Status.ACTIVE,
    pilot_priority=None,
    country="United Kingdom",
    website_url="https://www.baileyofbristol.co.uk",
    uk_site_url=None,
    models_index_url=None,
    price_list_url=None,
    brochure_url=None,
    ncc_supplier_name="Bailey of Bristol",
    specs_format="html",
    needs_javascript=TriState.NO,
    login_required=False,
    ncc_member=True,
    contact_name=None,
    contact_email=None,
    contact_phone=None,
    last_verified=None,
    notes=None,
)


def scraped_fixtures() -> list:
    return [
        bailey_caravan.build_extracted(
            bailey_caravan.parse_model_page(
                (FIXTURES_DIR / name).read_text(encoding="utf-8")
            ),
            f"https://example.test/{name}",
        )
        for name in _FIXTURE_PAGES
    ]


def live_baseline() -> list[Caravan]:
    return _dedupe_baseline(
        product
        for product in read_baseline(REAL_EXPORT, VehicleClass.CARAVAN)
        if product.manufacturer == "Bailey"
        and not product.archived
        and _is_current_model_year(product.year)
    )


@requires_real_export
def test_the_baseline_is_read_as_caravans_not_motorhomes() -> None:
    baseline = live_baseline()

    assert baseline
    assert all(isinstance(product, Caravan) for product in baseline)
    assert all(product.shipping_length_mm is not None for product in baseline)


@requires_real_export
def test_scraped_caravans_match_their_baseline_rows() -> None:
    """If the range corrections or the matching were wrong, these would come back new.

    Four scrapes, four matches — nothing classified as a new product. The rest of the
    baseline reports as disappeared only because this test feeds four fixtures rather
    than sweeping all 23 models.
    """
    diffs = diff_products(scraped_fixtures(), live_baseline())
    by_kind = {kind: [d for d in diffs if d.kind is kind] for kind in ChangeKind}

    assert not by_kind[ChangeKind.NEW_PRODUCT]
    assert len(by_kind[ChangeKind.CHANGED_FIELD]) == 3
    assert len(by_kind[ChangeKind.UNCHANGED_CONFIRMED]) == 1


@requires_real_export
def test_cabrera_confirms_every_field_it_collects() -> None:
    """The strongest single signal the extraction is right — see docs/adapters/bailey.md."""
    diffs = diff_products(scraped_fixtures(), live_baseline())
    cabrera = next(d for d in diffs if d.key == "Bailey Unicorn Deluxe Cabrera")

    assert cabrera.kind is ChangeKind.UNCHANGED_CONFIRMED
    assert not cabrera.changes
    assert len(cabrera.confirmed_fields) == 13


@requires_real_export
def test_the_changes_found_are_prices_and_weights() -> None:
    diffs = diff_products(scraped_fixtures(), live_baseline())
    messina = next(d for d in diffs if d.key == "Bailey Pegasus Black Edition Messina")
    changed = {c.field: (c.old_value, c.new_value) for c in messina.changes}

    assert changed["rrp_pounds"] == (32499, 34499)
    assert changed["mtplm_kilograms"] == (1708, 1712)
    assert all(c.priority == "tracked_numeric" for c in messina.changes)


@requires_real_export
def test_a_caravan_run_produces_a_caravan_upload_csv(tmp_path: Path) -> None:
    """The seam that matters most: 62 caravan columns, named for the caravan importer.

    A motorhome-shaped CSV here would be uploaded by hand into the wrong importer, which
    is the one irreversible step in the pipeline.
    """
    connection = store.connect(paths.db_path(root=tmp_path))
    try:
        run = store.start_run(
            connection,
            manufacturer_id=28,
            fmlv_manufacturer="Bailey",
            trigger="manual",
            vehicle_class=VehicleClass.CARAVAN,
        )
        baseline = live_baseline()
        store.persist_diff(
            connection,
            run_id=run.id,
            manufacturer_id=28,
            diffs=diff_products(scraped_fixtures(), baseline),
            vehicle_class=VehicleClass.CARAVAN,
        )
        store.finish_run(connection, run.id)
        for entry in store.list_change_queue(connection, run.id):
            store.record_decision(
                connection,
                proposed_change_id=entry.change.id,
                action="accept",
                decided_by="Francis Doyle",
            )

        result = generate_upload(
            connection,
            run_id=run.id,
            manufacturer=BAILEY,
            baseline=baseline,
            path=paths.upload_csv_path(
                run.id, vehicle_class=VehicleClass.CARAVAN, root=tmp_path
            ),
            vehicle_class=VehicleClass.CARAVAN,
        )
    finally:
        connection.close()

    assert result.path.name.endswith("_touring-caravans.csv")
    # All four: the three with real changes, plus Cabrera, which changed nothing but is
    # still on sale during the rollover window and so was offered a `year` bump. That
    # route (DESIGN.md §6.9) reaches caravans as well as motorhomes.
    assert len(result.motorhomes) == 4

    lines = result.path.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["-", "-"]  # FMLV wants the header on row 3
    header = next(csv.reader([lines[2]]))
    assert tuple(header) == caravan_schema.COLUMNS
    assert len(header) == 62


@requires_real_export
def test_the_upload_row_carries_the_caravan_only_columns(tmp_path: Path) -> None:
    connection = store.connect(paths.db_path(root=tmp_path))
    try:
        run = store.start_run(
            connection,
            manufacturer_id=28,
            fmlv_manufacturer="Bailey",
            trigger="manual",
            vehicle_class=VehicleClass.CARAVAN,
        )
        baseline = live_baseline()
        store.persist_diff(
            connection,
            run_id=run.id,
            manufacturer_id=28,
            diffs=diff_products(scraped_fixtures(), baseline),
            vehicle_class=VehicleClass.CARAVAN,
        )
        store.finish_run(connection, run.id)
        for entry in store.list_change_queue(connection, run.id):
            store.record_decision(
                connection,
                proposed_change_id=entry.change.id,
                action="accept",
                decided_by="Francis Doyle",
            )
        result = generate_upload(
            connection,
            run_id=run.id,
            manufacturer=BAILEY,
            baseline=baseline,
            path=tmp_path / "upload.csv",
            vehicle_class=VehicleClass.CARAVAN,
        )
    finally:
        connection.close()

    lines = result.path.read_text(encoding="utf-8").splitlines()
    rows = {r["model"]: r for r in csv.DictReader(lines[2:])}
    messina = rows["Messina"]

    assert messina["rrp_pounds"] == "34499"
    assert messina["twin_axle"] == "Yes"
    assert messina["type_rigid"] == "Yes"
    assert messina["type_folding"] == "No"
    assert messina["shipping_length_mm"] == "7905"
    assert messina["awning_length_mm"] == "10891"
    # One price in two columns — `build._mirror_guide_price` applies to caravans too.
    assert messina["price_min_range_pounds"] == messina["rrp_pounds"]
    # Out of scope and never published: left exactly as FMLV holds it, which is blank.
    assert messina["exterior_body_length_mm"] == ""
    assert messina["optional_equipment_payload_kilograms"] == ""


def test_latest_export_will_not_hand_a_caravan_run_the_motorhome_sheet(tmp_path: Path) -> None:
    """One export action saves both sheets side by side, so newest-file-wins is not enough.

    A motorhome baseline against caravan scrapes classifies every caravan as new and every
    motorhome as disappeared — a whole run of nonsense from one filename.
    """
    from src.cli import latest_export

    directory = paths.manufacturer_exports_dir(28, "Bailey", root=tmp_path)
    directory.mkdir(parents=True)
    motorhomes = directory / "2026-09-03_Bailey_motorhome-campervans.xlsx"
    caravans = directory / "2026-09-03_Bailey_touring-caravans.xlsx"
    caravans.write_bytes(b"caravans")
    motorhomes.write_bytes(b"motorhomes")  # written last, so it is the newest

    chosen = latest_export(
        root=tmp_path,
        manufacturer_id=28,
        manufacturer_name="Bailey",
        vehicle_class=VehicleClass.CARAVAN,
    )

    assert chosen == caravans


def test_latest_export_still_defaults_to_motorhomes(tmp_path: Path) -> None:
    from src.cli import latest_export

    directory = paths.manufacturer_exports_dir(28, "Bailey", root=tmp_path)
    directory.mkdir(parents=True)
    (directory / "2026-09-03_Bailey_touring-caravans.xlsx").write_bytes(b"c")
    motorhomes = directory / "2026-09-03_Bailey_motorhome-campervans.xlsx"
    motorhomes.write_bytes(b"m")

    assert latest_export(
        root=tmp_path, manufacturer_id=28, manufacturer_name="Bailey"
    ) == motorhomes


def test_a_missing_export_for_one_area_names_that_area(tmp_path: Path) -> None:
    from src.cli import CommandError, latest_export

    directory = paths.manufacturer_exports_dir(28, "Bailey", root=tmp_path)
    directory.mkdir(parents=True)
    (directory / "2026-09-03_Bailey_motorhome-campervans.xlsx").write_bytes(b"m")

    with pytest.raises(CommandError, match="touring-caravans"):
        latest_export(
            root=tmp_path,
            manufacturer_id=28,
            manufacturer_name="Bailey",
            vehicle_class=VehicleClass.CARAVAN,
        )


@requires_real_export
def test_an_unchanged_caravan_is_still_offered_a_model_year_bump() -> None:
    """DESIGN.md §6.9: still on sale is what makes it a current-model-year product.

    Swift's Carrera 122 was the motorhome case that established this — unchanged for the
    new season and therefore never offered a bump, leaving its year quietly stale. The
    rollover route is product-area-agnostic, and this pins that it stays so.
    """
    from datetime import date

    diffs = diff_products(scraped_fixtures(), live_baseline(), today=date(2026, 8, 15))
    cabrera = next(d for d in diffs if d.key == "Bailey Unicorn Deluxe Cabrera")

    assert cabrera.kind is ChangeKind.UNCHANGED_CONFIRMED
    assert cabrera.year_rollover_eligible is True


@requires_real_export
def test_outside_the_rollover_window_an_unchanged_caravan_contributes_nothing() -> None:
    from datetime import date

    diffs = diff_products(scraped_fixtures(), live_baseline(), today=date(2026, 2, 1))
    cabrera = next(d for d in diffs if d.key == "Bailey Unicorn Deluxe Cabrera")

    assert cabrera.year_rollover_eligible is False
