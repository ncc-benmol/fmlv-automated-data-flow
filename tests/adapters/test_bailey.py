"""Tests for the Bailey adapter's pure parsing functions, against real captured pages.

The fixtures are (trimmed) real pages fetched 20 August 2026 — see
`docs/adapters/bailey.md`. Trimming keeps only the hero price banner and the "Technical
specification" section, which is everything `parse_model_page` reads; verified to parse
identically to the untrimmed page before being saved. No network here.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.adapters.bailey import (
    RANGE_NAME_CORRECTIONS,
    BaileyProduct,
    _field,
    _hero_price,
    _is_blank,
    _kilograms,
    _leading_int,
    _metres_to_mm,
    _reconciles,
    find_model_urls,
    parse_model_page,
)
from src.product_model.enums import BodyType

FIXTURES = Path(__file__).parent / "fixtures"


def _page(name: str) -> str:
    return (FIXTURES / f"bailey_{name}.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Low-level value extraction
# --------------------------------------------------------------------------- #


def test_metres_to_mm_reads_the_leading_metric_figure() -> None:
    assert _metres_to_mm("6.096m / 20′ 0″") == 6096


def test_kilograms_strips_the_unit() -> None:
    assert _kilograms("3500kg") == 3500


def test_kilograms_reads_a_decimal_figure_without_truncating_it() -> None:
    # A digits-and-commas-only pattern matches just the "5" out of "3431.5kg" and
    # silently returns a 5kg motorhome — the real failure on Autograph IV 79-4F.
    assert _kilograms("3431.5kg") == 3432


def test_leading_int_reads_the_first_number() -> None:
    assert _leading_int("2") == 2


def test_hero_price_reads_the_otr_banner() -> None:
    html = '<small class="t3 mr-2">OTR</small> £75,999'
    assert _hero_price(html) == 75999


def test_is_blank_treats_a_bare_unit_with_no_figure_as_blank() -> None:
    # Bailey's own unfilled template row: "m /" with nothing between the unit and the slash.
    assert _is_blank("m /") is True
    assert _is_blank("£") is True


def test_is_blank_does_not_mistake_real_content_for_empty() -> None:
    assert _is_blank("Low Profile") is False
    assert _is_blank("Adamo") is False
    assert _is_blank("6.096m / 20′ 0″") is False
    assert _is_blank("3500kg") is False


def test_field_skips_an_earlier_unfilled_occurrence() -> None:
    # Bailey repeats several labels in a top-of-page summary block that is sometimes left
    # empty (or, for campervans, HTML-commented out) ahead of the real, populated row in
    # the "Technical specification" section further down the same page.
    html = (
        '<div class="col-6 pl-0 b3b">Overall Height</div>'
        '<div class="col-6 pl-0 b3">m / </div>'
        '<div class="col-6 pl-0 b3b">Overall Height</div>'
        '<div class="col-6 pl-0 b3">2.824m / 9′ 3″</div>'
    )
    assert _field(html, "Overall Height") == "2.824m / 9′ 3″"


def test_field_skips_a_wrapping_span_on_either_side() -> None:
    # The top-of-page MRO row wraps both the label and the value in a <span>, for a
    # tooltip "more info" link that sits alongside the figure.
    html = (
        '<div class="col-6 pl-0 b3b"><span>MRO</span></div>'
        '<div class="col-6 pl-0 b3"><span class="mr-1">2827kg</span>'
        '<a href="#">more info</a></div>'
    )
    assert _field(html, "MRO") == "2827kg"


# --------------------------------------------------------------------------- #
# Finding model links, scoped to one range
# --------------------------------------------------------------------------- #


def test_find_model_urls_is_scoped_to_its_own_range_path() -> None:
    html = (
        '<a href="https://www.baileyofbristol.co.uk/motorhomes/adamo/adamo-60-2/">A</a>'
        '<a href="https://www.baileyofbristol.co.uk/motorhomes/alora/alora-69-4i/">B</a>'
    )
    assert find_model_urls(html, "motorhomes/adamo") == [
        "https://www.baileyofbristol.co.uk/motorhomes/adamo/adamo-60-2/"
    ]


def test_find_model_urls_deduplicates_repeated_links() -> None:
    html = '<a href="https://www.baileyofbristol.co.uk/motorhomes/adamo/adamo-60-2/">A</a>' * 3
    assert find_model_urls(html, "motorhomes/adamo") == [
        "https://www.baileyofbristol.co.uk/motorhomes/adamo/adamo-60-2/"
    ]


# --------------------------------------------------------------------------- #
# Whole-page parsing against the real fixtures
# --------------------------------------------------------------------------- #


def test_adamo_60_2_parses_every_field() -> None:
    product = parse_model_page(_page("adamo_60_2"), is_campervan=False)

    assert product.range_label == "Adamo"
    assert product.model == "60-2"
    assert product.base_vehicle_manufacturer == "Ford"
    assert product.roof_profile_published == "Low Profile"
    assert product.mh_length_mm == 6096
    assert product.mh_width_mm == 2393  # mirrors folded, not extended (2740)
    assert product.mh_height_mm == 2863
    assert product.mtplm_kilograms == 3500
    assert product.mro_kilograms == 2827
    assert product.mh_payload_kilograms_published == 673
    assert product.mh_passenger_seats_inc_driver == 2
    assert product.berths == 2
    assert product.rrp_pounds == 75999
    assert product.body_type == BodyType.COACH_BUILT_LOW_PROFILE
    assert _reconciles(product) is True


def test_endeavour_b62_reads_the_hero_price_because_the_labelled_row_is_dead() -> None:
    # The "Technical specification" section's own `OTR Price` row is HTML-commented out
    # on every campervan page — a block copy-pasted from Bailey's caravan template ("your
    # new Bailey caravan" survives in its tooltip) and disabled rather than adapted.
    product = parse_model_page(_page("endeavour_b62"), is_campervan=True)

    assert product.range_label == "Endeavour"
    assert product.model == "B62"
    assert product.base_vehicle_manufacturer == "Ford"
    assert product.roof_profile_published == "H3"
    assert product.mh_height_mm == 2824
    assert product.rrp_pounds == 72999
    assert product.body_type == BodyType.CAMPERVAN_HIGH_TOP  # 2824mm clears the threshold
    assert _reconciles(product) is True


def test_adamo_xl_i_is_not_split_into_a_separate_range() -> None:
    # Requester's decision, 2026-08-20: XL-I/XL-T/XL-DL are models within Adamo, not a
    # second range, even though FMLV currently holds "Adamo XL" as its own range. No
    # 'XL-' prefix splitting happens here.
    product = parse_model_page(_page("adamo_xl_i"), is_campervan=False)

    assert product.range_label == "Adamo"
    assert product.model == "XL-I"
    assert product.mtplm_kilograms == 4250  # the heavier XL chassis class
    assert _reconciles(product) is True


def test_autograph_is_corrected_to_autograph_iv() -> None:
    product = parse_model_page(_page("autograph_72_2"), is_campervan=False)

    assert product.range_label == "Autograph IV"  # site says "Autograph"
    assert product.model == "72-2"
    # The base vehicle brand is "Peugeot" (from "Cab"), not "AL-KO" (from "Chassis") —
    # AL-KO AMC is a subframe system bolted onto the Peugeot cab, not a vehicle
    # manufacturer, and it disagrees with Cab, unlike every Ford-based range surveyed
    # where the two fields happen to agree. See test_cab_is_preferred_over_chassis below.
    assert product.base_vehicle_manufacturer == "Peugeot"
    assert _reconciles(product) is True


def test_cab_is_preferred_over_chassis_because_chassis_can_name_a_subframe() -> None:
    html = (
        '<div class="col-6 pl-0 b3b">Range</div><div class="col-6 pl-0 b3">Autograph</div>'
        '<div class="col-6 pl-0 b3b">Model</div><div class="col-6 pl-0 b3">72-2</div>'
        '<div class="col-6 pl-0 b3b">Cab</div><div class="col-6 pl-0 b3">Peugeot Cab (Graphite)</div>'
        '<div class="col-6 pl-0 b3b">Chassis</div><div class="col-6 pl-0 b3">AL-KO AMC</div>'
    )
    product = parse_model_page(html, is_campervan=False)
    assert product.base_vehicle_manufacturer == "Peugeot"


def test_a_decimal_kilogram_figure_is_not_truncated_at_the_decimal_point() -> None:
    # Autograph IV 79-4F publishes MRO as "3431.5kg". A digits-and-commas-only pattern
    # matches the "5" out of ".5kg" and silently returns a 5kg motorhome — this is what a
    # live run against the real site actually did before `_kilograms` allowed a decimal.
    product = parse_model_page(_page("autograph_79_4f"), is_campervan=False)

    assert product.mro_kilograms == 3432  # 3431.5 rounded
    assert product.mh_payload_kilograms_published == 1068  # 1068.5 rounded
    assert product.mtplm_kilograms == 4500
    assert _reconciles(product) is True


def test_range_name_corrections_only_contains_autograph() -> None:
    # Adamo has deliberately no entry — see the module docstring and the test above.
    assert RANGE_NAME_CORRECTIONS == {"Autograph": "Autograph IV"}


# --------------------------------------------------------------------------- #
# Body type
# --------------------------------------------------------------------------- #


def _product(**overrides: object) -> BaileyProduct:
    defaults: dict[str, object] = {
        "range_label": "Adamo",
        "model": "60-2",
        "is_campervan": False,
    }
    return BaileyProduct(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_low_profile_maps_to_coach_built_low_profile() -> None:
    product = _product(roof_profile_published="Low Profile")
    assert product.body_type == BodyType.COACH_BUILT_LOW_PROFILE


def test_an_unmapped_roof_profile_is_left_unset_rather_than_guessed() -> None:
    # No Bailey motorhome range other than "Low Profile" has been seen; anything else
    # (an A-class or over-cab range, if one appears) must not be silently mapped.
    product = _product(roof_profile_published="A Class")
    assert product.body_type is None


def test_campervan_body_type_comes_from_height_not_the_roof_code() -> None:
    # "H3" is a van body-height code, not something this adapter interprets directly —
    # the existing height-threshold rule decides it instead.
    tall = _product(is_campervan=True, mh_height_mm=2824, roof_profile_published="H3")
    assert tall.body_type == BodyType.CAMPERVAN_HIGH_TOP

    short = replace(tall, mh_height_mm=2000)
    assert short.body_type == BodyType.CAMPERVAN


def test_campervan_body_type_is_unset_without_a_height() -> None:
    product = _product(is_campervan=True, mh_height_mm=None)
    assert product.body_type is None


# --------------------------------------------------------------------------- #
# Payload self-check
# --------------------------------------------------------------------------- #


def test_published_payload_matching_the_two_masses_reconciles() -> None:
    product = _product(mtplm_kilograms=3500, mro_kilograms=2827, mh_payload_kilograms_published=673)
    assert _reconciles(product) is True


def test_published_payload_contradicting_the_two_masses_does_not_reconcile() -> None:
    product = _product(mtplm_kilograms=3500, mro_kilograms=2827, mh_payload_kilograms_published=999)
    assert _reconciles(product) is False


def test_a_1kg_rounding_difference_still_reconciles() -> None:
    # Two independently-rounded decimal figures can land 1kg apart even when the
    # underlying figures are exactly consistent (4500 - 3431.5 = 1068.5, which rounds
    # to 3432 and 1068 respectively — see the Autograph IV 79-4F fixture test).
    product = _product(mtplm_kilograms=4500, mro_kilograms=3432, mh_payload_kilograms_published=1068)
    assert _reconciles(product) is True


def test_a_missing_mass_is_not_treated_as_contradictory() -> None:
    product = _product(mtplm_kilograms=3500, mro_kilograms=None, mh_payload_kilograms_published=None)
    assert _reconciles(product) is True


def test_payload_falls_back_to_derivation_when_not_published() -> None:
    product = _product(mtplm_kilograms=3500, mro_kilograms=2827, mh_payload_kilograms_published=None)
    assert product.mh_payload_kilograms == 673
