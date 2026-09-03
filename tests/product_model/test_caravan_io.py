"""Reading and writing the FMLV touring-caravan export.

The heavier assertions here run against the **real Bailey export** rather than a
hand-built fixture — 81 products downloaded from the NCC site on 3 September 2026. A
schema whose column order is a contract with someone else's importer is worth checking
against the real thing rather than against our own idea of it.
"""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl
import pytest

from src.product_model import caravan_io, caravan_schema, validation
from src.product_model.caravan import Caravan
from src.product_model.enums import (
    BathroomLayout,
    BedType,
    CaravanBodyType,
    CaravanSleepingArea,
    Heating,
    KitchenLocation,
    LoungeLocation,
    Refrigeration,
)

#: The real export, if it has been fetched. Tests needing it skip rather than fail when
#: it is absent — `data/exports` is gitignored, so a fresh clone will not have it.
_REAL_EXPORT = Path("data/exports/28_Bailey/2026-09-03_Bailey_touring-caravans.xlsx")

requires_real_export = pytest.mark.skipif(
    not _REAL_EXPORT.exists(),
    reason="run `fmlv fetch-export Bailey` to check against the real caravan export",
)


def _row(**overrides: object) -> dict[str, object]:
    """A minimal raw export row, with every Yes/No column answered No by default."""
    row: dict[str, object] = dict.fromkeys(caravan_schema.COLUMNS, "")
    for column in caravan_schema.LAYOUT:
        row[column] = "No"
    row["archived"] = "No"
    row.update(overrides)
    return row


# --------------------------------------------------------------------------- #
# Schema shape
# --------------------------------------------------------------------------- #


def test_the_caravan_schema_has_the_columns_the_export_has() -> None:
    assert len(caravan_schema.COLUMNS) == 62
    assert len(set(caravan_schema.COLUMNS)) == 62


def test_the_caravan_schema_drops_every_motorhome_only_column() -> None:
    """A caravan is towed, so there is no chassis, no gearbox variant and no rear garage."""
    assert "base_vehicle_manufacturer" not in caravan_schema.COLUMNS
    assert "mh_passenger_seats_inc_driver" not in caravan_schema.COLUMNS
    assert "rear_garage" not in caravan_schema.COLUMNS
    assert "sleeping_area_separate_childrens_area" not in caravan_schema.COLUMNS
    assert not [c for c in caravan_schema.COLUMNS if c.startswith("automatic_")]
    assert not [c for c in caravan_schema.COLUMNS if c.startswith("mh_")]


def test_the_caravan_schema_carries_its_own_extra_columns() -> None:
    for column in (
        "internal_length_mm",
        "shipping_length_mm",
        "awning_length_mm",
        "twin_axle",
        "headroom_mm",
        "optional_equipment_payload_kilograms",
        "personal_effects_payload_kilograms",
    ):
        assert column in caravan_schema.COLUMNS


def test_optional_equipment_payload_is_out_of_automated_scope() -> None:
    """Populated on none of the 92 real caravan products this project holds."""
    assert "optional_equipment_payload_kilograms" not in caravan_schema.IN_SCOPE
    assert "optional_equipment_payload_kilograms" not in caravan_schema.TRACKED_NUMERIC
    assert "personal_effects_payload_kilograms" in caravan_schema.IN_SCOPE


@requires_real_export
def test_the_schema_column_order_matches_the_real_export_exactly() -> None:
    """Column order is a contract with FMLV's importer, not a preference."""
    workbook = openpyxl.load_workbook(_REAL_EXPORT, read_only=True)
    try:
        header = tuple(
            str(cell) for cell in next(workbook.active.iter_rows(min_row=1, max_row=1, values_only=True))
        )
    finally:
        workbook.close()

    assert caravan_schema.COLUMNS == header


# --------------------------------------------------------------------------- #
# Row <-> Caravan
# --------------------------------------------------------------------------- #


def test_row_to_caravan_reads_the_layout_groups() -> None:
    caravan, issues = caravan_io.row_to_caravan(
        _row(
            manufacturer="Bailey",
            model="Cabrera",
            type_rigid="Yes",
            sleeping_area_both="Yes",
            make_up_beds="Yes",
            island_bed="Yes",
            side_kitchen="Yes",
            separate_shower_toilet="Yes",
            front_lounge="Yes",
            blown_air_heating="Yes",
            fridge_freezer="Yes",
            twin_axle="Yes",
            microwave="Yes",
        )
    )

    assert not issues
    assert caravan.body_type is CaravanBodyType.RIGID
    assert caravan.sleeping_area is CaravanSleepingArea.BOTH
    assert set(caravan.bed_types) == {BedType.MAKE_UP, BedType.ISLAND}
    assert caravan.kitchen_location is KitchenLocation.SIDE
    assert caravan.bathroom_layout is BathroomLayout.SEPARATE_SHOWER_TOILET
    assert caravan.lounge_location is LoungeLocation.FRONT
    assert caravan.heating is Heating.BLOWN_AIR
    assert caravan.refrigeration is Refrigeration.FRIDGE_FREEZER
    assert caravan.twin_axle is True
    assert caravan.microwave is True


def test_row_to_caravan_reads_the_four_lengths_apart() -> None:
    caravan, _ = caravan_io.row_to_caravan(
        _row(
            internal_length_mm=6332,
            exterior_body_length_mm=7060,
            shipping_length_mm=7905,
            awning_length_mm=10891,
            overall_width_mm=2433,
            height_mm=2582,
            headroom_mm=1960,
        )
    )

    assert caravan.internal_length_mm == 6332
    assert caravan.exterior_body_length_mm == 7060
    assert caravan.shipping_length_mm == 7905
    assert caravan.awning_length_mm == 10891
    assert caravan.hitch_length_mm == 845


def test_an_ambiguous_layout_group_is_reported_and_kept() -> None:
    """FMLV holds real caravans with two bathroom flags set — four in Bailey's export.

    Same rule as the motorhome side: keep the first, record the rest so writing back
    re-asserts them, and report rather than raise.
    """
    caravan, issues = caravan_io.row_to_caravan(
        _row(model="Ancona", rear_shower_toilet="Yes", separate_shower_toilet="Yes")
    )

    assert [issue.code for issue in issues] == ["ambiguous_layout_group"]
    assert caravan.bathroom_layout is BathroomLayout.REAR_SHOWER_TOILET
    assert "separate_shower_toilet" in caravan.extra_column_flags

    written = caravan_io.caravan_to_row(caravan)
    assert written["rear_shower_toilet"] == "Yes"
    assert written["separate_shower_toilet"] == "Yes"


def test_caravan_to_row_fills_every_column() -> None:
    row = caravan_io.caravan_to_row(Caravan(manufacturer="Bailey", model="Cabrera"))
    assert set(row) == set(caravan_schema.COLUMNS)


def test_write_csv_writes_the_schema_header_in_order(tmp_path: Path) -> None:
    path = tmp_path / "upload.csv"
    caravan_io.write_csv([Caravan(manufacturer="Bailey", model="Cabrera")], path)

    with path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))

    assert tuple(header) == caravan_schema.COLUMNS


def test_write_csv_can_offset_the_header_for_the_upload_site(tmp_path: Path) -> None:
    path = tmp_path / "upload.csv"
    caravan_io.write_csv(
        [Caravan(manufacturer="Bailey", model="Cabrera")], path, leading_blank_rows=2
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["-", "-"]
    assert lines[2].startswith("product_id,")


# --------------------------------------------------------------------------- #
# Against the real export
# --------------------------------------------------------------------------- #


@requires_real_export
def test_every_real_bailey_caravan_survives_a_round_trip(tmp_path: Path) -> None:
    """Read 81 real products, write them, read them back — nothing may change.

    This is the test that would catch a dropped column, a Yes/No written the wrong way
    round, or a layout flag lost to the single-select collapse.
    """
    original = caravan_io.read_xlsx(_REAL_EXPORT)
    assert len(original.caravans) == 81

    path = tmp_path / "round-trip.csv"
    caravan_io.write_csv(original.caravans, path)
    returned = caravan_io.read_csv(path)

    assert len(returned.caravans) == len(original.caravans)
    for before, after in zip(original.caravans, returned.caravans, strict=True):
        assert before == after, f"{before.key} did not survive the round trip"


@requires_real_export
def test_bailey_builds_only_rigid_caravans() -> None:
    """The requester's statement, held against their own data — 81 of 81."""
    result = caravan_io.read_xlsx(_REAL_EXPORT)

    assert {caravan.body_type for caravan in result.caravans} == {CaravanBodyType.RIGID}


@requires_real_export
def test_no_real_caravan_carries_an_optional_equipment_payload() -> None:
    result = caravan_io.read_xlsx(_REAL_EXPORT)

    assert all(
        caravan.optional_equipment_payload_kilograms is None for caravan in result.caravans
    )


@requires_real_export
def test_shipping_length_exceeds_body_length_on_every_real_product() -> None:
    """The invariant `validation._validate_caravan_lengths` leans on."""
    result = caravan_io.read_xlsx(_REAL_EXPORT)
    hitches = [
        caravan.hitch_length_mm
        for caravan in result.caravans
        if caravan.hitch_length_mm is not None
    ]

    assert len(hitches) == 76
    assert min(hitches) > 0
    assert (min(hitches), max(hitches)) == (845, 1500)


@requires_real_export
def test_validation_flags_only_fmlvs_own_gaps_and_discrepancies() -> None:
    """No false positives against real data — the point of validating warnings, not errors.

    The six payload mismatches are FMLV's published figures disagreeing with themselves
    (two by 1kg, one by 21kg, one by 49kg), and the missing required fields are the
    caravan export's own blanks. An adapter is what will fill those.
    """
    result = caravan_io.read_xlsx(_REAL_EXPORT)
    issues = validation.validate_all_caravans(result.caravans)

    codes = {issue.code for issue in issues}
    assert codes <= {"missing_required", "payload_mismatch"}
    assert sum(issue.code == "payload_mismatch" for issue in issues) == 6
    assert not [issue for issue in issues if issue.code == "shipping_length_not_longer"]


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def _complete(**overrides: object) -> Caravan:
    """A caravan with every REQUIRED field filled, so a test can break exactly one."""
    caravan = Caravan(
        manufacturer="Bailey",
        manufacturer_display_name="Bailey",
        manufacturer_range="Unicorn Deluxe",
        model="Cabrera",
        berths=4,
        rrp_pounds=32499,
        mtplm_kilograms=1708,
        mro_kilograms=1544,
        personal_effects_payload_kilograms=164,
        internal_length_mm=6332,
        overall_width_mm=2433,
        exterior_body_length_mm=7060,
        shipping_length_mm=7905,
        height_mm=2582,
        awning_length_mm=10891,
        headroom_mm=1960,
        body_type=CaravanBodyType.RIGID,
        sleeping_area=CaravanSleepingArea.BOTH,
        kitchen_location=KitchenLocation.SIDE,
        bathroom_layout=BathroomLayout.SEPARATE_SHOWER_TOILET,
        lounge_location=LoungeLocation.FRONT,
        heating=Heating.BLOWN_AIR,
    )
    return caravan.model_copy(update=overrides)


def test_a_complete_caravan_raises_nothing() -> None:
    assert validation.validate_caravan(_complete()) == []


def test_swapping_the_two_length_columns_is_an_error() -> None:
    """The single most plausible way to get a caravan adapter wrong.

    Both are lengths, both sit in the same spec table, and on any one product either
    ordering looks reasonable — so it would be wrong on every product at once and quiet
    in review. Hence a check rather than a reviewer's eye.
    """
    swapped = _complete(exterior_body_length_mm=7905, shipping_length_mm=7060)

    issues = validation.validate_caravan(swapped)

    assert [issue.code for issue in issues] == ["shipping_length_not_longer"]
    assert issues[0].severity == "error"
    assert "swapped" in issues[0].message


def test_equal_lengths_are_an_error_too() -> None:
    """The hitch has to add something — equal figures mean one was read for the other."""
    issues = validation.validate_caravan(
        _complete(exterior_body_length_mm=7905, shipping_length_mm=7905)
    )

    assert [issue.code for issue in issues] == ["shipping_length_not_longer"]


def test_an_implausible_hitch_allowance_is_only_a_warning() -> None:
    """Outside 500-2000mm is suspicious, not impossible — no caravan gets rejected for it."""
    issues = validation.validate_caravan(
        _complete(exterior_body_length_mm=7000, shipping_length_mm=7100)
    )

    assert [issue.code for issue in issues] == ["implausible_hitch_length"]
    assert issues[0].severity == "warning"


def test_a_missing_length_is_not_treated_as_a_swap() -> None:
    """No exterior body length means no swap to detect — and it is not required either.

    Bailey publish internal and shipping length and nothing between them, which the
    requester reads as an industry trend rather than one brand's omission (3 September
    2026). So the field is out of scope and out of REQUIRED: a caravan without it is
    complete, not deficient.
    """
    issues = validation.validate_caravan(_complete(exterior_body_length_mm=None))

    assert issues == []


def test_the_payload_check_uses_personal_effects_when_optional_is_blank() -> None:
    issues = validation.validate_caravan(_complete(personal_effects_payload_kilograms=200))

    assert [issue.code for issue in issues] == ["payload_mismatch"]
    assert issues[0].severity == "warning"


def test_the_payload_check_counts_both_columns_when_both_are_filled() -> None:
    """Rare — none of the 92 real products — but the formula is the sum of the two."""
    issues = validation.validate_caravan(
        _complete(
            personal_effects_payload_kilograms=120,
            optional_equipment_payload_kilograms=44,
        )
    )

    assert issues == []


def test_a_caravan_is_never_asked_for_a_base_vehicle() -> None:
    """The motorhome schema makes `base_vehicle_manufacturer` REQUIRED; caravans have none."""
    assert "base_vehicle_manufacturer" not in caravan_schema.REQUIRED
    assert not hasattr(Caravan(), "base_vehicle_manufacturer")
