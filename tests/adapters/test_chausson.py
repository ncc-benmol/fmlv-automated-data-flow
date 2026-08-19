"""Chausson's parsing and joining, against real captured pages.

No network. `chausson_ranges_cards.html` is every model card trimmed out of
`/ranges/`, with the real page's duplication preserved on purpose. The
`chausson_model_*.html` fixtures are each model page's heading and characteristics rows.

Six model pages were kept, each for a reason: `650` as the ordinary case, `640` because it
publishes two vehicles' figures in one cell, `v594` for the campervan roof rule, `c514` for
the overcab body type, `x550` for the X line's body type and its in-between width, and
`x650` because it is a soft 404. Every negative test below is a trap that actually bit — see
`docs/adapters/chausson.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters import chausson
from src.adapters.chausson import ChaussonCard, ChaussonProduct
from src.product_model.enums import BodyType

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _model(slug: str) -> str:
    return _read(f"chausson_model_{slug}.html")


@pytest.fixture(scope="module")
def cards() -> dict[str, ChaussonCard]:
    return chausson.parse_cards(_read("chausson_ranges_cards.html"))


def _product(slug: str, cards: dict[str, ChaussonCard]) -> ChaussonProduct:
    """Build a product the way `collect` does, from a card plus its model page."""
    html = _model(slug)
    rows = chausson.parse_rows(html)
    range_label, model = chausson.parse_heading(html)
    return ChaussonProduct(
        card=cards[slug],
        range_label=range_label,
        model=model,
        mh_width_mm=chausson._millimetres(chausson.find_row(rows, chausson.LABEL_WIDTH) or ""),
        mh_height_mm=chausson._millimetres(chausson.find_row(rows, chausson.LABEL_HEIGHT) or ""),
        mtplm_kilograms=chausson._kilograms(chausson.find_row(rows, chausson.LABEL_MTPLM) or ""),
        mro_kilograms=chausson._kilograms(chausson.find_row(rows, chausson.LABEL_MRO) or ""),
    )


# --------------------------------------------------------------------------- #
# The cards: read forward, because the details follow the title
# --------------------------------------------------------------------------- #


def test_every_model_gets_its_own_card(cards: dict[str, ChaussonCard]) -> None:
    """18 real models, deduplicated from a page that renders each of them repeatedly."""
    assert len(cards) == 18


def test_the_details_belong_to_their_own_title(cards: dict[str, ChaussonCard]) -> None:
    """The trap: a card's details block comes *after* its title.

    Associating a details block with the nearest preceding title attributes the previous
    model's figures. It read S614's as S697's, and went unnoticed because the two cost the
    same and differ only in berths — which is exactly what this asserts.
    """
    assert cards["s614"].rrp_pounds == cards["s697"].rrp_pounds == 58_790
    assert cards["s614"].berths_published == "4"
    assert cards["s697"].berths_published == "2/3*"
    assert cards["s614"].berths == 4
    assert cards["s697"].berths == 2


def test_the_price_is_found_despite_being_written_in_gbp(cards: dict[str, ChaussonCard]) -> None:
    """Chausson write `From 58 790 GBP`, never a pound sign.

    Searching for `£` finds only the five line-level figures in the page nav and misses every
    one of the real per-model prices.
    """
    assert cards["s514"].rrp_pounds == 55_790
    assert cards["v594"].rrp_pounds == 57_490
    assert cards["x640"].rrp_pounds == 74_990


def test_length_and_base_vehicle_come_from_the_same_picto(cards: dict[str, ChaussonCard]) -> None:
    """Both live in `class="porteur picto ford"` — the logo and the metres beside it.

    Note the class ends in the make, not in `picto`. A pattern anchored on `picto"` matched
    the berth and seat counts and silently missed every single length.
    """
    assert cards["s614"].mh_length_mm == 6590
    assert cards["s614"].base_vehicle_manufacturer == "Ford"
    assert cards["c656"].base_vehicle_manufacturer == "Citroen"
    assert cards["v594"].base_vehicle_manufacturer == "Fiat"
    assert cards["v594"].mh_length_mm == 5990


def test_the_displayed_name_is_not_unique(cards: dict[str, ChaussonCard]) -> None:
    """`x550` and `x640` render as `550` and `640` — and `640` is also a Low profile.

    Two cards therefore show `640`. The slug is the identity; the name is not.
    """
    assert cards["640"].name == cards["x640"].name == "640"
    assert cards["640"].rrp_pounds is None
    assert cards["x640"].rrp_pounds == 74_990
    assert cards["640"].base_vehicle_manufacturer == "Ford"
    assert cards["x640"].base_vehicle_manufacturer == "Fiat"


def test_berths_take_the_standard_figure(cards: dict[str, ChaussonCard]) -> None:
    """Chausson write berths three ways, two of them with an optional extra.

    Per the data rules the lower figure is recorded, and the published string is kept so the
    provenance can show a reviewer what was on the page.
    """
    assert (cards["s697"].berths_published, cards["s697"].berths) == ("2/3*", 2)
    assert (cards["v594"].berths_published, cards["v594"].berths) == ("2+1*", 2)
    assert (cards["627"].berths_published, cards["627"].berths) == ("3/5*", 3)
    assert (cards["s614"].berths_published, cards["s614"].berths) == ("4", 4)


# --------------------------------------------------------------------------- #
# The model page: rows scoped per <li>
# --------------------------------------------------------------------------- #


def test_rows_are_paired_within_one_list_item() -> None:
    """The page carries more labels than values, so the two lists cannot be zipped.

    `/model/650/` has 26 labels and 21 values — the chassis and option-price blocks have
    labels and no figures. Zipping drifted by five and paired `Overall width (m)` with
    `1845x605`, a side-locker aperture, and the laden mass with `100L`, the waste tank.
    """
    rows = chausson.parse_rows(_model("650"))
    assert chausson.find_row(rows, chausson.LABEL_WIDTH) == "2.35"
    assert chausson.find_row(rows, chausson.LABEL_HEIGHT) == "2.92"
    assert chausson.find_row(rows, chausson.LABEL_MTPLM) == "3500"
    assert chausson.find_row(rows, chausson.LABEL_MRO) == "2896"


def test_the_range_comes_from_the_heading() -> None:
    """`Low profiles 650` -> (`Low profiles`, `650`). The only reliable statement of a line."""
    assert chausson.parse_heading(_model("650")) == ("Low profiles", "650")
    assert chausson.parse_heading(_model("v594")) == ("Vans", "V594")
    assert chausson.parse_heading(_model("c514")) == ("Overcab", "C514")
    assert chausson.parse_heading(_model("x550")) == ("X", "X550")


def test_a_soft_404_has_no_characteristics() -> None:
    """`/model/x650/` returns HTTP 200 with the `/ranges/` page and no accordion at all.

    It is linked from `/ranges/` and has no card. A page with no characteristics is an absent
    model, not a product with every field blank — so the real count is 18, not the 19 linked.
    """
    html = _model("x650")
    assert chausson.has_characteristics(html) is False
    assert chausson.parse_rows(html) == {}
    assert chausson.has_characteristics(_model("650")) is True


# --------------------------------------------------------------------------- #
# The trap: two vehicles' figures in one cell
# --------------------------------------------------------------------------- #


def test_a_two_vehicle_cell_takes_the_leading_figure(cards: dict[str, ChaussonCard]) -> None:
    """`/model/640/` publishes the 640's figures and a van's in the same cells.

    `2.35 / 2.05` width, `2.92 / 2.65` height, `3007 / 3085` running order. The second column
    is not a variant of the 640 — those three figures match the V594 exactly. Taking the last
    would put a van's dimensions on a coachbuilt, and every value would look plausible.
    """
    rows = chausson.parse_rows(_model("640"))
    assert chausson.find_row(rows, chausson.LABEL_WIDTH) == "2.35 / 2.05"
    assert chausson.find_row(rows, chausson.LABEL_MRO) == "3007 / 3085"

    product = _product("640", cards)
    assert product.mh_width_mm == 2350  # the 640's, not the van's 2050
    assert product.mh_height_mm == 2920
    assert product.mro_kilograms == 3007
    assert product.mh_payload_kilograms == 493


def test_the_second_column_really_is_another_vehicle(cards: dict[str, ChaussonCard]) -> None:
    """Stated as a test so the reasoning is checkable, not just asserted in a comment."""
    van = _product("v594", cards)
    assert van.mh_width_mm == 2050
    assert van.mh_height_mm == 2650
    rows = chausson.parse_rows(_model("640"))
    assert chausson.find_row(rows, chausson.LABEL_WIDTH).endswith("2.05")
    assert chausson.find_row(rows, chausson.LABEL_HEIGHT).endswith("2.65")


# --------------------------------------------------------------------------- #
# Body type
# --------------------------------------------------------------------------- #


def test_the_line_supplies_the_coachbuilt_body_types(cards: dict[str, ChaussonCard]) -> None:
    assert _product("650", cards).body_type is BodyType.COACH_BUILT_LOW_PROFILE
    assert _product("c514", cards).body_type is BodyType.COACH_BUILT_OVER_CAB_BED


def test_a_van_gets_its_body_type_from_the_roof(cards: dict[str, ChaussonCard]) -> None:
    """A campervan's type turns on roof height, not on which range it sits in.

    The V594 is 2.65 m overall, well above the 2300 mm high-top threshold, and Chausson list
    no pop-top as standard — so it is a high top.
    """
    van = _product("v594", cards)
    assert van.range_label == "Vans"
    assert van.mh_height_mm == 2650
    assert van.body_type is BodyType.CAMPERVAN_HIGH_TOP


def test_a_standard_height_van_would_not_be_a_high_top(cards: dict[str, ChaussonCard]) -> None:
    """The threshold is a floor, not an equality test against Chausson's current heights."""
    low = ChaussonProduct(card=cards["v594"], range_label="Vans", model="V594", mh_height_mm=2100)
    assert low.body_type is BodyType.CAMPERVAN
    unknown = ChaussonProduct(card=cards["v594"], range_label="Vans", model="V594")
    assert unknown.body_type is None


def test_the_x_line_is_coach_built(cards: dict[str, ChaussonCard]) -> None:
    """Settled by the NCC side, 19 August 2026: the X counts as coach built.

    Its 2.1 m width genuinely sits between a van's 2.05 and a coachbuilt's 2.35, which is why
    it was left for a decision. FMLV has no plain "coach built", so low profile is recorded —
    the X has no over-cab bed, being a compact on a 3.8 m wheelbase.
    """
    x550 = _product("x550", cards)
    assert x550.range_label == "X"
    assert x550.mh_width_mm == 2100
    assert x550.body_type is BodyType.COACH_BUILT_LOW_PROFILE


def test_an_unknown_line_gets_no_body_type(cards: dict[str, ChaussonCard]) -> None:
    """A line Chausson add later must not inherit a body type by accident."""
    invented = ChaussonProduct(
        card=cards["x550"], range_label="Some New Line", model="Z999", mh_height_mm=2750
    )
    assert invented.body_type is None


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def test_the_real_models_reconcile(cards: dict[str, ChaussonCard]) -> None:
    for slug in ("650", "640", "v594", "c514", "x550"):
        assert chausson._reconciles(_product(slug, cards)), slug


def test_a_mass_from_the_wrong_column_is_rejected(cards: dict[str, ChaussonCard]) -> None:
    """What the two-vehicle cells threaten: a running order belonging to another vehicle."""
    slipped = ChaussonProduct(
        card=cards["650"], range_label="Low profiles", model="650",
        mtplm_kilograms=3500, mro_kilograms=3500,
    )
    assert not chausson._reconciles(slipped)

    absurd = ChaussonProduct(
        card=cards["650"], range_label="Low profiles", model="650",
        mtplm_kilograms=3500, mro_kilograms=1000,
    )
    assert absurd.mh_payload_kilograms == 2500
    assert not chausson._reconciles(absurd)


def test_a_missing_mass_is_a_gap_not_a_contradiction(cards: dict[str, ChaussonCard]) -> None:
    partial = ChaussonProduct(card=cards["650"], range_label="Low profiles", model="650")
    assert chausson._reconciles(partial)
    assert partial.mh_payload_kilograms is None


def test_each_line_from_price_is_its_cheapest_model(cards: dict[str, ChaussonCard]) -> None:
    """The cross-check between two independently rendered figures.

    The five line-level "From" prices in the page nav are not used as product prices — they
    cover a group, not one model — but each should equal the cheapest per-model card price in
    its line, which is a free check on the card parse.
    """
    s_line = [cards[s].rrp_pounds for s in ("s514", "s614", "s697")]
    assert min(s_line) == 55_790  # the nav's "S Low Profiles From £55,790"
    x_line = [cards[s].rrp_pounds for s in ("x550", "x640")]
    assert min(x_line) == 73_990  # the nav's "X From £73,990"


# --------------------------------------------------------------------------- #
# Value parsing
# --------------------------------------------------------------------------- #


def test_prices_group_thousands_with_spaces() -> None:
    assert chausson._pounds("58 790") == 58_790
    assert chausson._pounds("74 990") == 74_990
    assert chausson._pounds("") is None


def test_metres_become_millimetres() -> None:
    assert chausson._millimetres("2.35") == 2350
    assert chausson._millimetres("6.59") == 6590
    assert chausson._millimetres("2,05") == 2050  # a comma decimal, should Chausson use one
    assert chausson._millimetres("") is None


def test_the_leading_figure_wins_for_every_kind_of_value() -> None:
    assert chausson._leading("2.35 / 2.05") == "2.35"
    assert chausson._leading("3007 / 3085") == "3007"
    assert chausson._leading("3500") == "3500"


def test_manufacturer_matches_the_registry_key() -> None:
    """`MANUFACTURER` is the `ADAPTERS` key and must equal `fmlv_manufacturer` exactly."""
    assert chausson.MANUFACTURER == "Trigano VDL Chausson"
    assert chausson.MANUFACTURER_DISPLAY_NAME == "Chausson"


def test_caravans_are_not_a_concern_and_all_five_lines_are_covered() -> None:
    """Chausson build motorhomes only, so unlike Coachman there is nothing to exclude."""
    labels = [label for _slug, label in chausson.DEFAULT_RANGES]
    assert labels == ["Low profiles", "S Low Profiles", "Overcab", "Vans", "X"]
    assert len(labels) == len(set(labels))
