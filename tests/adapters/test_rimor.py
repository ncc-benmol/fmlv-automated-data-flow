"""Rimor's parsing functions, against real captured pages.

No network and no PDF parsing here — `tests/fetch/test_pdf.py` covers extraction, and
these fixtures are what it produces. Every negative test below is a trap that actually
bit while the adapter was being written; see `docs/adapters/rimor.md`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src.adapters import rimor
from src.adapters.rimor import RimorCard
from src.product_model.enums import BedType, BodyType

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def kilig_range() -> str:
    return _fixture("rimor_kilig_range.html")


@pytest.fixture(scope="module")
def kilig_listing() -> str:
    return _fixture("rimor_kilig_low_profile_listing.html")


@pytest.fixture(scope="module")
def kilig_5() -> str:
    return _fixture("rimor_kilig_5_model.html")


@pytest.fixture(scope="module")
def sarus_8() -> str:
    return _fixture("rimor_sarus_8_model.html")


@pytest.fixture(scope="module")
def horus_leaflet() -> str:
    return _fixture("rimor_horus_uk_leaflet_text.txt")


@pytest.fixture(scope="module")
def catalogue() -> str:
    return _fixture("rimor_catalogue_spec_pages_text.txt")


# --------------------------------------------------------------------------- #
# Range page
# --------------------------------------------------------------------------- #


def test_body_style_links_are_found_in_page_order(kilig_range: str) -> None:
    assert rimor.parse_body_style_links(kilig_range, "kilig") == ["low-profile", "overcab"]


def test_body_style_links_ignore_the_other_ranges_in_the_nav(kilig_range: str) -> None:
    """Every page carries a nav linking all five ranges, plus its own body styles.

    Filtering on the range slug is what keeps `/gamma/sarus/...` out of Kilig's list.
    """
    assert rimor.parse_body_style_links(kilig_range, "sarus") == []


def test_unknown_body_style_segments_are_dropped_not_guessed() -> None:
    """A new segment has no `BodyType` to map to, so it is skipped rather than assumed."""
    html = '<a href="/int/en/gamma/kilig/low-profile"></a><a href="/int/en/gamma/kilig/tiny-house"></a>'
    assert rimor.parse_body_style_links(html, "kilig") == ["low-profile"]


def test_leaflet_url_is_read_off_the_range_page(kilig_range: str) -> None:
    url = rimor.parse_leaflet_url(kilig_range)
    assert url is not None
    assert url.endswith("Kilig 2025-26 - EU - V2 - WEB.pdf")
    # Rediscovered per run rather than hardcoded: the filename carries both a season
    # and a version, and the versions already differ between ranges.
    assert "/BrochureGamme/brochure/raw/" in url


def test_leaflet_url_is_none_when_no_pdf_is_linked() -> None:
    assert rimor.parse_leaflet_url("<html><a href='/int/en/gamma/kilig'>x</a></html>") is None


# --------------------------------------------------------------------------- #
# Body-style listing page
# --------------------------------------------------------------------------- #


def test_listing_finds_every_layout_including_slug_named_ones(kilig_listing: str) -> None:
    """Kilig low-profile is 7 layouts, and not one of them has a numeric slug.

    A `modello/\\d+` pattern finds none of these and quietly reports the range as empty —
    which is how the first survey pass found 18 of the 41 layouts instead of all of them.
    """
    cards = rimor.parse_model_cards(kilig_listing)
    assert [card.name for card in cards] == [
        "Kilig 66 Plus",
        "Kilig 67 Plus",
        "Kilig 69 Plus",
        "Kilig 77 Plus",
        "Kilig 78 Plus",
        "Kilig 79 Plus",
        "Kilig 95 Plus",
    ]
    assert all(card.url.startswith("/int/en/gamma/kilig/modello/") for card in cards)


def test_listing_deduplicates_the_repeated_model_block(kilig_listing: str) -> None:
    """The list is rendered twice — main content and footer — so 7 layouts appear 14 times."""
    assert kilig_listing.count('class="stretched-link') == 14
    assert len(rimor.parse_model_cards(kilig_listing)) == 7


def test_listing_reads_seats_and_berths_off_the_right_card(kilig_listing: str) -> None:
    by_name = {card.name: card for card in rimor.parse_model_cards(kilig_listing)}
    # Kilig 79 Plus is the only 7-seater in the body style, so a card boundary that
    # leaked into its neighbour would show up here first.
    assert by_name["Kilig 79 Plus"].seats == 7
    assert by_name["Kilig 79 Plus"].berths == 4
    assert by_name["Kilig 67 Plus"].seats == 4
    assert by_name["Kilig 67 Plus"].berths == 2


def test_listing_ignores_a_card_with_no_figures() -> None:
    html = (
        '<a href="/int/en/gamma/kilig/modello/5" class="stretched-link my-3 fw-bold"> Kilig 5 </a>'
    )
    (card,) = rimor.parse_model_cards(html)
    assert (card.seats, card.berths) == (None, None)


# --------------------------------------------------------------------------- #
# Model page
# --------------------------------------------------------------------------- #


def _card(url: str, name: str, seats: int | None = None, berths: int | None = None) -> RimorCard:
    return RimorCard(url=url, name=name, seats=seats, berths=berths)


def test_model_page_reads_identity_dimensions_and_layout(kilig_5: str) -> None:
    model = rimor.parse_model_page(
        kilig_5, "/int/en/gamma/kilig/modello/5", _card("/int/en/gamma/kilig/modello/5", "Kilig 5")
    )
    assert model is not None
    assert model.range_label == "Kilig"
    assert model.model == "5"
    assert model.body_style == "overcab"
    assert model.body_type is BodyType.COACH_BUILT_OVER_CAB_BED
    # Only the *outside* figure of each pair: 2340 not 2200, 3040 not 2060.
    assert (model.mh_length_mm, model.mh_width_mm, model.mh_height_mm) == (6970, 2340, 3040)
    assert model.bedding_solution == "Transverse bed"
    assert model.bed_types == [BedType.TRANSVERSE]


def test_model_page_takes_the_leading_integer_of_an_optional_berths_cell(kilig_5: str) -> None:
    """Kilig 5 publishes "4 (+ 2 opt)" — spaced, unlike most pages' "4 (+2 opt)".

    Four is the standard configuration; the other two need optional equipment. The
    verbatim text is kept for provenance because the integer alone loses that.
    """
    model = rimor.parse_model_page(
        kilig_5, "/int/en/gamma/kilig/modello/5", _card("/int/en/gamma/kilig/modello/5", "Kilig 5")
    )
    assert model is not None
    assert model.berths == 4
    assert model.berths_text == "4 (+ 2 opt)"
    assert model.mh_passenger_seats_inc_driver == 6


def test_model_page_handles_a_height_row_with_no_spaces_round_the_dash(sarus_8: str) -> None:
    """Sarus 8 alone writes "3050-2075 mm" where every other page writes "3050 - 2075 mm"."""
    assert "3050-2075 mm" in sarus_8
    model = rimor.parse_model_page(
        sarus_8, "/int/en/gamma/sarus/modello/8", _card("/int/en/gamma/sarus/modello/8", "Sarus 8")
    )
    assert model is not None
    assert model.mh_height_mm == 3050


def test_model_page_does_not_read_a_sibling_layouts_figures(kilig_5: str) -> None:
    """Every model page repeats the whole range in an "other range models" block.

    Those cards carry the same `numero posti` markup, so an unscoped read attributes a
    sibling's seats and berths to this product — silently, and plausibly.
    """
    assert kilig_5.count(rimor._SEATS_TITLE) > 1
    model = rimor.parse_model_page(
        kilig_5, "/int/en/gamma/kilig/modello/5", _card("/int/en/gamma/kilig/modello/5", "Kilig 5")
    )
    assert model is not None
    # Kilig 5's own figures, not Kilig 50's (6 seats / 6 berths) which follows it.
    assert (model.mh_passenger_seats_inc_driver, model.berths) == (6, 4)


def test_model_page_carries_the_cards_figures_through_for_checking(kilig_5: str) -> None:
    card = _card("/int/en/gamma/kilig/modello/5", "Kilig 5", seats=6, berths=4)
    model = rimor.parse_model_page(kilig_5, card.url, card)
    assert model is not None
    assert (model.card_seats, model.card_berths) == (6, 4)


def test_model_page_without_an_overview_block_is_none() -> None:
    assert rimor.parse_model_page("<html><body>maintenance</body></html>", "/x", _card("/x", "X")) is None


def test_model_falls_back_to_the_cards_name_when_the_heading_is_missing() -> None:
    html = (
        '<a href="/int/en/gamma/kilig/low-profile" class="tipologia">Low profile</a>'
        '<a class="gamma">Kilig</a>'
        'id="panoramica-modello" <td>outside length</td><td> 7308 mm </td> END PANORAMICA MODELLO'
    )
    model = rimor.parse_model_page(html, "/x", _card("/x", "Kilig 95 Plus"))
    assert model is not None
    assert model.model == "Kilig 95 Plus"


# --------------------------------------------------------------------------- #
# Bedding solutions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("solution", "expected"),
    [
        ("French bed", [BedType.FIXED]),
        ("Double bed", [BedType.FIXED]),
        ("Transverse bed", [BedType.TRANSVERSE]),
        ("Twin beds", [BedType.FIXED_SEPARATE]),
        ("Central bed", [BedType.ISLAND]),
        ("Bunk beds", [BedType.FIXED_BUNKS]),
        ("Rear suite bed", [BedType.FIXED]),
        ("XL Front drop-down bed", [BedType.DROP_DOWN]),
        ("Two drop-down beds", [BedType.DROP_DOWN]),
    ],
)
def test_bedding_solutions_map_to_bed_types(solution: str, expected: list[BedType]) -> None:
    assert rimor.bed_types_for(solution) == expected


@pytest.mark.parametrize(
    "solution",
    ["Double bunk beds", "Double superimposed bunk beds"],
)
def test_bunk_solutions_are_not_swallowed_by_the_double_bed_prefix(solution: str) -> None:
    """"Double bunk beds" contains "bunk beds" *and* starts like "Double bed".

    Ordering `BEDDING_SOLUTIONS` longest-first is the only thing stopping a bunk layout
    being recorded as a fixed double.
    """
    assert rimor.bed_types_for(solution) == [BedType.FIXED_BUNKS]


def test_an_unmapped_bedding_solution_yields_no_bed_types() -> None:
    assert rimor.bed_types_for("Hammock") == []
    assert rimor.bed_types_for(None) == []


# --------------------------------------------------------------------------- #
# Leaflet — the self-check's second source
# --------------------------------------------------------------------------- #


def test_leaflet_yields_one_dimension_pair_per_layout(horus_leaflet: str) -> None:
    """Horus is 7 layouts: two at 5413, four at 5998 and one at 6363, all 2050 wide."""
    assert rimor.parse_leaflet_dimensions(horus_leaflet) == Counter(
        {(5413, 2050): 2, (5998, 2050): 4, (6363, 2050): 1}
    )


def test_leaflet_ignores_bed_and_garage_openings() -> None:
    """Beds are written in the same `WxH` notation and must not be read as vehicles."""
    assert rimor.parse_leaflet_dimensions("1280x850 6970x2340 1050x630") == Counter(
        {(6970, 2340): 1}
    )


# --------------------------------------------------------------------------- #
# Catalogue — page-constant values only
# --------------------------------------------------------------------------- #


def test_catalogue_gives_mtplm_and_chassis_per_range(catalogue: str) -> None:
    facts = rimor.parse_catalogue(catalogue, (("horus", "Horus"), ("kilig", "Kilig")))
    assert facts["Horus"].mtplm_kilograms == 3500
    assert facts["Horus"].base_vehicle_manufacturer == "Fiat"
    assert facts["Kilig"].mtplm_kilograms == 3500
    assert facts["Kilig"].base_vehicle_manufacturer == "Ford"


def test_catalogue_spec_row_has_fewer_values_than_models(catalogue: str) -> None:
    """Why nothing per-model may be read out of the catalogue.

    The Horus page covers three layouts but prints two lengths, because a value spanning
    several columns is printed once. pypdf returns the whole row as a single run, so
    there is no way to tell which model each value belongs to — this is the fixture that
    documents the failure the adapter refuses to risk.
    """
    row = next(line for line in catalogue.splitlines() if line.startswith("Outside length"))
    assert row.split() == ["Outside", "length", "(mm)", "5413", "5998"]
    assert "HORUS 12 HORUS 38 HORUS 45" in catalogue  # three models, two values


def test_catalogue_drops_a_field_when_a_ranges_pages_disagree() -> None:
    """Disagreement means "page-constant" has stopped holding, so the value is unsafe."""
    text = (
        "HORUS 12\nDIMENSIONS AND WEIGHTS\nMaximum overall weight (kg) 3500\nEngine Fiat Ducato\n"
        "\n\n"
        "HORUS 95\nDIMENSIONS AND WEIGHTS\nMaximum overall weight (kg) 4400\nEngine Fiat Ducato\n"
    )
    facts = rimor.parse_catalogue(text, (("horus", "Horus"),))
    assert facts["Horus"].mtplm_kilograms is None
    assert facts["Horus"].base_vehicle_manufacturer == "Fiat"


def test_catalogue_urls_try_the_newer_season_and_version_first() -> None:
    urls = rimor.catalogue_urls(2026)
    assert "Catalogo%202026-27%20-%20EU%20-%20V9.pdf" in urls[0]
    assert "Catalogo%202025-26%20-%20EU%20-%20V1.pdf" in urls[-1]
    # Two seasons, because a run may fall either side of the changeover.
    assert len(urls) == 2 * rimor.MAX_CATALOGUE_VERSION


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def _model(**overrides: object) -> rimor.RimorModel:
    defaults: dict[str, object] = {
        "range_label": "Kilig",
        "model": "5",
        "url": "/int/en/gamma/kilig/modello/5",
        "mh_passenger_seats_inc_driver": 6,
        "berths": 4,
        "mh_length_mm": 6970,
        "mh_width_mm": 2340,
        "card_seats": 6,
        "card_berths": 4,
    }
    return rimor.RimorModel(**(defaults | overrides))  # type: ignore[arg-type]


LEAFLET = Counter({(6970, 2340): 1})


def test_a_consistent_layout_reconciles() -> None:
    assert rimor._reconciles(_model(), LEAFLET)[0] is True


def test_a_layout_whose_card_and_page_disagree_on_seats_is_rejected() -> None:
    ok, reason = rimor._reconciles(_model(card_seats=4), LEAFLET)
    assert ok is False
    assert "4 seats" in reason


def test_a_layout_whose_card_and_page_disagree_on_berths_is_rejected() -> None:
    ok, reason = rimor._reconciles(_model(card_berths=2), LEAFLET)
    assert ok is False
    assert "berths" in reason


def test_a_layout_the_leaflet_does_not_list_is_rejected() -> None:
    ok, reason = rimor._reconciles(_model(mh_length_mm=9999), LEAFLET)
    assert ok is False
    assert "9999x2340" in reason


def test_the_dimension_check_is_order_independent() -> None:
    """The leaflet's own reading order is scrambled, so only membership may be used."""
    shuffled = Counter({(7308, 2340): 1, (6970, 2340): 1, (6449, 2340): 1})
    assert rimor._reconciles(_model(), shuffled)[0] is True


def test_nothing_to_compare_against_passes() -> None:
    """Absence is not contradiction: a missing leaflet must not drop the whole range."""
    assert rimor._reconciles(_model(), Counter())[0] is True
    assert rimor._reconciles(_model(card_seats=None, card_berths=None), LEAFLET)[0] is True
