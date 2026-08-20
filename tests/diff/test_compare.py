"""Unit tests for field-level diffing between a baseline and a scraped product."""

from __future__ import annotations

from src.adapters.base import ExtractedMotorhome, Provenance
from src.diff.compare import MissingField, compare_fields, sort_changes
from src.product_model.enums import BodyType
from src.product_model.model import AutomaticVariant, Motorhome

BASELINE = Motorhome(
    product_id=101,
    manufacturer="Adria Mobil",
    manufacturer_range="Matrix",
    model="Supreme 670 DC",
    rrp_pounds=75950,
    mro_kilograms=2944,
    mtplm_kilograms=3500,
    body_type=BodyType.COACH_BUILT_LOW_PROFILE,
)


def test_field_with_no_provenance_is_never_compared() -> None:
    # The adapter never looked at body_type, so it must not show up as a "change"
    # even though the scraped Motorhome's body_type differs (it's just unset/None).
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(rrp_pounds=75950),
        provenance={"rrp_pounds": Provenance(source_url="https://example.com", snippet="x")},
    )
    changes, confirmed, _missing = compare_fields(BASELINE, extracted)
    assert changes == []
    assert confirmed == ["rrp_pounds"]


def test_changed_numeric_field_is_reported() -> None:
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(rrp_pounds=76950),
        provenance={
            "rrp_pounds": Provenance(source_url="https://example.com", snippet="RRP £76,950")
        },
    )
    changes, confirmed, _missing = compare_fields(BASELINE, extracted)
    assert confirmed == []
    assert len(changes) == 1
    change = changes[0]
    assert change.field == "rrp_pounds"
    assert change.old_value == 75950
    assert change.new_value == 76950
    assert change.priority == "tracked_numeric"
    assert change.high_suspicion is False
    assert change.provenance is not None
    assert change.provenance.snippet == "RRP £76,950"


def test_layout_flag_change_on_existing_product_is_high_suspicion() -> None:
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(body_type=BodyType.A_CLASS),
        provenance={"body_type": Provenance(source_url="https://example.com", snippet="A-class")},
    )
    changes, _confirmed, _missing = compare_fields(BASELINE, extracted)
    assert len(changes) == 1
    assert changes[0].priority == "layout"
    assert changes[0].high_suspicion is True


def test_nested_automatic_field_is_diffed_via_dotted_path() -> None:
    baseline = Motorhome(
        product_id=101,
        mtplm_kilograms=3500,
        automatic=AutomaticVariant(mro_kilograms=2972),
    )
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(automatic=AutomaticVariant(mro_kilograms=3000)),
        provenance={
            "automatic.mro_kilograms": Provenance(source_url="https://example.com", snippet="x")
        },
    )
    changes, _confirmed, _missing = compare_fields(baseline, extracted)
    assert len(changes) == 1
    assert changes[0].old_value == 2972
    assert changes[0].new_value == 3000
    assert changes[0].priority == "tracked_numeric"


def test_sort_changes_puts_tracked_numerics_before_layout_flags() -> None:
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(rrp_pounds=76950, body_type=BodyType.A_CLASS),
        provenance={
            "body_type": Provenance(source_url="https://example.com", snippet="A-class"),
            "rrp_pounds": Provenance(source_url="https://example.com", snippet="RRP"),
        },
    )
    changes, _confirmed, _missing = compare_fields(BASELINE, extracted)
    ordered = sort_changes(changes)
    assert [change.field for change in ordered] == ["rrp_pounds", "body_type"]


def test_in_scope_field_not_extracted_is_reported_missing() -> None:
    # The adapter attempted rrp_pounds but never found mro_kilograms this run —
    # BASELINE has one (2944). mro_kilograms is in_scope (schema.IN_SCOPE), so it
    # must be surfaced for the reviewer to confirm/replace, not silently skipped.
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(rrp_pounds=75950),
        provenance={"rrp_pounds": Provenance(source_url="https://example.com", snippet="x")},
    )
    _changes, _confirmed, missing = compare_fields(BASELINE, extracted)
    assert MissingField(field="mro_kilograms", old_value=2944) in missing


def test_out_of_scope_field_not_extracted_is_never_reported_missing() -> None:
    # body_type is not in schema.IN_SCOPE, so an adapter that never attempts it
    # (like Adria's, for the ~40 layout flags) must not be nagged about it.
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(rrp_pounds=75950),
        provenance={"rrp_pounds": Provenance(source_url="https://example.com", snippet="x")},
    )
    _changes, _confirmed, missing = compare_fields(BASELINE, extracted)
    assert all(m.field != "body_type" for m in missing)


def test_in_scope_field_with_no_baseline_value_is_never_reported_missing() -> None:
    # Nothing on record for berths on either side — no baseline figure to fall
    # back on, so there is nothing actionable to ask the reviewer about.
    baseline = Motorhome(product_id=101, rrp_pounds=75950)
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(rrp_pounds=75950),
        provenance={"rrp_pounds": Provenance(source_url="https://example.com", snippet="x")},
    )
    _changes, _confirmed, missing = compare_fields(baseline, extracted)
    assert all(m.field != "berths" for m in missing)


def test_in_scope_field_extracted_without_provenance_is_never_reported_missing() -> None:
    # An adapter (like Adria's) can set an identity field like manufacturer_range
    # directly, with no provenance entry, purely to build the product's key. That's
    # a value the adapter *did* find — it must not be flagged "missing" just
    # because there's no citable source snippet for it.
    extracted = ExtractedMotorhome(
        motorhome=Motorhome(manufacturer_range="Matrix", rrp_pounds=75950),
        provenance={"rrp_pounds": Provenance(source_url="https://example.com", snippet="x")},
    )
    _changes, _confirmed, missing = compare_fields(BASELINE, extracted)
    assert all(m.field != "manufacturer_range" for m in missing)
