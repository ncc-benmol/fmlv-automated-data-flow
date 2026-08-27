"""Tests for the Moto-Trek adapter's pure parsing functions, against real captured pages.

The fixtures are (trimmed) real pages fetched 27 August 2026 — see
`docs/adapters/moto-trek.md`. Trimming removes only `<head>`, `<style>`, `<script>`,
comments and lazy-load data URIs; the `<div>` nesting is left completely intact, because
`_panel_span` walks it to find the spec block. Every fixture was verified to parse
identically to the untrimmed page before being saved. No network here.

The pages chosen are the ones that broke the parser while it was being written:

* **pioneer** — carries neither always-empty label, because it publishes no width or
  height. An earlier version of the adapter required the surplus to *equal*
  `_ALWAYS_EMPTY_LABELS` and silently dropped it. Also the only `4/6` berths figure.
* **leisure_treka_eld** — `Garage Length = 3160kg`, a real data-entry error on Moto-Trek's
  site, plus the `M.I.R.O`/`M.T.P.L.M` vocabulary only this model uses, plus the loosest
  imperial rounding on the site.
* **leisure_treka_eb** — the ordinary shape, and the `2.17m ‘ 7’1″` cell whose separator is
  a stray left single quote instead of a slash.
* **x_cite_eb_elite** — `POA`, and a page title carrying a trim ("Elite") that FMLV drops.
* **tornado_transporter** — no "Cab and Body" block at all, so no base vehicle.
* **ford_custom_campervan** — a "Vehicle Specification" heading with no two-column block
  behind it.
* **motorhomes_index** — the navigation roster and the cards that cross-check it.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from src.adapters.moto_trek import (
    _ALWAYS_EMPTY_LABELS,
    HIGH_TOP_ABOVE_MM,
    IGNORED_SLUGS,
    LAST_PUBLISHED_PRICES,
    VEHICLE_IDENTITIES,
    DEFAULT_RANGES,
    IndexCard,
    MotoTrekProduct,
    _base_vehicle,
    _build_extracted_motorhome,
    _headline_price,
    _imperial_disagreements,
    _imperial_inches,
    _kilograms,
    _lower_int,
    _metres_to_mm,
    _panel_span,
    _reconciles,
    _value_kind,
    card_disagreements,
    find_roster,
    parse_index_cards,
    parse_spec_block,
    parse_vehicle_page,
    surplus_is_expected,
)
from src.product_model.enums import BodyType
from src.product_model.schema import IN_SCOPE, REQUIRED

FIXTURES = Path(__file__).parent / "fixtures"


def _page(name: str) -> str:
    return (FIXTURES / f"moto_trek_{name}.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Low-level value reading
# --------------------------------------------------------------------------- #


def test_metres_to_mm_reads_the_metric_half_only() -> None:
    assert _metres_to_mm("6.36m / 20’10”") == 6360


def test_metres_to_mm_handles_a_single_decimal_and_none_at_all() -> None:
    # "8.7m" on the Euro-Treka, "2m" on the Xplora living area.
    assert _metres_to_mm("8.7m") == 8700
    assert _metres_to_mm("2m") == 2000
    assert _metres_to_mm("0.7m") == 700


def test_metres_to_mm_ignores_a_value_that_is_not_a_length() -> None:
    # The Leisure-Treka ELD's Garage Length really does hold "3160kg".
    assert _metres_to_mm("3160kg") is None


def test_kilograms_strips_the_unit() -> None:
    assert _kilograms("3500kg") == 3500


def test_lower_int_takes_the_lower_figure_of_a_berths_range() -> None:
    # The Pioneer publishes "4/6"; the base vehicle sleeps 4, and FMLV holds 4.
    assert _lower_int("4/6") == 4
    assert _lower_int("2") == 2


def test_value_kind_types_each_shape_of_cell() -> None:
    assert _value_kind("3500kg") == "kg"
    assert _value_kind("6.36m / 20’10”") == "metres"
    assert _value_kind("2m") == "metres"
    assert _value_kind("70L") == "litres"
    assert _value_kind("2.0L 140BHP") == "engine"
    assert _value_kind("4/6") == "int"
    assert _value_kind("2") == "int"


def test_value_kind_does_not_mistake_a_weight_for_a_length() -> None:
    # The whole ELD defence rests on this distinction.
    assert _value_kind("3160kg") != "metres"


# --------------------------------------------------------------------------- #
# The metric/imperial cross-check
# --------------------------------------------------------------------------- #


def test_imperial_inches_reads_curly_feet_and_inches() -> None:
    assert _imperial_inches("6.36m / 20’10”") == 250


def test_imperial_inches_survives_the_stray_quote_separator() -> None:
    # Four pages print Living Area Height as "2.17m ‘ 7’1″" — a left single quote where
    # every other cell has a slash. The metric half is anchored at the start of the
    # string precisely so this does not need a second pattern.
    assert _imperial_inches("2.17m ‘ 7’1″") == 85
    assert _metres_to_mm("2.17m ‘ 7’1″") == 2170


def test_imperial_inches_is_none_where_only_metric_is_published() -> None:
    assert _imperial_inches("2.05m") is None


def test_imperial_disagreements_tolerates_moto_treks_own_loose_rounding() -> None:
    # Real cells from the ELD: 6.36m is 20'10.4" but is printed 20'9", and 2.64m is
    # 8'7.9" but is printed 8'6". Both are wrong and neither is worth a warning.
    assert _imperial_disagreements((("Overall Length", "6.36m / 20’9″"),)) == []
    assert _imperial_disagreements((("Overall Height*", "2.64m / 8’6″"),)) == []


def test_imperial_disagreements_still_fires_on_a_real_disagreement() -> None:
    # A check that can never fire is worth nothing, so prove this one can.
    assert _imperial_disagreements((("Overall Length", "6.36m / 18’0″"),)) != []


# --------------------------------------------------------------------------- #
# Price
# --------------------------------------------------------------------------- #


def test_headline_price_reads_the_from_figure() -> None:
    html = '<h3 class="elementor-heading-title elementor-size-default">from £72495.00</h3>'
    assert _headline_price(html) == (72495, False)


def test_headline_price_reports_poa_rather_than_zero() -> None:
    html = '<h3 class="elementor-heading-title elementor-size-default">POA</h3>'
    assert _headline_price(html) == (None, True)


def test_headline_price_ignores_the_same_figure_in_the_body_prose() -> None:
    # The Leisure-Treka pages repeat the price in a paragraph, with a thousands comma:
    # "‘Classic’ Models Available from – £72,495.00". Reading prose instead of the
    # heading would work until a model whose prose is out of step with its headline.
    html = (
        "<p>‘Classic’ Models Available from – £99,999.00</p>"
        '<h3 class="elementor-heading-title elementor-size-default">from £72495.00</h3>'
    )
    assert _headline_price(html) == (72495, False)


# --------------------------------------------------------------------------- #
# The two-column spec block
# --------------------------------------------------------------------------- #


def test_panel_span_is_bounded_by_the_containers_own_closing_tag() -> None:
    # "Cab and Body" and "Optional Extras" are sibling accordion panels full of
    # text-editor widgets, and their headings are not named consistently across models
    # (`Cab and Body` vs `CAB & BODY`), so they cannot be used as an end marker.
    span = _panel_span(_page("leisure_treka_eb"))
    assert span is not None
    assert "Cab and Body" not in _page("leisure_treka_eb")[span[0] : span[1]]


def test_spec_block_pairs_the_two_columns_by_position() -> None:
    block = parse_spec_block(_page("leisure_treka_eb"))
    assert block is not None
    assert dict(block.pairs)["Overall Length"] == "6.36m / 20’10”"
    assert dict(block.pairs)["Unladen Weight"] == "2500kg"
    assert dict(block.pairs)["Gross Weight"] == "3500kg"


def test_spec_block_surplus_is_the_two_always_empty_labels() -> None:
    block = parse_spec_block(_page("leisure_treka_eb"))
    assert block is not None
    assert block.surplus == _ALWAYS_EMPTY_LABELS
    assert surplus_is_expected(block)


def test_pioneer_has_no_surplus_at_all_and_is_still_collected() -> None:
    # The regression this adapter shipped with once: requiring the surplus to *equal*
    # `_ALWAYS_EMPTY_LABELS` dropped the Pioneer, which carries neither label because it
    # publishes no width or height for DCE to hang them on.
    block = parse_spec_block(_page("pioneer"))
    assert block is not None
    assert block.surplus == ()
    assert surplus_is_expected(block)

    product, _ = parse_vehicle_page(_page("pioneer"), "pioneer")
    assert product is not None
    assert (product.manufacturer_range, product.model) == ("Pioneer", "IB")
    assert product.mh_length_mm == 8350
    assert product.mh_width_mm is None
    assert product.mh_height_mm is None


def test_surplus_is_expected_rejects_a_data_bearing_label_running_past_the_values() -> None:
    block = parse_spec_block(_page("leisure_treka_eb"))
    assert block is not None
    shifted = replace(block, surplus=("Gross Weight", *_ALWAYS_EMPTY_LABELS))
    assert not surplus_is_expected(shifted)


def test_a_page_whose_columns_have_shifted_is_dropped_not_guessed_at() -> None:
    # Emptying one value widget in the middle of the value column is what DCE hiding a
    # value *without* also hiding its label would look like. The label column then runs
    # one entry further than it should, `Gross Weight` lands in the surplus, and nothing
    # on the page can be trusted — so no product may be emitted.
    #
    # The markup is asserted rather than assumed: an earlier version of this test used a
    # `<p>2500kg</p>` that does not exist in the page, so the replace was a no-op and the
    # test was really just re-checking the happy path.
    page = _page("leisure_treka_eb")
    widget = re.compile(r'(<div class="elementor-widget-container">\s*)2500kg(</div>)')
    assert len(widget.findall(page)) == 1
    html = widget.sub(r"\1\2", page, count=1)

    block = parse_spec_block(html)
    assert block is not None
    assert "Gross Weight" in block.surplus
    assert not surplus_is_expected(block)

    product, returned = parse_vehicle_page(html, "leisure-treka-eb")
    assert product is None
    assert returned is not None


# --------------------------------------------------------------------------- #
# The Leisure-Treka ELD: a real error on Moto-Trek's own site
# --------------------------------------------------------------------------- #


def test_eld_garage_length_holds_a_weight_and_is_reported_as_a_mismatch() -> None:
    block = parse_spec_block(_page("leisure_treka_eld"))
    assert block is not None
    assert block.mismatches == (("Garage Length", "3160kg", "metres"),)


def test_eld_keeps_every_in_scope_figure_despite_that_mismatch() -> None:
    # One mismatch on an out-of-scope field is a typo, not a column shift: the payload
    # identity 3500 - 3160 = 340 holds exactly as printed, and any one-place shift of the
    # value column would break it.
    product, _ = parse_vehicle_page(_page("leisure_treka_eld"), "leisure-treka-eld")
    assert product is not None
    assert product.mro_kilograms == 3160
    assert product.mtplm_kilograms == 3500
    assert product.mh_payload_kilograms_published == 340
    assert (product.mh_length_mm, product.mh_width_mm, product.mh_height_mm) == (
        6360,
        2260,
        2640,
    )
    assert _reconciles(product)[0]


def test_eld_publishes_the_mass_labels_nothing_else_on_the_site_uses() -> None:
    block = parse_spec_block(_page("leisure_treka_eld"))
    assert block is not None
    labels = dict(block.pairs)
    assert "M.I.R.O" in labels
    assert "M.T.P.L.M" in labels
    assert "Unladen Weight" not in labels
    assert "Gross Weight" not in labels


# --------------------------------------------------------------------------- #
# The pages that yield nothing
# --------------------------------------------------------------------------- #


def test_ford_custom_campervan_has_a_heading_but_no_two_column_block() -> None:
    assert "Vehicle Specification" in _page("ford_custom_campervan")
    assert parse_spec_block(_page("ford_custom_campervan")) is None


def test_an_unknown_slug_yields_nothing_rather_than_a_guessed_identity() -> None:
    product, block = parse_vehicle_page(_page("leisure_treka_eb"), "some-new-vehicle")
    assert product is None
    assert block is None


# --------------------------------------------------------------------------- #
# Base vehicle and price on real pages
# --------------------------------------------------------------------------- #


def test_base_vehicle_reads_the_make_from_the_cab_and_body_block() -> None:
    assert _base_vehicle(_page("leisure_treka_eb")) == "Peugeot"


def test_base_vehicle_is_none_where_the_page_has_no_cab_block() -> None:
    # True of the Tornado and the Pioneer. Out of collection scope, so a matched product
    # keeps whatever FMLV holds.
    assert _base_vehicle(_page("tornado_transporter")) is None


def test_x_cite_is_poa_so_no_price_is_proposed() -> None:
    product, _ = parse_vehicle_page(_page("x_cite_eb_elite"), "x-cite-eb-elite")
    assert product is not None
    assert product.is_poa is True
    assert product.rrp_pounds is None


def test_x_cite_loses_its_elite_trim_to_match_the_export() -> None:
    product, _ = parse_vehicle_page(_page("x_cite_eb_elite"), "x-cite-eb-elite")
    assert product is not None
    assert (product.manufacturer_range, product.model) == ("X-Cite", "EB")


# --------------------------------------------------------------------------- #
# Weights: reconciliation and the derived payload
# --------------------------------------------------------------------------- #


def test_payload_is_derived_where_moto_trek_publish_none() -> None:
    # Only the ELD publishes a payload. Leaving it alone would keep the Leisure-Treka
    # EB's inherited 340kg beside a 1000kg gap — arithmetically impossible.
    product, _ = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    assert product.mh_payload_kilograms_published is None
    assert product.mh_payload_kilograms == 1000


def test_reconciles_rejects_a_published_payload_that_does_not_add_up() -> None:
    product, _ = parse_vehicle_page(_page("leisure_treka_eld"), "leisure-treka-eld")
    assert product is not None
    broken = replace(product, mh_payload_kilograms_published=500)
    assert not _reconciles(broken)[0]


def test_reconciles_rejects_a_mass_in_running_order_above_the_mtplm() -> None:
    # The type check cannot see a swap of these two, because both are kg.
    product, _ = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    swapped = replace(product, mro_kilograms=3500, mtplm_kilograms=2500)
    assert not _reconciles(swapped)[0]


def test_reconciles_passes_a_product_missing_the_figures_entirely() -> None:
    product, _ = parse_vehicle_page(_page("pioneer"), "pioneer")
    assert product is not None
    assert _reconciles(replace(product, mro_kilograms=None))[0]


# --------------------------------------------------------------------------- #
# Body type — out of scope, and the height threshold is gated on shape
# --------------------------------------------------------------------------- #


def test_a_van_conversion_above_the_threshold_is_a_high_top() -> None:
    product, _ = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    assert product.is_campervan
    assert product.mh_height_mm is not None
    assert product.mh_height_mm > HIGH_TOP_ABOVE_MM
    assert product.body_type is BodyType.CAMPERVAN_HIGH_TOP


def test_the_height_threshold_never_promotes_a_coachbuilt() -> None:
    # The X-Cite is 2870mm, well above the threshold, and is simply a low-profile
    # motorhome — the threshold only ever separates campervan from campervan_high_top
    # (requester, 27 August 2026). FMLV's coach_built_low_profile is right and untouched.
    product, _ = parse_vehicle_page(_page("x_cite_eb_elite"), "x-cite-eb-elite")
    assert product is not None
    assert not product.is_campervan
    assert product.mh_height_mm is not None
    assert product.mh_height_mm > HIGH_TOP_ABOVE_MM
    assert product.body_type is None


def test_a_campervan_with_no_height_claims_no_body_type() -> None:
    product, _ = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    assert replace(product, mh_height_mm=None).body_type is None


# --------------------------------------------------------------------------- #
# The roster and its cross-check
# --------------------------------------------------------------------------- #


def test_find_roster_lists_all_thirteen_vehicles_from_the_navigation() -> None:
    # `/motorhomes/` shows only the 11 leisure vehicles; the nav is the one source that
    # also carries the Tornado and the Cyclone, under Motorsport and Trailers.
    roster = find_roster(_page("motorhomes_index"))
    assert len(roster) == 13
    assert set(VEHICLE_IDENTITIES) <= set(roster)
    assert set(IGNORED_SLUGS) <= set(roster)


def test_the_roster_is_exactly_what_is_collected_plus_what_is_ignored() -> None:
    # If this fails, Moto-Trek have added or renamed a vehicle and the identity table
    # needs a look — which `collect` also narrates at run time.
    roster = find_roster(_page("motorhomes_index"))
    assert set(roster) == set(VEHICLE_IDENTITIES) | set(IGNORED_SLUGS)


def test_eleven_products_are_collected() -> None:
    # Moto-Trek's own `/motorhomes/` index claims 11 leisure vehicles; ten of them are
    # current in FMLV and the Euro-Treka IB is new.
    assert len(VEHICLE_IDENTITIES) == 11


def test_index_cards_republish_berths_gross_weight_and_price() -> None:
    cards = parse_index_cards(_page("motorhomes_index"))
    assert cards["leisure-treka-eb"] == IndexCard(
        slug="leisure-treka-eb", berths=2, mtplm_kilograms=3500, rrp_pounds=72495
    )
    # The Pioneer card is the one that proves the icons, not position, identify the two
    # figures: "4/6" berths beside 7500kg.
    assert cards["pioneer"] == IndexCard(
        slug="pioneer", berths=4, mtplm_kilograms=7500, rrp_pounds=199995
    )


def test_every_card_agrees_with_its_own_vehicle_page() -> None:
    cards = parse_index_cards(_page("motorhomes_index"))
    for name, slug in (
        ("leisure_treka_eb", "leisure-treka-eb"),
        ("leisure_treka_eld", "leisure-treka-eld"),
        ("pioneer", "pioneer"),
        ("x_cite_eb_elite", "x-cite-eb-elite"),
    ):
        product, _ = parse_vehicle_page(_page(name), slug)
        assert product is not None
        assert card_disagreements(product, cards[slug]) == []


def test_card_disagreements_reports_a_genuine_mismatch() -> None:
    product, _ = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    card = IndexCard(slug="leisure-treka-eb", berths=4, mtplm_kilograms=3500, rrp_pounds=72495)
    assert card_disagreements(product, card) == ["berths (page 2, card 4)"]


def test_the_tornado_carries_the_leisure_treka_ebs_figures() -> None:
    # Recorded as a test because it is the reason `collect` narrates the Tornado: its
    # spec block is byte-identical to the EB's except for berths, so the one figure that
    # differs may be the placeholder rather than the correction.
    tornado, _ = parse_vehicle_page(_page("tornado_transporter"), "tornado-transporter")
    eb, _ = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert tornado is not None
    assert eb is not None
    shared = ("mh_length_mm", "mh_width_mm", "mh_height_mm", "mro_kilograms", "mtplm_kilograms")
    assert all(getattr(tornado, f) == getattr(eb, f) for f in shared)
    assert (tornado.berths, eb.berths) == (3, 2)


# --------------------------------------------------------------------------- #
# Identity, ranges and wiring
# --------------------------------------------------------------------------- #


def test_default_ranges_are_the_fmlv_range_names() -> None:
    # The labels have to be the real `manufacturer_range` values, because
    # `cli.baseline_scope` matches on that column and this adapter declares no
    # `baseline_in_scope` hook.
    assert {label for _slug, label in DEFAULT_RANGES} == {
        identity[0] for identity in VEHICLE_IDENTITIES.values()
    }


def test_default_range_labels_are_unique() -> None:
    # `cli.resolve_ranges` keys on a unique label; a duplicate would silently shadow.
    labels = [label for _slug, label in DEFAULT_RANGES]
    assert len(labels) == len(set(labels))


def test_the_terrain_and_tornado_repeat_the_range_in_the_model() -> None:
    # Deliberate, and it is what the export holds — see the module docstring.
    assert VEHICLE_IDENTITIES["the-terrain"][:2] == ("The Terrain", "The Terrain")
    assert VEHICLE_IDENTITIES["tornado-transporter"][:2] == ("Tornado", "Tornado")


def test_every_leisure_treka_is_a_van_conversion_including_the_eld() -> None:
    """The ELD's odd figures are measurement conventions, not a different vehicle.

    An earlier version of this table had the ELD as a coachbuilt, on the strength of it
    being 2.26m wide against its siblings' 2.05m, 2.64m tall against their 2.76m and
    3160kg against their 2500kg. Its own handbook dissolves all three: the width is
    quoted "with the mirrors folded" (210mm over the body, ~105mm per mirror), the height
    "with the TV aerial stowed", and its mass is an `M.I.R.O` — habitation equipment, gas,
    a full water tank and the hook-up cable included — against the siblings' dry
    `Unladen Weight`. All four are 6.36m on the same Boxer.

    So FMLV's `campervan_high_top` was right and the proposed correction was not.
    """
    for slug in ("leisure-treka-rl", "leisure-treka-eb", "leisure-treka-eld"):
        assert VEHICLE_IDENTITIES[slug][2] is True, slug


def test_the_eld_is_a_high_top_like_its_siblings() -> None:
    product, _ = parse_vehicle_page(_page("leisure_treka_eld"), "leisure-treka-eld")
    assert product is not None
    assert product.mh_height_mm == 2640
    assert product.body_type is BodyType.CAMPERVAN_HIGH_TOP


# --------------------------------------------------------------------------- #
# What reaches the reviewer
# --------------------------------------------------------------------------- #


def test_provenance_covers_every_in_scope_field_that_was_found() -> None:
    product, block = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)

    for field in (
        "manufacturer_range",
        "model",
        "berths",
        "rrp_pounds",
        "mro_kilograms",
        "mtplm_kilograms",
        "mh_payload_kilograms",
        "mh_length_mm",
        "mh_width_mm",
        "mh_height_mm",
    ):
        assert field in extracted.provenance, field
        assert field in IN_SCOPE, field


def test_seats_are_never_claimed_because_moto_trek_publish_none() -> None:
    product, block = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert extracted.motorhome.mh_passenger_seats_inc_driver is None
    assert "mh_passenger_seats_inc_driver" not in extracted.provenance
    # It is required on upload, so a new product will be flagged rather than silently
    # blank — which is the intended outcome, not a gap in this adapter.
    assert "mh_passenger_seats_inc_driver" in REQUIRED


def test_price_provenance_names_the_basis() -> None:
    # A manufacturer changing basis between runs would show every product moving price
    # without a price change, so the snippet has to say which basis was recorded.
    product, block = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert "Ex works" in extracted.provenance["rrp_pounds"].snippet


def test_derived_payload_says_so_in_its_provenance() -> None:
    product, block = parse_vehicle_page(_page("leisure_treka_eb"), "leisure-treka-eb")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert "derived" in extracted.provenance["mh_payload_kilograms"].snippet


def test_the_two_identity_halves_are_recorded_together() -> None:
    # Proposing one without the other corrupts the name — Bailey's "Adamo I" failure.
    product, block = parse_vehicle_page(_page("x_cite_eb_elite"), "x-cite-eb-elite")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert "Paired with the model below" in extracted.provenance["manufacturer_range"].snippet
    assert "Paired with the range above" in extracted.provenance["model"].snippet


def test_the_provenance_snippet_quotes_the_label_the_page_actually_used() -> None:
    # The vocabulary differs per model, so a snippet naming "Unladen Weight" on the ELD
    # would send a reviewer looking for a row that page does not have.
    product, block = parse_vehicle_page(_page("leisure_treka_eld"), "leisure-treka-eld")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert "M.I.R.O" in extracted.provenance["mro_kilograms"].snippet
    assert "M.T.P.L.M" in extracted.provenance["mtplm_kilograms"].snippet


def test_berths_provenance_shows_the_raw_range_it_narrowed() -> None:
    product, block = parse_vehicle_page(_page("pioneer"), "pioneer")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert extracted.motorhome.berths == 4
    assert "4/6" in extracted.provenance["berths"].snippet


def test_a_poa_product_records_no_price_provenance() -> None:
    product, block = parse_vehicle_page(_page("x_cite_eb_elite"), "x-cite-eb-elite")
    assert product is not None
    assert block is not None
    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert extracted.motorhome.rrp_pounds is None
    assert "rrp_pounds" not in extracted.provenance


def test_the_manufacturer_string_matches_the_registry_row() -> None:
    from src.adapters import adapter_for, moto_trek

    assert moto_trek.MANUFACTURER == "MOTO-TREK LIMITED"
    assert adapter_for("MOTO-TREK LIMITED") is moto_trek

# --------------------------------------------------------------------------- #
# The last published price: narrated, never asserted
# --------------------------------------------------------------------------- #


def test_last_published_prices_covers_exactly_the_poa_vehicles() -> None:
    # The four the site marks POA. If Moto-Trek start quoting one again, the run will
    # read the headline instead and this entry simply stops being reached.
    assert set(LAST_PUBLISHED_PRICES) == {
        "euro-treka-ib",
        "x-cite-eb-elite",
        "x-cite-g-elite",
        "tornado-transporter",
    }


def test_last_published_prices_carry_a_date() -> None:
    # The date is the point: a bare figure invites being read as current.
    for amount, published in LAST_PUBLISHED_PRICES.values():
        assert amount > 0
        assert published == "January 2024"


def test_the_euro_treka_figure_is_the_one_from_their_own_price_list() -> None:
    # £152,995 is the January 2024 list's "2024 Retail Price" column — net plus VAT, the
    # basis FMLV holds. Not the October guide's £153,215, which is on-the-road.
    assert LAST_PUBLISHED_PRICES["euro-treka-ib"] == (152_995, "January 2024")


def test_a_last_published_price_is_never_written_to_the_product() -> None:
    # The whole point of the table is that it informs a reviewer without the run
    # asserting a withdrawn figure as collected.
    product, block = parse_vehicle_page(_page("x_cite_eb_elite"), "x-cite-eb-elite")
    assert product is not None
    assert block is not None
    assert "x-cite-eb-elite" in LAST_PUBLISHED_PRICES
    assert product.rrp_pounds is None
    assert product.is_poa is True

    extracted = _build_extracted_motorhome(product, "https://moto-trek.co.uk/x/", block)
    assert extracted.motorhome.rrp_pounds is None
    assert "rrp_pounds" not in extracted.provenance
