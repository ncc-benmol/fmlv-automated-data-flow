"""Read/write tests for the FMLV motorhome export, against the real Adria sample."""

from __future__ import annotations

from pathlib import Path

import pytest

from fmlv_automated_data_flow.fmlv import io, validation

ADRIA_EXPORT = (
    Path(__file__).parents[2]
    / "csv-examples"
    / "1785753111-adria-caravans-motorhomes-product-exports"
    / "motorhome-campervans.xlsx"
)


@pytest.fixture(scope="module")
def adria_result() -> io.ReadResult:
    return io.read_xlsx(ADRIA_EXPORT)


def test_reads_every_row(adria_result: io.ReadResult) -> None:
    # The workbook has 41 data rows beneath the header.
    assert len(adria_result.motorhomes) == 41


def test_known_product_reads_correctly(adria_result: io.ReadResult) -> None:
    supreme_640 = next(m for m in adria_result.motorhomes if m.model == "Supreme 640 SLB")

    assert supreme_640.product_id == 3914
    assert supreme_640.manufacturer == "Adria Mobil"
    assert supreme_640.manufacturer_display_name == "Adria"
    assert supreme_640.manufacturer_range == "TWIN"
    assert supreme_640.rrp_pounds == 75950
    assert supreme_640.mro_kilograms == 2944
    assert supreme_640.mtplm_kilograms == 3500
    assert supreme_640.mh_payload_kilograms == 556
    assert supreme_640.berths == 2
    assert supreme_640.archived is False

    # Layout groups collapsed to their enum, not left as 40 raw flags.
    assert supreme_640.sleeping_area.value == "sleeping_area_both"
    assert supreme_640.kitchen_location.value == "side_kitchen"
    assert supreme_640.bathroom_layout.value == "side_shower_toilet"
    assert supreme_640.heating.value == "blown_air_heating"
    assert supreme_640.refrigeration.value == "fridge_freezer"
    assert supreme_640.rear_garage is True

    # Automatic-gearbox variant present and distinct from the manual figures.
    assert supreme_640.automatic is not None
    assert supreme_640.automatic.rrp_pounds == 80095
    assert supreme_640.automatic.mro_kilograms == 2972

    assert len(supreme_640.images) == 13


def test_flags_ambiguous_layout_groups_without_raising(adria_result: io.ReadResult) -> None:
    # Two rows in the real export have both blown-air and wet-central heating ticked.
    ambiguous = [i for i in adria_result.issues if i.code == "ambiguous_layout_group"]
    assert len(ambiguous) == 2
    assert all(i.field == "Heating" for i in ambiguous)


def test_validation_flags_payload_mismatches_without_raising(
    adria_result: io.ReadResult,
) -> None:
    # payload == mtplm - mro holds for most rows; a handful of genuine data-entry
    # mismatches in the sample export should surface as warnings, not crash validation.
    issues = validation.validate_all(adria_result.motorhomes)
    mismatches = [i for i in issues if i.code == "payload_mismatch"]
    assert len(mismatches) == 5
    assert all(i.severity == "warning" for i in mismatches)


def test_round_trip_through_csv_is_lossless(adria_result: io.ReadResult, tmp_path: Path) -> None:
    out_path = tmp_path / "roundtrip.csv"
    io.write_csv(adria_result.motorhomes, out_path)

    reread = io.read_csv(out_path)

    assert reread.motorhomes == adria_result.motorhomes
    # The writer always emits exactly one Yes per single-select group (or none), so a
    # round trip resolves any ambiguity the original file had — re-reading our own
    # output can never raise an "ambiguous_layout_group" issue.
    assert reread.issues == []


def test_write_csv_preserves_column_order(adria_result: io.ReadResult, tmp_path: Path) -> None:
    from fmlv_automated_data_flow.fmlv import schema

    out_path = tmp_path / "order.csv"
    io.write_csv(adria_result.motorhomes, out_path)

    header = out_path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header == list(schema.COLUMNS)
