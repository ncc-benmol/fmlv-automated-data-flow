"""Auto-Trail's parsing functions, against real captured specification pages.

No network and no PDF parsing here — `tests/fetch/test_pdf.py` covers extraction, and
these fixtures are what it produces. The fixtures hold the spec-bearing pages of five
of the ten documents, chosen because each one broke the parser while it was being
written; the equipment-list pages between them are dropped. Every negative test below
is a trap that actually bit — see `docs/adapters/auto-trail.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters import auto_trail
from src.adapters.auto_trail import AutoTrailProduct
from src.product_model.enums import BodyType

FIXTURES = Path(__file__).parent / "fixtures"


def _parse(name: str, range_label: str) -> dict[str, AutoTrailProduct]:
    text = auto_trail.normalise((FIXTURES / name).read_text(encoding="utf-8"))
    return {product.model: product for product in auto_trail.parse_models(text, range_label)}


@pytest.fixture(scope="module")
def expedition_coachbuilt() -> dict[str, AutoTrailProduct]:
    return _parse("auto_trail_expedition_coachbuilt_spec_text.txt", "Expedition Coachbuilt")


@pytest.fixture(scope="module")
def expedition_van() -> dict[str, AutoTrailProduct]:
    return _parse("auto_trail_expedition_van_spec_text.txt", "Expedition")


@pytest.fixture(scope="module")
def frontier() -> dict[str, AutoTrailProduct]:
    return _parse("auto_trail_frontier_spec_text.txt", "Frontier")


@pytest.fixture(scope="module")
def v_line_se() -> dict[str, AutoTrailProduct]:
    return _parse("auto_trail_v_line_se_spec_text.txt", "V-Line SE")


@pytest.fixture(scope="module")
def f_line() -> dict[str, AutoTrailProduct]:
    return _parse("auto_trail_f_line_spec_text.txt", "F-Line")


# --------------------------------------------------------------------------- #
# Counts, against Auto-Trail's own published rosters
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("fixture_name", "range_label", "expected"),
    [
        ("auto_trail_expedition_coachbuilt_spec_text.txt", "Expedition Coachbuilt", 4),
        ("auto_trail_frontier_spec_text.txt", "Frontier", 3),
        ("auto_trail_expedition_van_spec_text.txt", "Expedition", 7),
        ("auto_trail_v_line_se_spec_text.txt", "V-Line SE", 4),
        ("auto_trail_f_line_spec_text.txt", "F-Line", 6),
    ],
)
def test_parses_exactly_the_models_the_document_claims(
    fixture_name: str, range_label: str, expected: int
) -> None:
    """Each document's `Applicable to` line is the manufacturer's own count."""
    text = auto_trail.normalise((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    assert len(auto_trail.parse_roster(text)) == expected
    assert len(auto_trail.parse_models(text, range_label)) == expected


def test_section_headings_are_not_mistaken_for_models(f_line: dict[str, AutoTrailProduct]) -> None:
    """`POWER`, `SAFETY` and `LIVING ROOM FEATURES` are all-caps lines too.

    Treating every all-caps line as a model heading picks up all of them; the roster is
    what filters them out.
    """
    assert set(f_line) == {"F60", "F62", "F67", "F70", "F72", "F74"}


# --------------------------------------------------------------------------- #
# The trap: gross train weight is not the maximum laden weight
# --------------------------------------------------------------------------- #


def test_gross_train_weight_is_not_read_as_mtplm(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
) -> None:
    """C63 publishes both figures; only the maximum laden weight is the MTPLM."""
    c63 = expedition_coachbuilt["C63"]
    assert c63.mtplm_kilograms == 3500
    assert c63.mgtw_kilograms == 4750
    assert c63.mro_kilograms == 2960
    assert c63.mh_payload_kilograms == 540


def test_c71_mtplm_is_not_invented_from_the_document(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
) -> None:
    """The trap this adapter exists to survive.

    C71's block goes straight from axle loadings to `Max. gross train weight`, with no
    `Max. gross weight` row at all. A loose parser reads 4750 kg and proposes a 7.26 m
    motorhome with a 1670 kg payload, which is plausible enough to be accepted.

    Nothing is inferred from the document. The 3500 kg below comes from the price list,
    read off the page image by a person — see the next test.
    """
    c71 = expedition_coachbuilt["C71"]
    assert c71.mgtw_kilograms == 4750  # present, and deliberately not used as the MTPLM
    assert c71.mro_kilograms == 3080
    assert c71.mtplm_kilograms == 3500
    assert c71.mtplm_manually_sourced is True


def test_a_manually_sourced_figure_is_flagged_as_such(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
) -> None:
    """The price list is a rasterised image, so C71's weight cannot be re-derived.

    It is marked so `collect` narrates it and the reviewer's provenance says where it came
    from and when — a figure no run can refresh must not look like one that can.
    """
    assert expedition_coachbuilt["C71"].mtplm_manually_sourced is True
    for model in ("C63", "C72", "C73"):
        assert expedition_coachbuilt[model].mtplm_manually_sourced is False


def test_the_document_always_beats_the_manual_figure() -> None:
    """If Auto-Trail add the missing row, the parsed value must win immediately."""
    text = auto_trail.normalise(
        (FIXTURES / "auto_trail_expedition_coachbuilt_spec_text.txt").read_text(encoding="utf-8")
    ).replace(
        "Max. gross train weight (with 3650kg upgrade MGTW increases to 4900kg) 4750/4900kg",
        "Max. gross weight (with 3650kgs no cost option) 3650/4400kg\n"
        "Max. gross train weight (with 3650kg upgrade MGTW increases to 4900kg) 4750/4900kg",
    )
    c71 = {p.model: p for p in auto_trail.parse_models(text, "Expedition Coachbuilt")}["C71"]
    assert c71.mtplm_kilograms == 3650  # from the document, not the 3500 in the table
    assert c71.mtplm_manually_sourced is False


def test_a_gross_train_weight_read_as_mtplm_is_rejected() -> None:
    """The same trap, stated as the check that catches it."""
    misparsed = AutoTrailProduct(
        range_label="Expedition Coachbuilt",
        model="C71",
        mtplm_kilograms=4750,  # actually the gross train weight
        mgtw_kilograms=4750,
        mro_kilograms=3080,
    )
    assert not auto_trail._reconciles(misparsed)


# --------------------------------------------------------------------------- #
# The trap: campervans label the maximum laden weight differently
# --------------------------------------------------------------------------- #


def test_campervans_use_max_authorised_weight(expedition_van: dict[str, AutoTrailProduct]) -> None:
    """Campervans say `Max. authorised weight`, never `Max. gross weight`.

    Matching only the motorhome label loses all 16 campervan weights while looking like
    "campervans don't publish any".
    """
    van_54 = expedition_van["54"]
    assert van_54.mtplm_kilograms == 3500
    assert van_54.mro_kilograms == 2685
    assert van_54.mh_payload_kilograms == 815


# --------------------------------------------------------------------------- #
# The trap: the parenthetical contradicts the row
# --------------------------------------------------------------------------- #


def test_parenthetical_boilerplate_is_not_read_as_the_weight(
    frontier: dict[str, AutoTrailProduct],
) -> None:
    """Frontier rows carry `(with 3650kgs no cost option)` on 4500 and 5000 kg vehicles.

    Reading the parenthetical rather than the figure at the end of the row yields
    3650 kg for a 5000 kg motorhome.
    """
    assert frontier["Delaware"].mtplm_kilograms == 4500
    assert frontier["Comanche"].mtplm_kilograms == 5000


def test_first_of_several_weights_is_the_standard_build() -> None:
    """`3500/3650/4400kg` lists the standard build first, upgrades after."""
    assert auto_trail._leading_kilograms("3500/3650/4400") == 3500
    assert auto_trail._leading_kilograms("4,750/4,900") == 4750


# --------------------------------------------------------------------------- #
# The trap: the kerning artefact
# --------------------------------------------------------------------------- #


def test_kerning_artefact_is_repaired() -> None:
    """`T` before a lowercase letter renders with a spurious space."""
    assert auto_trail.normalise("T otal seats 4") == "Total seats 4"
    assert auto_trail.normalise("Max. T orque 350Nm") == "Max. Torque 350Nm"


def test_kerning_repair_leaves_real_single_letter_words_alone() -> None:
    """Only `T` is repaired.

    A broader `[A-Z] ` rule also fires on `ECWVT A compliance` and `T&C s`, which are
    real word boundaries, and would corrupt them.
    """
    assert auto_trail.normalise("A compliance to all relevant EU standards") == (
        "A compliance to all relevant EU standards"
    )


def test_seats_are_read_despite_the_kerning_artefact(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
) -> None:
    """Without the repair, `Total seats` never matches and every count is empty."""
    assert expedition_coachbuilt["C63"].mh_passenger_seats_inc_driver == 4


# --------------------------------------------------------------------------- #
# Berths and seats
# --------------------------------------------------------------------------- #


def test_berths_and_seats_both_take_the_standard_figure(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
) -> None:
    """C73 is `Sleeps 4-6` with `Seatbelts 4-6`.

    Auto-Trail market it as "truly a six-berth", but the sixth berth and the fifth and
    sixth belts are both options — their own copy calls it an "*optional* six-belt"
    motorhome. FMLV carries one figure per spec and it is the standard build, per the
    base-vehicle rule in `docs/adapters/README.md`.
    """
    c73 = expedition_coachbuilt["C73"]
    assert c73.berths == 4
    assert c73.mh_passenger_seats_inc_driver == 4
    assert c73.sleeps_published == "4-6"  # the reviewer still sees what was published


def test_a_single_berth_figure_is_unaffected(
    expedition_van: dict[str, AutoTrailProduct],
) -> None:
    """Most campervans publish `Sleeps 2`, with no range to reduce."""
    assert expedition_van["54"].berths == 2
    assert expedition_van["54"].sleeps_published == "2"


def test_published_maxima_agree_with_each_other(
    f_line: dict[str, AutoTrailProduct],
    frontier: dict[str, AutoTrailProduct],
) -> None:
    """`Max. No. of berths` restates the upper bound of `Sleeps`, not the standard figure.

    The check compares the two *maxima* with each other. Comparing either against
    `berths` would fail on every model whose `Sleeps` is a range, since `berths` now
    records the lower bound.
    """
    for product in (*f_line.values(), *frontier.values()):
        assert product.stated_max_berths == product.sleeps_max


def test_a_berth_range_still_reconciles(f_line: dict[str, AutoTrailProduct]) -> None:
    """Regression: recording the standard figure must not trip the maximum check.

    `Sleeps 2-4` with `Max. No. of berths 4` gives `berths=2` and `sleeps_max=4`. A
    check written against `berths` would reject this — and it is 17 of the 37 layouts.
    """
    f60 = f_line["F60"]
    assert f60.berths == 2
    assert f60.sleeps_max == 4
    assert f60.stated_max_berths == 4
    assert auto_trail._reconciles(f60)


def test_disagreeing_berth_maxima_are_rejected() -> None:
    """Two maxima that disagree mean the block boundaries slipped."""
    slipped = AutoTrailProduct(
        range_label="F-Line",
        model="F70",
        berths=2,
        sleeps_max=4,
        stated_max_berths=6,  # read out of the following model's block
        mtplm_kilograms=3500,
        mro_kilograms=2980,
    )
    assert not auto_trail._reconciles(slipped)


# --------------------------------------------------------------------------- #
# Model naming
# --------------------------------------------------------------------------- #


def test_range_prefix_is_stripped_from_model_names(
    v_line_se: dict[str, AutoTrailProduct],
    f_line: dict[str, AutoTrailProduct],
) -> None:
    """Auto-Trail repeats the range name on the roster's first entry only.

    `Applicable to V-Line 540 SE, 610 SE, 635 SE, 636 SE` must not yield one model
    called `V-Line 540 SE` beside three called `610 SE`. Note the range label is
    `V-Line SE` while the entry says `V-Line 540 SE`, so only the first word is a
    prefix.
    """
    assert set(v_line_se) == {"540 SE", "610 SE", "635 SE", "636 SE"}
    assert "F60" in f_line  # roster says `F-LINE F60` against a `F-Line` range label


def test_model_names_without_a_range_prefix_are_left_alone(
    frontier: dict[str, AutoTrailProduct],
) -> None:
    """Frontier's roster is bare names: `Delaware, Scout, Comanche`."""
    assert set(frontier) == {"Delaware", "Scout", "Comanche"}


def test_overlapping_campervan_names_stay_separate(
    expedition_van: dict[str, AutoTrailProduct],
) -> None:
    """`68`, `68 XL` and `68 XL Flex` are three products, not one.

    Blocks are matched by suffix, which is safe here only because the variants extend
    the tail: `EXPEDITION 68 XL` does not end with `68`.
    """
    assert {"68", "68 XL", "68 XL Flex"} <= set(expedition_van)
    assert expedition_van["68"].mh_length_mm == 6363
    assert expedition_van["54"].mh_length_mm == 5413


# --------------------------------------------------------------------------- #
# The two Expeditions
# --------------------------------------------------------------------------- #


def test_the_two_expedition_ranges_are_labelled_separately(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
    expedition_van: dict[str, AutoTrailProduct],
) -> None:
    """Nothing in a model's own name separates the coachbuilts from the campervans.

    The range comes from which document the model was read out of, and the two must not
    collapse into one `manufacturer_range`.
    """
    assert expedition_coachbuilt["C73"].range_label == "Expedition Coachbuilt"
    assert expedition_van["68"].range_label == "Expedition"
    assert not set(expedition_coachbuilt) & set(expedition_van)


def test_both_expedition_ranges_are_registered_and_distinct() -> None:
    labels = [label for _path, label in auto_trail.DEFAULT_RANGES]
    assert len(labels) == len(set(labels))
    assert "Expedition Coachbuilt" in labels
    assert "Expedition" in labels


# --------------------------------------------------------------------------- #
# The towing identity, and why it warns rather than drops
# --------------------------------------------------------------------------- #


def test_towing_identity_holds_for_a_normal_motorhome(
    frontier: dict[str, AutoTrailProduct],
) -> None:
    assert auto_trail._towing_identity_holds(frontier["Delaware"])
    assert auto_trail._towing_identity_holds(frontier["Scout"])


def test_comanche_fails_the_towing_identity_but_is_still_proposed(
    frontier: dict[str, AutoTrailProduct],
) -> None:
    """Auto-Trail's own inconsistency, not a misparse.

    Comanche is a 5000 kg tri-axle carrying the 1500 kg towing figure that belongs to
    the 4500 kg Delaware and Scout. Its weights are correct, so it warns and is kept.
    """
    comanche = frontier["Comanche"]
    assert comanche.mgtw_kilograms - comanche.mtplm_kilograms != comanche.towing_kilograms
    assert not auto_trail._towing_identity_holds(comanche)
    assert auto_trail._reconciles(comanche)
    assert comanche.mh_payload_kilograms == 965


# --------------------------------------------------------------------------- #
# Dimensions
# --------------------------------------------------------------------------- #


def test_width_excludes_the_awning(expedition_coachbuilt: dict[str, AutoTrailProduct]) -> None:
    """The row is followed by `(2408mm with awning)` on its own line."""
    assert expedition_coachbuilt["C63"].mh_width_mm == 2373


def test_a_dual_height_takes_the_base_vehicle(frontier: dict[str, AutoTrailProduct]) -> None:
    """Frontier publishes `Height 3030/3106mm`.

    The extra 76 mm is the roof-mounted satellite dome in the optional Media+ pack, so
    3030 is the vehicle. Same rule as `3500/3650kg` for weights — see the base-vehicle
    rule in `docs/adapters/README.md`. A pattern anchored on `mm` reads 3106 instead.
    """
    for product in frontier.values():
        assert product.mh_height_mm == 3030


def test_a_malformed_dimension_is_left_unread_and_narrated(
    f_line: dict[str, AutoTrailProduct],
) -> None:
    """The F74 publishes `Height 2880m` — a typo for 2880mm.

    Accepting a bare `m` would mean reading a figure whose unit the document got wrong,
    so the value stays unread and the gap is narrated instead of being silent.
    """
    f74 = f_line["F74"]
    assert f74.mh_height_mm is None
    assert f74.mh_length_mm == 7327
    assert f74.parse_warnings == ("Height row is present but its value could not be read",)
    assert f_line["F72"].mh_height_mm == 2880  # every other F-Line publishes it correctly


# --------------------------------------------------------------------------- #
# Body types and chassis
# --------------------------------------------------------------------------- #


def test_body_type_distinguishes_over_cab_bed_from_over_cab_storage(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
    frontier: dict[str, AutoTrailProduct],
) -> None:
    """"Lo-Line ... with over cab *storage* area" is a low profile, not an over-cab bed."""
    assert expedition_coachbuilt["C63"].body_type is BodyType.COACH_BUILT_OVER_CAB_BED
    assert frontier["Scout"].body_type is BodyType.COACH_BUILT_OVER_CAB_BED
    assert frontier["Delaware"].body_type is BodyType.COACH_BUILT_LOW_PROFILE


def test_campervans_are_high_tops(expedition_van: dict[str, AutoTrailProduct]) -> None:
    """No `BODY STYLES` section, so the type comes from the roof instead.

    All seven Expedition Vans are 2680mm — a roof line materially above the side windows,
    which is what makes a high top. Their pop-top is a **cost option**, so it does not
    change the base vehicle.
    """
    assert all(p.body_type is BodyType.CAMPERVAN_HIGH_TOP for p in expedition_van.values())


def test_a_standard_pop_top_makes_it_a_high_top_elevating_roof() -> None:
    """Adventure fits the same pop-top as the Expedition Van, but `Included` not optional.

    Same 2680mm shell, same dimensions — the difference is one word at the end of the row,
    and it is the difference between two body types.
    """
    adventure = """ADVENTURE 55
Sleeps 4
Height 2680mm
Colour coded elevating pop-top roof (including bathroom window) Included
"""
    assert auto_trail._body_type(adventure) is BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF


def test_an_optional_pop_top_does_not_change_the_body_type() -> None:
    """The base-vehicle rule: an extra the buyer may not have is not what the vehicle is."""
    expedition = """EXPEDITION 67
Sleeps 2-4
Height 2680mm
Colour coded elevating pop-top roof (bathroom window included) Cost option
"""
    assert auto_trail._body_type(expedition) is BodyType.CAMPERVAN_HIGH_TOP


def test_a_standard_height_campervan_is_not_a_high_top() -> None:
    """Below 2300mm the roof is a standard van roof.

    The threshold is drawn from FMLV's own data: the tallest standard-height campervan on
    the site is 2050mm, so 2300mm clears every known one while sitting far below the
    2680mm every Auto-Trail campervan shares.
    """
    low = """SOME VAN
Sleeps 2
Height 2100mm
"""
    assert auto_trail._body_type(low) is BodyType.CAMPERVAN


def test_a_standard_height_campervan_with_a_standard_pop_top() -> None:
    """The fourth combination — a pop-top on a standard roof, not on a high top."""
    low_pop_top = """SOME VAN
Sleeps 2
Height 2100mm
Colour coded elevating pop-top roof Included
"""
    assert auto_trail._body_type(low_pop_top) is BodyType.CAMPERVAN_ELEVATING_ROOF


def test_body_type_is_unset_only_when_the_height_is_unknown() -> None:
    """Height answers the high-top question, so without it nothing can be said."""
    no_height = """SOME VAN
Sleeps 2
"""
    assert auto_trail._body_type(no_height) is None


def test_chassis_make_is_captured(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
    f_line: dict[str, AutoTrailProduct],
) -> None:
    assert expedition_coachbuilt["C63"].base_vehicle_manufacturer == "Fiat"
    assert f_line["F60"].base_vehicle_manufacturer == "Ford"


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_finds_the_spec_pdf_despite_the_upload_counter() -> None:
    html = """<a href="https://www.auto-trail.co.uk/wp-content/uploads/Auto-Trail-Website-Tech-Spec-F-Line-8.pdf">spec</a>"""
    assert auto_trail.find_spec_pdf_url(html) == (
        "https://www.auto-trail.co.uk/wp-content/uploads/Auto-Trail-Website-Tech-Spec-F-Line-8.pdf"
    )


def test_price_list_is_not_mistaken_for_the_spec_pdf() -> None:
    """Model pages link both; only the technical specification carries the numbers."""
    html = """<a href="https://www.auto-trail.co.uk/wp-content/uploads/Motorhome-Price-and-Options-List-1st-June-2026-2.pdf">prices</a>"""
    assert auto_trail.find_spec_pdf_url(html) is None


def test_model_urls_are_read_in_order_and_deduplicated() -> None:
    """Slugs are not derivable from names, so links are read rather than constructed."""
    html = """
    <a href="https://www.auto-trail.co.uk/motorhomes/f-line-f60/">F60</a>
    <a href="https://www.auto-trail.co.uk/motorhomes/f67/">F67</a>
    <a href="https://www.auto-trail.co.uk/motorhomes/f-line-f60/">F60 again</a>
    """
    assert auto_trail.find_model_urls(html) == [
        "https://www.auto-trail.co.uk/motorhomes/f-line-f60/",
        "https://www.auto-trail.co.uk/motorhomes/f67/",
    ]


def test_manufacturer_matches_the_registry_key() -> None:
    """`MANUFACTURER` is the `ADAPTERS` key and must equal `fmlv_manufacturer` exactly."""
    assert auto_trail.MANUFACTURER == "Auto-Trail"


# --------------------------------------------------------------------------- #
# Price: the on-the-road figure, and the join it depends on
# --------------------------------------------------------------------------- #


def _card(url: str, title: str, price: str | None) -> str:
    """One range-page model card, in the shape Auto-Trail's theme emits."""
    price_block = f'<div class="card-price">Price from £{price}</div>' if price else ""
    return f"""
    <a href="{url}" class="card">
        <div class="card-image-section"><div class="model-number">x</div></div>
        <div class="card-content">
            <h4 class="card-title">{title}</h4>
            <div class="card-details">{price_block}<div class="card-description"></div></div>
        </div>
    </a>
    """


F_LINE_PAGE = _card("https://www.auto-trail.co.uk/motorhomes/f-line-f60/", "F-Line         F60", "69,005.00") + _card(
    "https://www.auto-trail.co.uk/motorhomes/f67/", "F-Line F67", "69,638.00"
)


def test_price_is_read_from_the_range_page() -> None:
    """The price list PDF is a rasterised image; the range page is the only text source."""
    prices = auto_trail.parse_prices(F_LINE_PAGE, "F-Line")
    assert auto_trail.price_for("F60", "F-Line", prices) == 69005
    assert auto_trail.price_for("F67", "F-Line", prices) == 69638


def test_run_together_whitespace_in_a_card_title_is_ignored() -> None:
    """WordPress emits `F-Line         F60`; the join must not care."""
    assert auto_trail._match_key("F-Line         F60", "F-Line") == "F60"


def test_the_join_survives_the_range_words_moving_around_the_number() -> None:
    """The document says `V-Line 610 Sport`; the page says `V-Line Sport 610`.

    Neither is a prefix of the other, so head-trimming cannot align them. Dropping every
    word belonging to the range label, wherever it sits, leaves `610` on both sides.
    """
    page = _card("https://www.auto-trail.co.uk/campervans/v-line-sport-610/", "V-Line Sport 610", "80,440.00")
    prices = auto_trail.parse_prices(page, "V-Line Sport")
    assert auto_trail.price_for("610 Sport", "V-Line Sport", prices) == 80440


def test_the_join_survives_the_page_naming_a_range_the_document_does_not() -> None:
    """The page says `Expedition Van 54`; the document's roster says just `54`.

    "Expedition Van" is the document-internal name and the range is called "Expedition"
    on the website, so neither side can be renamed to match the other.
    """
    page = _card("https://www.auto-trail.co.uk/campervans/54-2/", "Expedition Van 54", "54,959.00")
    prices = auto_trail.parse_prices(page, "Expedition")
    assert auto_trail.price_for("54", "Expedition", prices) == 54959


def test_overlapping_campervan_names_do_not_take_each_others_prices() -> None:
    """`68`, `68 XL` and `68 XL Flex` are three products at two prices.

    Suffix matching is only safe because the variants extend the tail: `VAN68XL` does not
    end with `68`. Getting this wrong would give the 68 its bigger sibling's price.
    """
    page = (
        _card("https://www.auto-trail.co.uk/campervans/expedition-68/", "Expedition Van 68", "60,153.00")
        + _card("https://www.auto-trail.co.uk/campervans/68xl/", "Expedition Van 68XL", "60,153.00")
        + _card("https://www.auto-trail.co.uk/campervans/68xl-flex/", "Expedition Van 68XL Flex", "62,035.00")
    )
    prices = auto_trail.parse_prices(page, "Expedition")
    assert auto_trail.price_for("68", "Expedition", prices) == 60153
    assert auto_trail.price_for("68 XL", "Expedition", prices) == 60153
    assert auto_trail.price_for("68 XL Flex", "Expedition", prices) == 62035


def test_a_card_without_a_price_does_not_borrow_the_next_ones() -> None:
    """The pattern cannot cross a card boundary, so an unpriced model stays unpriced."""
    page = _card("https://www.auto-trail.co.uk/motorhomes/f-line-f60/", "F-Line F60", None) + _card(
        "https://www.auto-trail.co.uk/motorhomes/f67/", "F-Line F67", "69,638.00"
    )
    prices = auto_trail.parse_prices(page, "F-Line")
    assert auto_trail.price_for("F60", "F-Line", prices) is None
    assert auto_trail.price_for("F67", "F-Line", prices) == 69638


def test_an_unmatched_model_yields_no_price_rather_than_a_guess() -> None:
    """Price is the one field with no arithmetic check behind it."""
    prices = auto_trail.parse_prices(F_LINE_PAGE, "F-Line")
    assert auto_trail.price_for("F999", "F-Line", prices) is None


def test_price_is_read_as_whole_pounds() -> None:
    assert auto_trail._pounds("69,005.00") == 69005
    assert auto_trail._pounds("129,784.00") == 129784
