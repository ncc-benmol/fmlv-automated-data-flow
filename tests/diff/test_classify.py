"""Unit tests for the top-level match + diff + classify orchestration."""

from __future__ import annotations

from datetime import date

from src.adapters.base import ExtractedMotorhome, Provenance
from src.diff.classify import ChangeKind, diff_products
from src.product_model.model import Motorhome


def make_baseline(**overrides: object) -> Motorhome:
    fields: dict[str, object] = {
        "product_id": 101,
        "manufacturer": "Adria Mobil",
        "manufacturer_range": "Matrix",
        "model": "Supreme 670 DC",
        "rrp_pounds": 75950,
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
        provenance={"rrp_pounds": Provenance(source_url="https://example.com", snippet="x")},
    )


def test_matched_product_with_a_changed_field_is_classified_changed_field() -> None:
    baseline = make_baseline(rrp_pounds=75950)
    extracted = make_extracted(rrp_pounds=76950)

    diffs = diff_products([extracted], [baseline])

    assert len(diffs) == 1
    assert diffs[0].kind == ChangeKind.CHANGED_FIELD
    assert diffs[0].fmlv_product_id == 101
    assert [c.field for c in diffs[0].changes] == ["rrp_pounds"]


def test_matched_product_with_no_changes_is_unchanged_confirmed() -> None:
    baseline = make_baseline(rrp_pounds=75950)
    extracted = make_extracted(rrp_pounds=75950)

    diffs = diff_products([extracted], [baseline])

    assert len(diffs) == 1
    assert diffs[0].kind == ChangeKind.UNCHANGED_CONFIRMED
    assert diffs[0].confirmed_fields == ["rrp_pounds"]
    assert diffs[0].changes == []


def test_unmatched_scraped_product_is_a_new_product_with_blank_product_id() -> None:
    extracted = make_extracted(
        rrp_pounds=99950, manufacturer_range="Coral", model="Axess 600 SP"
    )

    diffs = diff_products([extracted], [])

    assert len(diffs) == 1
    assert diffs[0].kind == ChangeKind.NEW_PRODUCT
    assert diffs[0].fmlv_product_id is None
    assert diffs[0].baseline is None


def test_baseline_product_not_seen_this_run_is_disappeared() -> None:
    baseline = make_baseline()

    diffs = diff_products([], [baseline])

    assert len(diffs) == 1
    assert diffs[0].kind == ChangeKind.DISAPPEARED
    assert diffs[0].fmlv_product_id == 101
    assert diffs[0].extracted is None


def test_changed_field_in_rollover_window_is_flagged_eligible() -> None:
    baseline = make_baseline(rrp_pounds=75950)
    extracted = make_extracted(rrp_pounds=76950)

    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))

    assert diffs[0].year_rollover_eligible is True


def test_changed_field_outside_rollover_window_is_not_flagged() -> None:
    baseline = make_baseline(rrp_pounds=75950)
    extracted = make_extracted(rrp_pounds=76950)

    diffs = diff_products([extracted], [baseline], today=date(2026, 1, 15))

    assert diffs[0].year_rollover_eligible is False


def test_unchanged_confirmed_is_never_flagged_even_in_season() -> None:
    baseline = make_baseline(rrp_pounds=75950)
    extracted = make_extracted(rrp_pounds=75950)

    diffs = diff_products([extracted], [baseline], today=date(2026, 7, 15))

    assert diffs[0].kind == ChangeKind.UNCHANGED_CONFIRMED
    assert diffs[0].year_rollover_eligible is False


def test_mixed_run_produces_one_diff_per_product_never_silent() -> None:
    still_here = make_baseline(product_id=101, rrp_pounds=75950)
    gone = make_baseline(
        product_id=202, manufacturer_range="Coral", model="Axess 600 SP", rrp_pounds=60000
    )
    scraped_still_here = make_extracted(rrp_pounds=76950)
    scraped_new = make_extracted(
        rrp_pounds=45000, manufacturer_range="Sonic", model="Axess 600 SL"
    )

    diffs = diff_products([scraped_still_here, scraped_new], [still_here, gone])

    kinds = {d.kind for d in diffs}
    assert kinds == {ChangeKind.CHANGED_FIELD, ChangeKind.NEW_PRODUCT, ChangeKind.DISAPPEARED}
    assert len(diffs) == 3
