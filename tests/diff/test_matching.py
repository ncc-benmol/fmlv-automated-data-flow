"""Unit tests for token-based product matching."""

from __future__ import annotations

import pytest

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


# --- Model codes spaced one way and closed up the other (docs/adapters/sunlight.md) ---


def test_spaced_model_code_matches_the_closed_up_baseline() -> None:
    # Sunlight's MY27 price list prints "V 60" and renamed the range at the same time;
    # FMLV holds the layout as "Van Adventure Edition" / "V60".
    baseline = make_motorhome(manufacturer_range="Van Adventure Edition", model="V60")
    scraped = make_extracted(manufacturer_range="Van Adventure", model="V 60")
    results = match_products([scraped], [baseline])
    assert results[0].baseline is baseline
    assert results[0].method == "fuzzy"


def test_code_with_a_trailing_letter_matches_however_it_is_spaced() -> None:
    # "V 67 S" (baseline) and "V 67S" (price list) are one layout, not two.
    baseline = make_motorhome(manufacturer_range="Van Adventure Edition", model="V 67 S")
    scraped = make_extracted(manufacturer_range="Van Adventure", model="V 67S")
    results = match_products([scraped], [baseline])
    assert results[0].baseline is baseline


def test_a_trailing_letter_still_distinguishes_two_real_layouts() -> None:
    # Sunlight sells both a CLIFF 540 and a CLIFF 540 V. Gluing the code back together
    # must not glue these two into one (sunlight.py's parser exists to keep them apart).
    baseline = make_motorhome(manufacturer_range="CLIFF Adventure", model="CLIFF 540")
    scraped = make_extracted(manufacturer_range="CLIFF Vanlife", model="CLIFF 540 V")
    results = match_products([scraped], [baseline])
    assert results[0].baseline is None


def test_siblings_sharing_a_range_but_not_a_code_do_not_match() -> None:
    # A two-word range name is half the token bag, which was enough on its own to drag
    # two different layouts up to the threshold.
    baseline = make_motorhome(manufacturer_range="Low Profiles", model="T65")
    scraped = make_extracted(manufacturer_range="Low Profiles", model="T 66S")
    results = match_products([scraped], [baseline])
    assert results[0].baseline is None
    assert token_similarity(baseline, scraped.motorhome) == 0.0


def test_a_code_on_only_one_side_does_not_block_a_match() -> None:
    # The code gate applies only when *both* names carry one; a trim-only name is not
    # disqualified for having no digits to agree about.
    baseline = make_motorhome(manufacturer_range="Matrix", model="Supreme Plus")
    scraped = make_extracted(manufacturer_range="Matrix", model="Supreme Plus 670")
    results = match_products([scraped], [baseline])
    assert results[0].baseline is baseline


def test_adria_layout_code_plus_trim_is_unaffected_by_code_joining() -> None:
    # "DC" is two letters, so it is left alone rather than glued to "670" — the case
    # DEFAULT_THRESHOLD was calibrated against must not move.
    baseline = make_motorhome(manufacturer_range="Matrix", model="Supreme 670 DC")
    scraped = make_extracted(manufacturer_range="Matrix", model="670 DC Supreme Alde RHD")
    # 2/3 — the score the old word-bag tokeniser gave this pair, unchanged.
    assert token_similarity(baseline, scraped.motorhome) == pytest.approx(2 / 3)


# --- Which duplicate baseline row an update lands on ---


def test_live_baseline_row_wins_over_an_archived_duplicate() -> None:
    # FMLV's export is a history: Sunlight's "Coachbuilts A60" is in it twice, archived
    # 2022 and live 2026. An update belongs on the live row.
    archived = make_motorhome(
        manufacturer_range="Coachbuilts", model="A60", product_id=3524, year=2022, archived=True
    )
    live = make_motorhome(
        manufacturer_range="Coachbuilts", model="A60", product_id=6562, year=2026, archived=False
    )
    scraped = make_extracted(manufacturer_range="Coachbuilts Root", model="A 60")

    results = match_products([scraped], [archived, live])

    assert results[0].baseline is live


def test_newest_year_wins_between_two_live_duplicates() -> None:
    older = make_motorhome(
        manufacturer_range="Low Profiles", model="T58", product_id=3536, year=2022
    )
    newer = make_motorhome(
        manufacturer_range="Low Profiles", model="T58", product_id=7982, year=2026
    )
    scraped = make_extracted(manufacturer_range="Low Profiles", model="T 58")

    results = match_products([scraped], [older, newer])

    assert results[0].baseline is newer
