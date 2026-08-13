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


def test_c71_has_no_mtplm_and_none_is_invented(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
) -> None:
    """The trap this adapter exists to survive.

    C71's block goes straight from axle loadings to `Max. gross train weight`, with no
    `Max. gross weight` row at all. A loose parser reads 4750 kg and proposes a 7.26 m
    motorhome with a 1670 kg payload, which is plausible enough to be accepted.
    """
    c71 = expedition_coachbuilt["C71"]
    assert c71.mtplm_kilograms is None
    assert c71.mh_payload_kilograms is None
    assert c71.mgtw_kilograms == 4750  # present, and deliberately not used as the MTPLM
    assert c71.mro_kilograms == 3080


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


def test_berths_take_the_maximum_and_seats_the_standard(
    expedition_coachbuilt: dict[str, AutoTrailProduct],
) -> None:
    """C73 is `Sleeps 4-6` with `Seatbelts 4-6`, and is sold as "truly a six-berth"."""
    c73 = expedition_coachbuilt["C73"]
    assert c73.berths == 6
    assert c73.mh_passenger_seats_inc_driver == 4


def test_berths_agree_with_the_separately_published_maximum(
    f_line: dict[str, AutoTrailProduct],
    frontier: dict[str, AutoTrailProduct],
) -> None:
    """`Max. No. of berths` is an independent statement of the same figure."""
    for product in (*f_line.values(), *frontier.values()):
        assert product.stated_max_berths == product.berths


def test_disagreeing_berth_counts_are_rejected() -> None:
    """Two berth figures that disagree mean the block boundaries slipped."""
    slipped = AutoTrailProduct(
        range_label="F-Line",
        model="F70",
        berths=4,
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


def test_campervan_body_type_is_left_unset(expedition_van: dict[str, AutoTrailProduct]) -> None:
    """The campervan documents have no `BODY STYLES` section, so nothing is guessed."""
    assert all(product.body_type is None for product in expedition_van.values())


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
