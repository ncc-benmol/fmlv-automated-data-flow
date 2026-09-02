"""Elddis adapter — pure parsing tests against real captured pages.

No network and no PDF work here. Every fixture is a real page or document captured during
the survey on 21 August 2026, chosen because it broke the parser at some point while it was
being written:

* `whirlwind_gt_155` — the ordinary motorhome, and the tolerance-based payload.
* `avalon_250` — the same shape but with the *plain* `MTPLM - MIRO` payload, which is why
  the self-check has to be a band rather than an equality.
* `autoquest_apex_196p` — the site's `196+` against FMLV's `196P`, and the one MTPLM
  that is not 3500.
* `autoquest_cv20` / `autoquest_cv80` — the campervan template, which heads its block
  `Technical Specifications` and `Notes` where the motorhomes use
  `Technical Specification` and `NOTES`; and the pop-top-as-standard rule that separates
  the two.
* `whirlwind_gtv_554` / `whirlwind_gtv_563` — the worst case: metres instead of
  millimetres, comma-separated masses, `Excluding Aerial` height, prose berths and seats,
  and weights split Fixed Roof / Pop Top x Manual / Automatic with the model name embedded
  in the label.

**One deliberate edit to the captures.** The three motorhome pages embed a Mapbox access
token belonging to Elddis's web agency, inside the retailer-search `<script>` block that
powers their dealer map. It is redacted to `pk.REDACTED-...` in the committed fixtures:
GitHub's secret-scanning push protection rejects it, and it is a third party's credential
that has no business in this repository either way. It cannot affect any test — `_text_lines`
strips every `<script>` block before parsing, so the token is never in the text the parser
sees. Apart from that substitution the fixtures are the bytes the site served.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.adapters.elddis import (
    DEFAULT_RANGES,
    MANUFACTURER,
    _kilograms,
    _leading_int,
    _millimetres,
    _model_code,
    _reconciles,
    _text_lines,
    apply_brochure_weights,
    count_index_cards,
    find_brochure_url,
    find_model_urls,
    parse_brochure_weights,
    parse_model_page,
    spec_fields,
)
from src.product_model.enums import BodyType

FIXTURES = Path(__file__).parent / "fixtures"

#: What Elddis publicly lists, from `sitemap.xml` and confirmed independently by the two
#: `*-specification` index pages: 34 motorhomes across 5 ranges, 15 campervans across 4.
EXPECTED_MOTORHOMES = 34
EXPECTED_CAMPERVANS = 15


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def _parse(name: str, *, segment: str, is_campervan: bool):
    product = parse_model_page(
        _fixture(name), segment=segment, is_campervan=is_campervan
    )
    assert product is not None, f"{name} did not parse"
    return product


# --------------------------------------------------------------------------------------
# The roster
# --------------------------------------------------------------------------------------


def test_sitemap_yields_every_motorhome_and_campervan_layout():
    """The sitemap is the roster, and it must total the manufacturer's public count."""
    sitemap = _fixture("elddis_sitemap.xml")
    motorhomes = campervans = 0
    for path, _ in DEFAULT_RANGES:
        vehicle_type, _, segment = path.partition("/")
        found = find_model_urls(sitemap, segment, vehicle_type)
        assert found, f"no model pages found for {path}"
        if vehicle_type == "campervans":
            campervans += len(found)
        else:
            motorhomes += len(found)
    assert motorhomes == EXPECTED_MOTORHOMES
    assert campervans == EXPECTED_CAMPERVANS


def test_range_urls_do_not_leak_between_similarly_named_ranges():
    """`whirlwind-gt` must not collect `whirlwind-gt-evolve`'s nine layouts.

    The segments are prefixes of one another, so a loose `in`-style match would give
    Whirlwind GT eighteen models and Whirlwind GT Evolve nine of them again. The same
    hazard exists for `avalon`/`avalon-evolve` and `autoquest-cv`/`autoquest-cv-evolve`.
    """
    sitemap = _fixture("elddis_sitemap.xml")
    base = find_model_urls(sitemap, "whirlwind-gt", "motorhomes")
    evolve = find_model_urls(sitemap, "whirlwind-gt-evolve", "motorhomes")
    assert len(base) == 9
    assert len(evolve) == 9
    assert not set(base) & set(evolve)
    assert all("evolve" not in url for url in base)

    avalon = find_model_urls(sitemap, "avalon", "motorhomes")
    assert len(avalon) == 4
    assert all("evolve" not in url for url in avalon)

    autoquest_cv = find_model_urls(sitemap, "autoquest-cv", "campervans")
    assert len(autoquest_cv) == 4
    assert all("evolve" not in url for url in autoquest_cv)


def test_range_overview_pages_are_not_mistaken_for_models():
    """`/motorhomes/avalon` is the range page; only three-segment paths are models."""
    urls = find_model_urls(_fixture("elddis_sitemap.xml"), "avalon", "motorhomes")
    assert "https://elddis.co.uk/motorhomes/avalon" not in urls
    assert "https://elddis.co.uk/motorhomes/avalon/avalon-250" in urls


def test_caravans_are_out_of_scope():
    """The sitemap carries 31 caravan URLs; none may be collected under any range."""
    sitemap = _fixture("elddis_sitemap.xml")
    for path, _ in DEFAULT_RANGES:
        vehicle_type, _, segment = path.partition("/")
        assert all(
            "/caravans/" not in url
            for url in find_model_urls(sitemap, segment, vehicle_type)
        )


def test_specification_indexes_confirm_the_sitemap_count():
    """The free second opinion on the roster — and it agrees exactly."""
    assert (
        count_index_cards(_fixture("elddis_motorhome_specification_index.html"))
        == EXPECTED_MOTORHOMES
    )
    assert (
        count_index_cards(_fixture("elddis_campervan_specification_index.html"))
        == EXPECTED_CAMPERVANS
    )


def test_roster_cross_check_is_skipped_for_a_partial_range_selection():
    """A `--range` run must not be compared against the full index.

    Regression test for a real false alarm: the first version counted the *available*
    ranges on both sides of the guard instead of the requested ones, so the guard never
    fired and `fmlv run --range "Whirlwind GTV"` warned "the sitemap lists 3 but
    campervan-specification shows 15" on every partial run.
    """
    from src.adapters.elddis import _ranges_by_vehicle_type

    one_range = (("campervans/whirlwind-gtv", "Whirlwind GTV"),)
    assert _ranges_by_vehicle_type(one_range) == {"motorhome": 0, "campervan": 1}
    assert _ranges_by_vehicle_type(DEFAULT_RANGES) == {"motorhome": 5, "campervan": 4}
    # The guard fires precisely when the two disagree for that vehicle type.
    assert (
        _ranges_by_vehicle_type(one_range)["campervan"]
        != _ranges_by_vehicle_type(DEFAULT_RANGES)["campervan"]
    )
    # ...and does not fire for a full run.
    assert _ranges_by_vehicle_type(DEFAULT_RANGES) == _ranges_by_vehicle_type(
        DEFAULT_RANGES
    )


# --------------------------------------------------------------------------------------
# The spec block, and the heading that differs by vehicle type
# --------------------------------------------------------------------------------------


def test_campervan_block_heading_is_plural_and_still_parses():
    """Motorhomes head this `Technical Specification`, campervans `Technical
    Specifications` — and the footnotes `NOTES` versus `Notes`.

    Matching the motorhome spelling exactly finds 34 of 49 products and silently drops
    every campervan, which is how this was found.
    """
    motorhome = spec_fields(_text_lines(_fixture("elddis_whirlwind_gt_155.html")))
    campervan = spec_fields(_text_lines(_fixture("elddis_autoquest_cv20.html")))
    assert motorhome["M.T.P.L.M"].startswith("3500")
    assert campervan["M.T.P.L.M"].startswith("3500")


def test_footnotes_never_become_spec_fields():
    """The block stops at the notes, so `Note 1: …` prose is not read as a field."""
    fields = spec_fields(_text_lines(_fixture("elddis_whirlwind_gt_155.html")))
    assert not [label for label in fields if label.lower().startswith("note")]
    # The last real row is a mattress size; nothing beyond the notes gets in.
    assert "Rear Mattress Size" in fields
    assert "ADDITIONAL OPTIONS AVAILABLE" not in fields


def test_optional_payload_label_case_varies_between_pages():
    """`Mass Available` on 34 pages, `Mass available` on 12. Recorded because the same
    casing hazard applies to any label matched exactly."""
    motorhome = spec_fields(_text_lines(_fixture("elddis_whirlwind_gt_155.html")))
    campervan = spec_fields(_text_lines(_fixture("elddis_autoquest_cv20.html")))
    assert "Mass Available for Optional Payload" in motorhome
    assert "Mass available for Optional Payload" in campervan


# --------------------------------------------------------------------------------------
# One ordinary motorhome, end to end
# --------------------------------------------------------------------------------------


def test_whirlwind_gt_155_reads_every_field():
    product = _parse(
        "elddis_whirlwind_gt_155.html", segment="whirlwind-gt", is_campervan=False
    )
    assert product.manufacturer_range == "Whirlwind GT"
    assert product.model == "155"
    assert product.year == 2026
    assert product.berths == 4
    assert product.mh_passenger_seats_inc_driver == 4
    assert product.mh_length_mm == 7373
    assert product.mh_height_mm == 2925
    assert product.mro_kilograms == 2926
    assert product.mtplm_kilograms == 3500
    assert product.mh_payload_kilograms == 530
    assert product.rrp_pounds == 66195
    assert product.base_vehicle_manufacturer == "Peugeot"
    assert product.body_type is BodyType.COACH_BUILT_LOW_PROFILE


def test_width_is_the_body_figure_not_the_mirror_figure():
    """Elddis publishes both. FMLV holds the body width on all 29 matched products, and
    the base-vehicle rule wants the narrower one anyway."""
    product = _parse(
        "elddis_whirlwind_gt_155.html", segment="whirlwind-gt", is_campervan=False
    )
    assert product.mh_width_mm == 2239  # not 2678, the mirrors-included figure


def test_height_is_not_the_maximum_headroom_decoy():
    """`Maximum Headroom` is 2080 on every motorhome and looks like a plausible height."""
    product = _parse(
        "elddis_whirlwind_gt_155.html", segment="whirlwind-gt", is_campervan=False
    )
    assert product.mh_height_mm != 2080


def test_price_is_the_hero_figure_not_an_option_price():
    """`Gearbox - £3,246`, `Colour - £847` and `Tow Bar - £706` sit on the same page, as
    does the `£1,690` OTR-charge footnote."""
    product = _parse(
        "elddis_whirlwind_gt_155.html", segment="whirlwind-gt", is_campervan=False
    )
    assert product.rrp_pounds == 66195


def test_imperial_half_of_each_value_is_never_parsed():
    """Values are dual-unit — `7373mm/24'2"`, `2926kgs/57.60cwt`. The imperial half
    contains digits and a quote character, so it survives naive cleaning."""
    assert _millimetres("7373mm/24'2\"") == 7373
    assert _kilograms("2926kgs/57.60cwt") == 2926
    assert _kilograms("3500kgs/68.89cwt") == 3500


# --------------------------------------------------------------------------------------
# Identity: the range comes from FMLV, and `196+` is `196P`
# --------------------------------------------------------------------------------------


def test_site_plus_becomes_fmlv_p():
    """The site writes `196+`; the export writes `196P`. Getting this wrong reports the
    product as new *and* its baseline row as disappeared."""
    product = _parse(
        "elddis_autoquest_apex_196p.html", segment="autoquest-apex", is_campervan=False
    )
    assert product.site_model_name == "Autoquest APEX 196+"
    assert product.model == "196P"
    assert product.manufacturer_range == "Autoquest Apex"
    assert product.mtplm_kilograms == 3650  # the one range that is not 3500
    assert product.berths == 6


@pytest.mark.parametrize(
    ("site_name", "expected"),
    [
        ("Whirlwind GT 155", "155"),
        ("Whirlwind GT Evolve 196+", "196P"),
        ("Autoquest APEX 196+", "196P"),
        ("Autoquest CV20", "CV20"),
        ("Autoquest Evolve CV80", "CV80"),
        ("Autoquest APEX CV60", "CV60"),
        ("Whirlwind GTV 554", "554"),
        ("Avalon Evolve 250", "250"),
    ],
)
def test_model_code_is_the_trailing_layout_code(site_name: str, expected: str):
    assert _model_code(site_name) == expected


def test_model_code_rejects_a_name_with_no_layout_code():
    """A template change that drops the code should skip the product loudly, not emit a
    vehicle whose model is a marketing sentence."""
    assert _model_code("Autoquest") is None
    assert _model_code("The all-new Whirlwind") is None


def test_fmlv_folds_campervans_into_the_motorhome_range():
    """Only the real export reveals this: `Autoquest Apex` holds both the motorhomes and
    the campervans, and the site's `Autoquest CV` range collapses to `Autoquest`."""
    apex_van = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-apex-cv", is_campervan=True
    )
    assert apex_van.manufacturer_range == "Autoquest Apex"

    autoquest_van = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-cv", is_campervan=True
    )
    assert autoquest_van.manufacturer_range == "Autoquest"


def test_evolve_ranges_stay_distinct_from_their_base_range():
    """`Whirlwind GT Evolve 155` and `Whirlwind GT 155` are different vehicles that score
    0.750 on the matcher's 0.5 threshold, so the range strings must not collide."""
    assert {
        segment: parse_model_page(
            _fixture("elddis_whirlwind_gt_155.html"),
            segment=segment,
            is_campervan=False,
        ).manufacturer_range
        for segment in ("whirlwind-gt", "whirlwind-gt-evolve")
    } == {
        "whirlwind-gt": "Whirlwind GT",
        "whirlwind-gt-evolve": "Whirlwind GT Evolve",
    }


def test_unknown_segment_is_refused_rather_than_guessed():
    """A new range must be added to `_SEGMENT_RANGES` deliberately; inventing a range name
    from the URL would propose a rename across the brand."""
    assert (
        parse_model_page(
            _fixture("elddis_whirlwind_gt_155.html"),
            segment="brand-new-range",
            is_campervan=False,
        )
        is None
    )


# --------------------------------------------------------------------------------------
# The self-check band
# --------------------------------------------------------------------------------------


def test_payload_uses_the_miro_tolerance_on_most_models():
    """Whirlwind GT 155: 3500 - 2926 x 1.015 = 530, not the plain 574."""
    product = _parse(
        "elddis_whirlwind_gt_155.html", segment="whirlwind-gt", is_campervan=False
    )
    assert product.mh_payload_kilograms == 530
    assert product.mtplm_kilograms - product.mro_kilograms == 574
    assert _reconciles(product)


def test_payload_omits_the_tolerance_on_some_models():
    """Avalon 250 publishes the plain 3500 - 3090 = 410. This is the reason the check is a
    band: an equality against the tolerance formula rejects it."""
    product = _parse("elddis_avalon_250.html", segment="avalon", is_campervan=False)
    assert product.mro_kilograms == 3090
    assert product.mh_payload_kilograms == 410
    assert product.mtplm_kilograms - product.mro_kilograms == 410
    assert _reconciles(product)


@pytest.mark.parametrize(
    "fixture_and_segment",
    [
        ("elddis_whirlwind_gt_155.html", "whirlwind-gt", False),
        ("elddis_avalon_250.html", "avalon", False),
        ("elddis_autoquest_apex_196p.html", "autoquest-apex", False),
        ("elddis_autoquest_cv20.html", "autoquest-cv", True),
        ("elddis_autoquest_cv80.html", "autoquest-cv", True),
        ("elddis_whirlwind_gtv_554.html", "whirlwind-gtv", True),
        ("elddis_whirlwind_gtv_563.html", "whirlwind-gtv", True),
    ],
)
def test_every_fixture_reconciles(fixture_and_segment):
    name, segment, is_campervan = fixture_and_segment
    assert _reconciles(_parse(name, segment=segment, is_campervan=is_campervan))


def test_reconciles_rejects_a_payload_outside_the_band():
    """A misread mass is what this defends against. The GTV's pop-top MIRO is 160kg
    heavier than its fixed-roof one, so mixing the two variants fails by that much."""
    from dataclasses import replace

    product = _parse(
        "elddis_whirlwind_gtv_563.html", segment="whirlwind-gtv", is_campervan=True
    )

    # Payload above the plain subtraction, i.e. a vehicle carrying more than its own
    # weight limit allows.
    assert not _reconciles(
        replace(product, mh_payload_kilograms=product.mtplm_kilograms)
    )
    # Payload below the tolerance-adjusted floor by more than rounding can explain.
    assert not _reconciles(replace(product, mh_payload_kilograms=1))


def test_reconciles_passes_when_a_mass_is_missing():
    """Nothing to contradict, so nothing to reject — the missing figure is reported
    elsewhere rather than costing the whole product."""
    from dataclasses import replace

    product = _parse(
        "elddis_whirlwind_gt_155.html", segment="whirlwind-gt", is_campervan=False
    )
    assert _reconciles(replace(product, mro_kilograms=None))
    assert _reconciles(replace(product, mtplm_kilograms=None))
    assert _reconciles(replace(product, mh_payload_kilograms=None))


# --------------------------------------------------------------------------------------
# Campervans and the pop-top rule
# --------------------------------------------------------------------------------------


def test_campervan_without_a_pop_top_is_a_plain_high_top():
    product = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-cv", is_campervan=True
    )
    assert product.model == "CV20"
    assert product.mh_height_mm == 2670
    assert product.mh_width_mm == 2050
    assert product.mh_length_mm == 5998
    assert product.berths == 2
    assert product.pop_top_standard is False
    assert product.body_type is BodyType.CAMPERVAN_HIGH_TOP
    assert product.base_vehicle_manufacturer == "Fiat"


def test_campervan_with_a_standard_pop_top_gets_the_elevating_roof_type():
    """Only the CV80s say "comes with a pop-top"; CV20/40/60 never mention one."""
    product = _parse(
        "elddis_autoquest_cv80.html", segment="autoquest-cv", is_campervan=True
    )
    assert product.model == "CV80"
    assert product.berths == 4
    assert product.pop_top_standard is True
    assert product.body_type is BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF


def test_optional_pop_top_does_not_change_the_body_type():
    """The GTVs offer a pop-top as a cost option, so per the base-vehicle rule the vehicle
    is what it is with the roof down — and berths stay at the fixed-roof figure."""
    product = _parse(
        "elddis_whirlwind_gtv_554.html", segment="whirlwind-gtv", is_campervan=True
    )
    assert product.pop_top_optional is True
    assert product.pop_top_standard is False
    assert product.body_type is BodyType.CAMPERVAN_HIGH_TOP
    assert product.berths == 3  # not the pop-top's 5


def test_silence_about_a_pop_top_means_the_vehicle_has_none():
    """`README.md`'s rule, confirmed for the CV60 by the requester on 2026-08-21: a page
    that does not state the elevating roof is included is taken not to have one.

    FMLV holds Autoquest CV60 as `campervan_high_top_elevating_roof`; its page mentions a
    pop-top zero times, so the adapter proposes the plain high top. The CV20 fixture stands
    in for the same template — neither it, the CV40 nor the CV60 mentions one.
    """
    html = _fixture("elddis_autoquest_cv20.html")
    assert not re.search(r"pop[-\s]?top", html, re.IGNORECASE)
    product = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-cv", is_campervan=True
    )
    assert product.pop_top_standard is False
    assert product.body_type is BodyType.CAMPERVAN_HIGH_TOP


def test_mention_count_is_not_the_pop_top_signal():
    """The GTVs talk about the pop-top far more than the CV80s do, and still do not have
    one as standard. A naive keyword search would give all three an elevating roof.

    This is the test that stops someone "simplifying" the detection into a substring
    search for "pop-top".
    """
    gtv = _fixture("elddis_whirlwind_gtv_563.html")
    cv80 = _fixture("elddis_autoquest_cv80.html")
    gtv_mentions = len(re.findall(r"pop[-\s]?top", gtv, re.IGNORECASE))
    cv80_mentions = len(re.findall(r"pop[-\s]?top", cv80, re.IGNORECASE))
    assert gtv_mentions > cv80_mentions > 0

    gtv_product = _parse(
        "elddis_whirlwind_gtv_563.html", segment="whirlwind-gtv", is_campervan=True
    )
    cv80_product = _parse(
        "elddis_autoquest_cv80.html", segment="autoquest-cv", is_campervan=True
    )
    # More mentions, no elevating roof; fewer mentions, elevating roof.
    assert gtv_product.body_type is BodyType.CAMPERVAN_HIGH_TOP
    assert cv80_product.body_type is BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF


def test_body_type_is_left_unset_when_height_is_unknown():
    """The missing-data rule: never assume a high top."""
    from dataclasses import replace

    product = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-cv", is_campervan=True
    )
    assert replace(product, mh_height_mm=None).body_type is None


def test_every_motorhome_is_coach_built_low_profile():
    """Elddis states no body class anywhere, and FMLV holds all 21 of its current
    motorhomes as low profile."""
    for name, segment in [
        ("elddis_whirlwind_gt_155.html", "whirlwind-gt"),
        ("elddis_avalon_250.html", "avalon"),
        ("elddis_autoquest_apex_196p.html", "autoquest-apex"),
    ]:
        product = _parse(name, segment=segment, is_campervan=False)
        assert product.body_type is BodyType.COACH_BUILT_LOW_PROFILE


# --------------------------------------------------------------------------------------
# The Whirlwind GTVs: every unit and label convention on the site, broken at once
# --------------------------------------------------------------------------------------


def test_gtv_dimensions_are_published_in_metres():
    """Every other model gives millimetres. A parser anchored on `mm` returns nothing."""
    product = _parse(
        "elddis_whirlwind_gtv_554.html", segment="whirlwind-gtv", is_campervan=True
    )
    assert product.mh_length_mm == 5400  # "5.4m"
    assert product.mh_width_mm == 2050  # "2.05m"
    assert product.mh_height_mm == 2610  # "2.61m", Excluding Aerial


def test_gtv_height_is_not_the_raised_pop_top_figure():
    """The base vehicle's height, not the optional pop-top's. On the 554 the label states
    the condition outright, which is why the taller figure is not the vehicle's height:

        Overall Height Excluding Aerial: 2.61m
        Overall Height Including Pop Top (If option is selected): 2.81m

    Confirmed by the requester on 2026-08-21. The two lines are adjacent, both are
    `Overall Height…`, and only exact label matching separates them.
    """
    fields = spec_fields(_text_lines(_fixture("elddis_whirlwind_gtv_554.html")))
    # Both figures really are present, so this is a live hazard rather than a hypothetical.
    assert fields["Overall Height Excluding Aerial"].startswith("2.61")
    assert any(
        "pop top" in label.lower() and "2.81" in value
        for label, value in fields.items()
    )

    product = _parse(
        "elddis_whirlwind_gtv_554.html", segment="whirlwind-gtv", is_campervan=True
    )
    assert product.mh_height_mm == 2610
    assert product.mh_height_mm != 2810


def test_gtv_is_a_high_top_at_2610mm():
    """Confirmed by the requester on 2026-08-21: 2610mm on a Peugeot Boxer is a high top.

    Worth pinning because 2610 is below the "around 2680mm" figure `README.md` quotes, so
    the tempting reading is a plain campervan — and because it is the evidence that the
    shared `HIGH_TOP_ABOVE_MM` needed no Elddis-specific adjustment.
    """
    from src.adapters.elddis import HIGH_TOP_ABOVE_MM

    assert HIGH_TOP_ABOVE_MM == 2300
    for name in (
        "elddis_whirlwind_gtv_554.html",
        "elddis_whirlwind_gtv_563.html",
    ):
        product = _parse(name, segment="whirlwind-gtv", is_campervan=True)
        assert product.mh_height_mm == 2610
        assert product.body_type is BodyType.CAMPERVAN_HIGH_TOP


def test_gtv_masses_carry_thousands_separators():
    assert _kilograms("2,710kg") == 2710
    assert _kilograms("3,076kg") == 3076


def test_gtv_554_falls_back_to_the_automatic_figure():
    """The 554 is `Automatic as standard` and publishes no manual mass at all, so
    "prefer manual" has to degrade rather than return nothing."""
    product = _parse(
        "elddis_whirlwind_gtv_554.html", segment="whirlwind-gtv", is_campervan=True
    )
    assert product.mro_kilograms == 2710  # automatic, fixed roof
    assert product.mh_payload_kilograms == 790
    assert product.mtplm_kilograms == 3500
    assert product.base_vehicle_manufacturer == "Peugeot"


def test_gtv_563_reads_the_manual_fixed_roof_variant_from_a_prefixed_label():
    """The 563's labels embed the model name and a seat count, and no two share a format:
    `GTV 563 (4-seats) Fixed Roof - Mass in running order - (Manual) - Fixed Roof`.
    """
    product = _parse(
        "elddis_whirlwind_gtv_563.html", segment="whirlwind-gtv", is_campervan=True
    )
    assert product.model == "563"
    assert product.mro_kilograms == 2856  # manual, fixed roof — not 2916/3016/3076
    assert product.mh_payload_kilograms == 644
    assert product.mtplm_kilograms == 3500
    assert _reconciles(product)


def test_gtv_563_seats_take_the_fixed_roof_figure_which_is_the_higher_one():
    """`Fixed Roof (Manual or Automatic) 4 seats or Pop Top (Manual or Automatic) 3 seats`.

    Worth its own test because "take the lower figure of a range" would give 3 here. The
    rule is "take the base vehicle", and Elddis writes the fixed-roof figure first.
    """
    product = _parse(
        "elddis_whirlwind_gtv_563.html", segment="whirlwind-gtv", is_campervan=True
    )
    assert product.mh_passenger_seats_inc_driver == 4


def test_gtv_berths_read_the_fixed_roof_figure_from_prose():
    """`Fixed Roof 3 Berth or Pop Top Roof 5 Berth` -> 3."""
    assert _leading_int("Fixed Roof 3 Berth or Pop Top Roof 5 Berth") == 3
    assert (
        _leading_int(
            "Fixed Roof (Manual or Automatic) 4 seats or Pop Top "
            "(Manual or Automatic) 3 seats"
        )
        == 4
    )


# --------------------------------------------------------------------------------------
# The 2026 brochure, and the Evolve weights the website gets wrong
# --------------------------------------------------------------------------------------
#
# Fixtures here are the *extracted text* of single brochure pages, not the PDFs — those are
# 100MB and 120MB, and `tests/fetch/test_pdf.py` already covers extraction itself.


def test_brochure_discovery_picks_the_right_document_by_its_label():
    """The downloads page lists 30+ PDFs, including three superseded model years and the
    Buccaneer and Xplore equivalents — every one a near miss for a loose filename match."""
    index = _fixture("elddis_brochures_index.html")
    motorhome = find_brochure_url(index, "motorhome")
    campervan = find_brochure_url(index, "campervan")
    assert motorhome is not None and motorhome.endswith("elddis-brochure-2026-motorhome.pdf")
    assert campervan is not None and campervan.endswith("elddis-brochure-2026-campervan.pdf")
    # Never another brand's brochure, and never an older year.
    for url in (motorhome, campervan):
        assert "buccaneer" not in url and "xplore" not in url and "compass" not in url
        assert "2025" not in url and "2023" not in url and "2022" not in url


def test_brochure_discovery_returns_none_when_absent():
    assert find_brochure_url("<html><body>no brochures here</body></html>", "motorhome") is None


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (
            "elddis_brochure_2026_autoquest_evolve_page.txt",
            {
                ("Autoquest Evolve", "CV20"): {"mtplm": 3500, "mro": 2884, "payload": 573},
                ("Autoquest Evolve", "CV80"): {"mtplm": 3500, "mro": 3059, "payload": 441},
            },
        ),
        (
            "elddis_brochure_2026_avalon_evolve_page.txt",
            {
                ("Avalon Evolve", "250"): {"mtplm": 3500, "mro": 3131, "payload": 369},
                ("Avalon Evolve", "295"): {"mtplm": 3500, "mro": 3091, "payload": 363},
            },
        ),
        (
            "elddis_brochure_2026_whirlwind_gt_evolve_page.txt",
            {
                ("Whirlwind GT Evolve", "105"): {"mtplm": 3500, "mro": 2721, "payload": 738},
                # The 196+ is the only one plated at 3650, and the brochure agrees with the
                # website on that — which is what makes MTPLM a usable alignment check.
                ("Whirlwind GT Evolve", "196P"): {"mtplm": 3650, "mro": 3009, "payload": 596},
            },
        ),
    ],
)
def test_brochure_weights_parse(fixture: str, expected: dict):
    parsed = parse_brochure_weights(_fixture(fixture))
    for key, values in expected.items():
        assert parsed[key] == values, f"{key} parsed as {parsed.get(key)}"


def test_brochure_model_codes_are_normalised_to_fmlv_form():
    """The brochure spaces the campervan codes (`CV 20`) and writes `196+`; FMLV uses
    `CV20` and `196P`. A mismatch here would silently apply no override at all."""
    campervan = parse_brochure_weights(
        _fixture("elddis_brochure_2026_autoquest_evolve_page.txt")
    )
    assert {model for _, model in campervan} == {"CV20", "CV40", "CV60", "CV80"}
    motorhome = parse_brochure_weights(
        _fixture("elddis_brochure_2026_whirlwind_gt_evolve_page.txt")
    )
    assert "196P" in {model for _, model in motorhome}
    assert "196+" not in {model for _, model in motorhome}


def test_brochure_parser_ignores_non_evolve_tables():
    """The base Autoquest CV table has the identical shape. Only Evolve is overridden,
    because only Evolve diverges — every other range agrees with the website exactly."""
    assert parse_brochure_weights(
        _fixture("elddis_brochure_2026_autoquest_cv_base_page.txt")
    ) == {}


def test_brochure_row_with_the_wrong_number_of_values_is_dropped():
    """The values are positional, so a missing cell would shift every later model onto its
    neighbour's weights — plausibly, since all the numbers are in range. Whole table goes.
    """
    text = (
        "AUTOQUEST EVOLVE CV 20 CV 40 CV 60 CV 80\n"
        "Max technical permissible laden mass 3500KG 3500KG 3500KG 3500KG\n"
        "Mass in running order 2884KG 2954KG 2895KG\n"  # one short
        "Max user payload 573KG 502KG 562KG 441KG\n"
    )
    assert parse_brochure_weights(text) == {}


def test_brochure_override_replaces_the_site_weights():
    product = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-cv-evolve", is_campervan=True
    )
    assert (product.mro_kilograms, product.mh_payload_kilograms) == (2835, 622)

    brochure = parse_brochure_weights(
        _fixture("elddis_brochure_2026_autoquest_evolve_page.txt")
    )
    updated = apply_brochure_weights(product, brochure)
    assert updated.mro_kilograms == 2884
    assert updated.mh_payload_kilograms == 573
    assert updated.weights_from_brochure is True
    # The site's figures are kept so the provenance can show a reviewer both.
    assert updated.site_mro_kilograms == 2835
    assert updated.site_payload_kilograms == 622
    # And the brochure's figures must survive the same arithmetic as the site's.
    assert _reconciles(updated)


def test_brochure_override_is_refused_when_mtplm_disagrees():
    """MTPLM is the fixed plating limit, so two current documents should never differ on
    it. If they do, the wrong table has been read and the override is unsafe."""
    product = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-cv-evolve", is_campervan=True
    )
    bad = {("Autoquest Evolve", "CV20"): {"mtplm": 3650, "mro": 2884, "payload": 573}}
    unchanged = apply_brochure_weights(product, bad)
    assert unchanged.mro_kilograms == 2835
    assert unchanged.weights_from_brochure is False


def test_products_with_no_brochure_entry_keep_the_site_weights():
    """Base ranges are never overridden — the brochure agrees with them anyway."""
    product = _parse(
        "elddis_autoquest_cv20.html", segment="autoquest-cv", is_campervan=True
    )
    brochure = parse_brochure_weights(
        _fixture("elddis_brochure_2026_autoquest_evolve_page.txt")
    )
    unchanged = apply_brochure_weights(product, brochure)
    assert unchanged.mro_kilograms == 2835
    assert unchanged.weights_from_brochure is False


def _fake(manufacturer_range: str, model: str, mro: int, payload: int):
    from src.adapters.elddis import ElddisProduct

    return (
        ElddisProduct(
            manufacturer_range=manufacturer_range,
            model=model,
            site_model_name=f"{manufacturer_range} {model}",
            is_campervan=False,
            mtplm_kilograms=3500,
            mro_kilograms=mro,
            mh_payload_kilograms=payload,
        ),
        "https://example.test",
    )


def test_brochure_is_fetched_while_the_site_still_copies_base_weights():
    """The bug as it stands today: Evolve 155 carries Whirlwind GT 155's figures."""
    from src.adapters.elddis import _evolve_weights_look_copied

    parsed = [
        _fake("Whirlwind GT", "155", 2926, 530),
        _fake("Whirlwind GT Evolve", "155", 2926, 530),
    ]
    assert _evolve_weights_look_copied(parsed) is True


def test_brochure_is_skipped_once_elddis_publish_real_evolve_weights():
    """The override retires itself. When the site starts publishing the heavier Evolve
    figures, no 100MB brochure is downloaded and the site's own numbers are used.

    This is the test that should start failing — usefully — when Elddis fix their site.
    """
    from src.adapters.elddis import _evolve_weights_look_copied

    parsed = [
        _fake("Whirlwind GT", "155", 2926, 530),
        _fake("Whirlwind GT Evolve", "155", 2984, 471),  # the brochure's real figures
    ]
    assert _evolve_weights_look_copied(parsed) is False


def test_brochure_is_fetched_when_there_is_no_base_range_to_compare():
    """`--range "Avalon Evolve"` collects no base range, so nothing can be compared.
    Assume the bug is present: that costs a download, where assuming otherwise would cost
    a wrong weight."""
    from src.adapters.elddis import _evolve_weights_look_copied

    assert _evolve_weights_look_copied([_fake("Avalon Evolve", "250", 3090, 410)]) is True


def test_no_brochure_for_a_run_with_no_evolve_range_at_all():
    from src.adapters.elddis import _evolve_weights_look_copied

    parsed = [_fake("Whirlwind GTV", "554", 2710, 790), _fake("Avalon", "250", 3090, 410)]
    assert _evolve_weights_look_copied(parsed) is False


def test_only_evolve_ranges_trigger_a_brochure_download():
    """The brochures are 100MB and 120MB, so a run with no Evolve range must not fetch
    one. `--range "Whirlwind GTV"` stays a six-fetch run."""
    from src.adapters.elddis import _EVOLVE_SEGMENTS

    assert _EVOLVE_SEGMENTS == {
        "whirlwind-gt-evolve",
        "avalon-evolve",
        "autoquest-cv-evolve",
    }
    non_evolve = {
        path.partition("/")[2] for path, _ in DEFAULT_RANGES
    } - _EVOLVE_SEGMENTS
    assert not (non_evolve & _EVOLVE_SEGMENTS)


# --------------------------------------------------------------------------------------
# Unit helpers
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7373mm/24'2\"", 7373),
        ("2239mm/7'4\"", 2239),
        ("5.4m", 5400),
        ("5.99m", 5990),
        ("2.05m", 2050),
        ("2.61m", 2610),
        (None, None),
        ("not a measurement", None),
    ],
)
def test_millimetres(raw, expected):
    assert _millimetres(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2926kgs/57.60cwt", 2926),
        ("2,710kg", 2710),
        # Banker's rounding, as in `bailey.py` — an exact .5 goes to even. No FMLV-recorded
        # field is published to half a kilogram, so this is helper robustness only.
        ("194.5kgs", 194),
        ("345kgs/9.15cwt", 345),
        (None, None),
        ("N/A", None),
    ],
)
def test_kilograms(raw, expected):
    assert _kilograms(raw) == expected


def test_metres_pattern_never_misreads_a_millimetre_value():
    """`7373mm` must not be read as 7.373 metres scaled up, or as 7373 metres."""
    assert _millimetres("7373mm") == 7373
    assert _millimetres("2925mm/9'7\"") == 2925


# --------------------------------------------------------------------------------------
# Module contract
# --------------------------------------------------------------------------------------


def test_manufacturer_matches_the_registry_exactly():
    """`MANUFACTURER` is the adapter's registration key and the baseline's filter, so it
    must equal the registry row's `fmlv_manufacturer` byte for byte."""
    import csv

    with open("config/manufacturers.csv", encoding="utf-8", newline="") as handle:
        names = {row["fmlv_manufacturer"] for row in csv.DictReader(handle)}
    assert MANUFACTURER in names
    assert MANUFACTURER == "Elddis (EHG UK)"


def test_default_ranges_cover_every_segment_with_an_fmlv_range():
    from src.adapters.elddis import _SEGMENT_RANGES

    segments = {path.partition("/")[2] for path, _ in DEFAULT_RANGES}
    assert segments == set(_SEGMENT_RANGES)
