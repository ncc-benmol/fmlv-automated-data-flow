"""Etrusco's parsing, against real captured family pages.

No network. Each `etrusco_<family>.html` fixture is one model family page trimmed to the two
things the adapter reads: the floorplan slider's `<h3>` headlines, and then every layout's
`<h4>` subline followed by the two tables belonging to it. The real page's duplication — each
layout named once in the slider and once beside its own tables — is preserved on purpose,
because choosing between those two is what the parse gets right or wrong.

Six of the eight families were kept, each for a reason: `campervans_fiat` for the roof rule
and the two-letter `CV` prefix (and because the CV 540 is the layout that sells),
`semi_integrated_ford` because it is the family absent from both menus, `overcab_fiat` for the
over-cab body type and the one berth figure published without a range, `integrated_fiat` for
the A class, and `cv_modelle_fiat_plus` and `t_modelle_fiat_base` because they are the two
families sitting under the longer URL path — the ones a roster taken from a single menu misses.

Every negative test below is a trap that actually bit — see `docs/adapters/etrusco.md`.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from src.adapters import etrusco
from src.adapters.etrusco import EtruscoLayout
from src.product_model.enums import BodyType

FIXTURES = Path(__file__).parent / "fixtures"

#: (family path, range label, expected layout count) for each captured page.
CAPTURED = (
    ("campervans-fiat", "CV-Model Fiat", 5),
    ("cv-modelle-fiat_plus", "CV-Model Plus", 3),
    ("semi-integrated-ford", "T-Model Ford", 4),
    ("t-modelle-fiat_base", "T-Model Base", 5),
    ("overcab-fiat", "A-Model Base", 2),
    ("integrated-fiat", "I-Model Fiat", 3),
)


def _read(family: str) -> str:
    return (FIXTURES / f"etrusco_{family.replace('-', '_')}.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def layouts() -> dict[str, EtruscoLayout]:
    """Every captured layout, keyed on its model name, parsed the way `collect` parses it."""
    found: dict[str, EtruscoLayout] = {}
    for family, range_label, _count in CAPTURED:
        for layout in etrusco.parse_layouts(family, range_label, _read(family)):
            found[layout.model] = layout
    return found


# --------------------------------------------------------------------------- #
# The layout names: the subline, not the slider
# --------------------------------------------------------------------------- #


def test_every_layout_on_a_family_page_is_found() -> None:
    for family, _label, count in CAPTURED:
        assert len(etrusco.parse_layout_names(_read(family))) == count, family


def test_the_names_are_read_in_the_order_the_page_renders_them() -> None:
    """Order is the whole pairing mechanism: name *n* belongs to table pair *n*."""
    assert etrusco.parse_layout_names(_read("campervans-fiat")) == [
        "CV 540 DB",
        "CV 600 SB",
        "CV 600 DB",
        "CV 640 SB",
        "CV 640 PB",
    ]


def test_a_name_appearing_twice_is_counted_once() -> None:
    """Each layout is named in the slider *and* beside its tables. Only one of them pairs.

    Anchoring on the subline is what keeps the names in step with the tables; the count here
    would be ten, not five, if both were taken.
    """
    html = _read("campervans-fiat")
    assert html.count("CV 540 DB") == 2
    assert html.count("o-floorplan__headline") == 5
    assert html.count("o-floorplan__subline") == 5
    assert len(etrusco.parse_layout_names(html)) == 5


def test_the_names_are_not_in_a_tab_title_attribute() -> None:
    """The first version of this parser looked for `data-tab-title`, which does not exist.

    It returned no layouts at all, and every family was skipped. The attribute is asserted
    absent so that a page rewrite reintroducing it is a visible change rather than a silent
    one, and so the dead end is not tried twice.
    """
    html = _read("campervans-fiat")
    assert "data-tab-title" not in html
    assert re.findall(r'data-tab-title="([^"]+)"', html) == []


# --------------------------------------------------------------------------- #
# The paired tables
# --------------------------------------------------------------------------- #


def test_labels_and_values_come_from_two_tables_zipped_by_row() -> None:
    html = _read("campervans-fiat")
    assert html.count("<table") == 10  # two per layout
    specs = etrusco.parse_spec_tables(html)
    assert len(specs) == 5
    assert specs[0][etrusco.LABEL_PRICE] == "£59,099"
    assert specs[0][etrusco.LABEL_DIMENSIONS] == "541 | 205 | 270"
    assert specs[0][etrusco.LABEL_CHASSIS] == "Fiat Ducato"


def test_a_dropped_table_is_a_mismatch_and_not_a_realignment() -> None:
    """The check `collect` makes before pairing anything.

    Losing one table shifts every later value onto the wrong label, which would produce
    entirely plausible motorhomes carrying each other's weights. The counts stop matching
    instead, and `collect` drops the whole family rather than guessing.
    """
    html = _read("campervans-fiat")
    last = list(re.finditer(r"<table.*?</table>", html, re.S))[-1]
    without_last_table = html[: last.start()] + html[last.end() :]
    assert without_last_table.count("<table") == 9
    assert len(etrusco.parse_layout_names(without_last_table)) == 5
    assert len(etrusco.parse_spec_tables(without_last_table)) == 4


# --------------------------------------------------------------------------- #
# Values
# --------------------------------------------------------------------------- #


def test_dimensions_are_one_cell_in_centimetres(layouts: dict[str, EtruscoLayout]) -> None:
    """`541 | 205 | 270` is three figures in one cell, and none of them are millimetres."""
    campervan = layouts["CV 540 DB"]
    assert (campervan.mh_length_mm, campervan.mh_width_mm, campervan.mh_height_mm) == (
        5410,
        2050,
        2700,
    )
    overcab = layouts["A 6.9 DB"]
    assert (overcab.mh_length_mm, overcab.mh_width_mm, overcab.mh_height_mm) == (6990, 2320, 3100)


def test_berths_take_the_standard_figure(layouts: dict[str, EtruscoLayout]) -> None:
    """`2 - 5 OPT` is two as built; the other three need optional equipment."""
    assert layouts["CV 540 DB"].berths_published == "2 - 5 OPT"
    assert layouts["CV 540 DB"].berths == 2
    assert layouts["I 6900 SB"].berths_published == "4 - 5 OPT"
    assert layouts["I 6900 SB"].berths == 4


def test_a_berth_figure_published_without_a_range_is_taken_whole() -> None:
    """The over-cab A 6.9 DB publishes a bare `6`, and six is what it sleeps."""
    parsed = {
        layout.model: layout
        for layout in etrusco.parse_layouts("overcab-fiat", "A-Model Base", _read("overcab-fiat"))
    }
    assert parsed["A 6.9 DB"].berths_published == "6"
    assert parsed["A 6.9 DB"].berths == 6
    assert parsed["A 6.9 SB"].berths_published == "4 - 5 OPT"
    assert parsed["A 6.9 SB"].berths == 4


def test_seats_are_the_permitted_number_including_driver(layouts: dict[str, EtruscoLayout]) -> None:
    """Etrusco publish exactly FMLV's basis, so no adjustment is made to it."""
    assert layouts["T 6.9 SF"].seats_published == "4"
    assert layouts["T 6.9 SF"].mh_passenger_seats_inc_driver == 4


def test_the_chassis_gives_the_base_vehicle_manufacturer(layouts: dict[str, EtruscoLayout]) -> None:
    assert layouts["T 6.9 SF"].base_vehicle_manufacturer == "Ford"  # 'Ford Transit'
    assert layouts["I 6900 SB"].base_vehicle_manufacturer == "Fiat"  # 'Fiat Ducato'


def test_the_price_is_the_layouts_own(layouts: dict[str, EtruscoLayout]) -> None:
    """Per-layout figures, so usable as a guide price; the overview's are range-level.

    Two layouts sharing a price is real rather than a parse collapsing them: the 640 SB and
    640 PB differ only in their bed, and Etrusco charge the same for both.
    """
    assert layouts["CV 540 DB"].rrp_pounds == 59_099
    assert layouts["CV 640 SB"].rrp_pounds == 61_499
    assert layouts["CV 640 PB"].rrp_pounds == 61_499


def test_the_plus_ranges_names_keep_their_suffix() -> None:
    """`CV 600 DB` and `CV 600 DB+` are two different vehicles at two different prices.

    The Plus range repeats the base range's layout names with a trailing `+`. Losing the
    suffix would collide six of the eight campervans onto three model names, and the join back
    to FMLV's existing products is on the name.
    """
    plus = etrusco.parse_layouts(
        "model-overview/cv-modelle-fiat_plus", "CV-Model Plus", _read("cv-modelle-fiat_plus")
    )
    assert [layout.model for layout in plus] == ["CV 600 DB+", "CV 640 SB+", "CV 640 PB+"]
    base = etrusco.parse_layouts("campervans-fiat", "CV-Model Fiat", _read("campervans-fiat"))
    shared = {layout.model for layout in base} & {layout.model for layout in plus}
    assert shared == set()
    assert next(l for l in plus if l.model == "CV 600 DB+").rrp_pounds == 60_999
    assert next(l for l in base if l.model == "CV 600 DB").rrp_pounds == 59_999


def test_each_ranges_from_price_is_its_cheapest_layout() -> None:
    """The cross-check between two independently rendered figures.

    The seven `Price from a)` figures on `/gb/en/modeloverview` are range-level and are not used
    as product prices, but each should equal the cheapest per-layout price in its range, which
    is a free check on the table parse. T-Model Ford is absent from that overview entirely, so
    it has no figure to check against — which is the same fact that nearly lost the family.
    """
    cheapest = {
        label: min(
            layout.rrp_pounds
            for layout in etrusco.parse_layouts(family, label, _read(family))
            if layout.rrp_pounds is not None
        )
        for family, label, _count in CAPTURED
    }
    assert cheapest["CV-Model Fiat"] == 59_099  # the overview's 'CV-Model Fiat Price from a)'
    assert cheapest["CV-Model Plus"] == 60_999
    assert cheapest["T-Model Base"] == 66_499
    assert cheapest["A-Model Base"] == 68_399
    assert cheapest["I-Model Fiat"] == 75_999


def test_prices_carry_a_thousands_comma_and_a_currency_symbol() -> None:
    assert etrusco._pounds("£67,100") == 67_100
    assert etrusco._pounds("£100,000") == 100_000
    assert etrusco._pounds("") is None


def test_a_mass_is_read_without_its_tolerance_band() -> None:
    assert etrusco._kilograms("2799 (2659 - 2939)*") == 2799
    assert etrusco._band("2799 (2659 - 2939)*") == (2659, 2939)
    assert etrusco._kilograms("3500") == 3500
    assert etrusco._band("3500") is None


def test_centimetres_become_millimetres() -> None:
    assert etrusco._centimetres_to_mm("698") == 6980
    assert etrusco._centimetres_to_mm(" 232 ") == 2320
    assert etrusco._centimetres_to_mm("") is None


# --------------------------------------------------------------------------- #
# Payload, which is derived and has a decoy sitting next to it
# --------------------------------------------------------------------------- #


def test_payload_is_maximum_laden_minus_running_order(layouts: dict[str, EtruscoLayout]) -> None:
    layout = layouts["T 6.9 SF"]
    assert (layout.mtplm_kilograms, layout.mro_kilograms) == (3500, 2799)
    assert layout.mh_payload_kilograms == 701


def test_payload_is_not_the_optional_equipment_mass() -> None:
    """The trap `sunlight.md` records too, and the reason the label is named in the adapter.

    `Manufacturer-specified mass for optional equipment` sits between the two masses in the
    same table and reads like it belongs there. It is a cap on factory-fitted extras: 341kg
    for the T 6.9 SF, against a real payload of 701kg.
    """
    html = _read("semi-integrated-ford")
    spec = etrusco.parse_spec_tables(html)[0]
    assert spec[etrusco.LABEL_NOT_PAYLOAD] == "341"
    layout = etrusco.parse_layouts("semi-integrated-ford", "T-Model Ford", html)[0]
    assert layout.mh_payload_kilograms == 701


def test_a_missing_mass_leaves_payload_blank(layouts: dict[str, EtruscoLayout]) -> None:
    """Per the data rule in `docs/adapters/README.md`: not found means blank, never inherited."""
    assert replace(layouts["T 6.9 SF"], mro_kilograms=None).mh_payload_kilograms is None
    assert replace(layouts["T 6.9 SF"], mtplm_kilograms=None).mh_payload_kilograms is None


# --------------------------------------------------------------------------- #
# The self-check: a printed tolerance band
# --------------------------------------------------------------------------- #


def test_every_captured_layout_reconciles(layouts: dict[str, EtruscoLayout]) -> None:
    assert len(layouts) == 22
    for model, layout in layouts.items():
        assert layout.mro_band is not None, model  # the check is worthless if the band is missed
        assert etrusco._band_reconciles(layout), model
        assert etrusco._reconciles(layout), model


def test_a_band_from_the_wrong_column_is_rejected(layouts: dict[str, EtruscoLayout]) -> None:
    """What a slipped column looks like: one layout's mass beside another's band.

    Both figures are real and both belong to a T 7.3, which is exactly why nothing downstream
    would question the result. The arithmetic does: 2858kg ±5% is 2715 - 3001, not 2725 - 3011.
    """
    slipped = replace(layouts["T 7.3 SF"], mro_band=layouts["T 7.3 SCF"].mro_band)
    assert slipped.mro_kilograms == 2858
    assert slipped.mro_band == (2725, 3011)
    assert not etrusco._band_reconciles(slipped)
    assert not etrusco._reconciles(slipped)


def test_a_kilogram_of_printed_rounding_is_not_a_failure(layouts: dict[str, EtruscoLayout]) -> None:
    """The band is printed rounded to whole kilograms, so it is never exactly ±5%."""
    layout = layouts["T 6.9 SF"]
    assert layout.mro_kilograms == 2799  # 2799 x 0.95 = 2659.05, printed as 2659
    assert layout.mro_band == (2659, 2939)
    assert etrusco._band_reconciles(layout)
    assert not etrusco._band_reconciles(replace(layout, mro_band=(2650, 2939)))


def test_a_missing_band_is_a_gap_not_a_contradiction(layouts: dict[str, EtruscoLayout]) -> None:
    assert etrusco._band_reconciles(replace(layouts["T 6.9 SF"], mro_band=None))
    assert etrusco._band_reconciles(replace(layouts["T 6.9 SF"], mro_kilograms=None))


def test_masses_leaving_no_payload_are_rejected(layouts: dict[str, EtruscoLayout]) -> None:
    layout = replace(layouts["T 6.9 SF"], mro_band=None)
    assert not etrusco._reconciles(replace(layout, mro_kilograms=3500))
    assert not etrusco._reconciles(replace(layout, mro_kilograms=1000))  # 2500kg payload, absurd
    assert etrusco._reconciles(replace(layout, mtplm_kilograms=None, mro_kilograms=None))


# --------------------------------------------------------------------------- #
# Body type
# --------------------------------------------------------------------------- #


def test_the_family_supplies_the_coachbuilt_body_types(layouts: dict[str, EtruscoLayout]) -> None:
    assert layouts["I 6900 SB"].body_type is BodyType.A_CLASS
    assert layouts["T 6.9 SF"].body_type is BodyType.COACH_BUILT_LOW_PROFILE
    assert layouts["A 6.9 DB"].body_type is BodyType.COACH_BUILT_OVER_CAB_BED


def test_a_campervan_gets_its_body_type_from_the_roof(layouts: dict[str, EtruscoLayout]) -> None:
    """A campervan's type is a property of its roof, not of the range it sits in."""
    campervan = layouts["CV 540 DB"]
    assert campervan.mh_height_mm == 2700
    assert campervan.mh_height_mm > etrusco.HIGH_TOP_ABOVE_MM
    assert campervan.body_type is BodyType.CAMPERVAN_HIGH_TOP


def test_a_standard_height_campervan_would_not_be_a_high_top(
    layouts: dict[str, EtruscoLayout],
) -> None:
    """Etrusco publish none, but the rule is the threshold and not the range."""
    assert replace(layouts["CV 540 DB"], mh_height_mm=2050).body_type is BodyType.CAMPERVAN
    assert replace(layouts["CV 540 DB"], mh_height_mm=None).body_type is None


def test_an_unknown_model_letter_gets_no_body_type(layouts: dict[str, EtruscoLayout]) -> None:
    """A new range letter is a blank, not a guess at the nearest known type."""
    assert replace(layouts["I 6900 SB"], range_label="Q-Model Fiat").body_type is None


def test_the_body_type_comes_from_the_letter_and_not_the_url() -> None:
    """The two URL shapes name the same body type differently, so the path cannot decide it.

    `overcab-fiat` and `model-overview/t-modelle-fiat_base` are both real paths; a rule keyed on
    the path segment worked on the first shape and returned nothing on the second.
    """
    low_profile = etrusco.parse_layouts(
        "model-overview/t-modelle-fiat_base", "T-Model Base", _read("t-modelle-fiat_base")
    )
    assert [layout.body_type for layout in low_profile] == [BodyType.COACH_BUILT_LOW_PROFILE] * 5


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


def test_manufacturer_matches_the_registry_key() -> None:
    """`MANUFACTURER` is the `ADAPTERS` key and must equal `fmlv_manufacturer` exactly."""
    assert etrusco.MANUFACTURER == "Etrusco"
    assert etrusco.MANUFACTURER_DISPLAY_NAME == "Etrusco"


def test_all_eight_uk_families_are_covered_and_named_distinctly() -> None:
    """Etrusco build no caravans, so unlike Coachman there is nothing to exclude.

    Eight families, and no single menu lists them all: the model overview omits
    `semi-integrated-ford`, and a roster taken from it would also have to cope with the two
    families living under the longer `model-overview/` path. Twelve of the twenty-eight layouts
    sit in the three families one menu or the other leaves out.
    """
    paths = [path for path, _label in etrusco.DEFAULT_RANGES]
    labels = [label for _path, label in etrusco.DEFAULT_RANGES]
    assert len(paths) == 8
    assert len(labels) == len(set(labels))
    assert "semi-integrated-ford" in paths  # in the sitemap only, in neither menu
    assert "model-overview/cv-modelle-fiat_plus" in paths  # the second path shape
    assert "model-overview/t-modelle-fiat_base" in paths
