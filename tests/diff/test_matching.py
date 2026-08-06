"""Unit tests for token-based product matching."""

from __future__ import annotations

from src.adapters.base import ExtractedMotorhome
from src.diff.matching import match_products, token_similarity
from src.product_model.model import Motorhome


def make_motorhome(**overrides: object) -> Motorhome:
    fields: dict[str, object] = {
        "manufacturer": "Adria Mobil",
        "manufacturer_range": "Matrix",
        "model": "Supreme 670 DC",
        "product_id": 12345,
    }
    fields.update(overrides)
    return Motorhome(**fields)


def make_extracted(**overrides: object) -> ExtractedMotorhome:
    return ExtractedMotorhome(motorhome=make_motorhome(product_id=None, **overrides))


def test_exact_range_and_model_match_scores_one() -> None:
    baseline = make_motorhome()
    scraped = make_extracted(manufacturer_range="Matrix", model="Supreme 670 DC")
    assert token_similarity(baseline, scraped.motorhome) == 1.0


def test_word_order_difference_still_matches() -> None:
    # Adria's site: "670 DC" (layout) + "Supreme Alde RHD" (trim) vs baseline's
    # "Supreme 670 DC" — same words, different order/extra trim words (see
    # docs/adapters/adria.md).
    baseline = make_motorhome(manufacturer_range="Matrix", model="Supreme 670 DC")
    scraped = make_extracted(manufacturer_range="Matrix", model="670 DC Supreme Alde RHD")
    results = match_products([scraped], [baseline])
    assert len(results) == 1
    assert results[0].baseline is baseline
    assert results[0].method == "fuzzy"
    assert 0.5 <= results[0].score < 1.0


def test_unrelated_product_does_not_match() -> None:
    baseline = make_motorhome(manufacturer_range="Matrix", model="Supreme 670 DC")
    scraped = make_extracted(manufacturer_range="Coral", model="Axess 600 SP")
    results = match_products([scraped], [baseline])
    assert results[0].baseline is None
    assert results[0].method is None
    assert results[0].score == 0.0


def test_one_to_one_assignment_does_not_double_match_a_baseline_row() -> None:
    baseline = make_motorhome(manufacturer_range="Matrix", model="Supreme 670 DC")
    best = make_extracted(manufacturer_range="Matrix", model="Supreme 670 DC")
    worse = make_extracted(manufacturer_range="Matrix", model="670 DC Supreme Alde RHD")

    results = match_products([worse, best], [baseline])

    matched = [r for r in results if r.baseline is not None]
    assert len(matched) == 1
    # The exact match wins the shared baseline row even though it was scored second.
    assert matched[0].extracted is best
    assert matched[0].method == "exact"


def test_new_product_with_no_baseline_candidates_is_unmatched() -> None:
    scraped = make_extracted(manufacturer_range="Coral", model="Axess 600 SP")
    results = match_products([scraped], [])
    assert results[0].baseline is None
    assert results[0].baseline_index is None


def test_threshold_can_be_tightened() -> None:
    baseline = make_motorhome(manufacturer_range="Matrix", model="Supreme 670 DC")
    scraped = make_extracted(manufacturer_range="Matrix", model="670 DC Supreme Alde RHD")
    results = match_products([scraped], [baseline], threshold=0.9)
    assert results[0].baseline is None
