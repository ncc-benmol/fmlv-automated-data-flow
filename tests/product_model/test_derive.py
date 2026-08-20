"""Tests for the mirrored-field derivation.

`price_min_range_pounds` is in scope but no adapter reads it, because FMLV holds it
equal to `rrp_pounds` on every product in every baseline export rather than publishing
it separately. Without this derivation the reviewer is asked to confirm it by hand on
every matched product of every manufacturer — see `product_model.derive`.
"""

from __future__ import annotations

from src.adapters.base import ExtractedMotorhome, Provenance
from src.product_model.derive import MIRRORED_FIELDS, apply_mirrored_fields
from src.product_model.model import Motorhome
from src.product_model.schema import IN_SCOPE


def _extracted(**overrides: object) -> ExtractedMotorhome:
    motorhome = Motorhome(manufacturer="Bailey", manufacturer_range="Adamo", model="69-4")
    for field, value in overrides.items():
        setattr(motorhome, field, value)
    return ExtractedMotorhome(motorhome=motorhome)


def test_every_mirrored_field_is_actually_in_scope() -> None:
    # A mirrored field that isn't in scope would be pointless work: nothing asks for it.
    assert set(MIRRORED_FIELDS) <= IN_SCOPE


def test_every_mirror_source_is_a_real_motorhome_field() -> None:
    for target, source in MIRRORED_FIELDS.items():
        assert target in Motorhome.model_fields
        assert source in Motorhome.model_fields


def test_price_min_range_is_mirrored_from_the_guide_price() -> None:
    item = _extracted(rrp_pounds=81899)

    assert apply_mirrored_fields([item]) == 1
    assert item.motorhome.price_min_range_pounds == 81899


def test_a_mirrored_field_gets_provenance_so_it_counts_as_attempted() -> None:
    # Without a provenance entry `diff.compare.compare_fields` treats the field as never
    # attempted and raises the "not found this run" prompt regardless of the value.
    item = _extracted(rrp_pounds=81899)

    apply_mirrored_fields([item])

    provenance = item.provenance["price_min_range_pounds"]
    assert "mirrored from rrp_pounds" in provenance.snippet
    assert "81899" in provenance.snippet


def test_the_mirrored_provenance_reuses_the_sources_url_when_there_is_one() -> None:
    item = _extracted(rrp_pounds=81899)
    item.provenance["rrp_pounds"] = Provenance(
        source_url="https://www.baileyofbristol.co.uk/motorhomes/adamo/adamo-69-4/",
        snippet="OTR price: £81,899",
    )

    apply_mirrored_fields([item])

    assert item.provenance["price_min_range_pounds"].source_url == (
        "https://www.baileyofbristol.co.uk/motorhomes/adamo/adamo-69-4/"
    )


def test_no_price_means_no_mirrored_price_rather_than_a_fabricated_one() -> None:
    # Swift, Rimor and Chausson publish no price at all. Mirroring a None into the
    # duplicate would claim a reading that was never made; the field must stay missing.
    item = _extracted(rrp_pounds=None)

    assert apply_mirrored_fields([item]) == 0
    assert item.motorhome.price_min_range_pounds is None
    assert "price_min_range_pounds" not in item.provenance


def test_a_value_an_adapter_read_itself_is_never_overwritten() -> None:
    item = _extracted(rrp_pounds=81899, price_min_range_pounds=79999)

    assert apply_mirrored_fields([item]) == 0
    assert item.motorhome.price_min_range_pounds == 79999
    assert "price_min_range_pounds" not in item.provenance


def test_it_counts_across_every_product_it_is_given() -> None:
    items = [_extracted(rrp_pounds=1000), _extracted(rrp_pounds=2000), _extracted()]

    assert apply_mirrored_fields(items) == 2
