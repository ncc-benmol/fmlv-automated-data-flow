"""Tests for the Weinsberg adapter's pure parsing functions, against real artefacts.

Fixtures captured 3 September 2026 — see `docs/adapters/weinsberg.md`. The price lists
are the **extracted text** of the PDFs, trimmed to the technical-data and options pages
the parsers actually read and stored as a JSON list of page strings; the PDFs themselves
are never committed, and `tests/fetch/test_pdf.py` covers the extraction. The HTML pages
are untrimmed, including WEINSBERG's 404 — which is served with HTTP 200 and so is a
fixture in its own right.

No network here.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.adapters.weinsberg import (
    DEFAULT_RANGES,
    DOWNLOADS_URL,
    HIGH_TOP_ABOVE_MM,
    MANUFACTURER,
    MANUFACTURER_DISPLAY_NAME,
    RANGES,
    PriceListRow,
    RangeSpec,
    _body_type,
    _build_extracted_motorhome,
    _centimetres_to_mm,
    _chassis_values,
    _mass_rows,
    _price_values,
    _row_values,
    _thousands,
    baseline_in_scope,
    find_european_price_list_url,
    find_price_list_url,
    is_not_found,
    parse_index_prices,
    parse_layout_count,
    parse_price_list_pages,
    pop_up_roof_is_standard,
    reconciles,
)
from src.product_model.enums import BodyType
from src.product_model.model import Motorhome

FIXTURES = Path(__file__).parent / "fixtures"

#: The roster each range page and each price list independently claims, from the survey.
#: This is the manufacturer's own public count and the number a silently-dropped layout
#: would break.
EXPECTED_ROSTER: dict[str, tuple[str, ...]] = {
    "CaraCore": ("650 MF", "650 MEG", "700 MEG"),
    "CaraHome": ("600 DKG", "650 DG", "650 MEG"),
    "CaraSuite EDITION [SPICY]": ("650 MF", "650 MG", "650 MEG", "700 MEG", "700 DX"),
    "CaraCompact EDITION [PEPPER]": ("580 MEG", "600 MF", "600 MEG"),
    "CaraBus EDITION [FIRE]": (
        "540 MQ", "600 MQ", "600 ME", "600 DQ", "600 MQH", "630 ME", "630 MEG",
    ),
    "CaraBus GREY EDITION [FIRE]": (
        "540 MQ", "600 MQ", "600 ME", "600 DQ", "600 MQH", "630 ME", "630 MEG",
    ),
    "X-PEDITION": ("600 MQ",),
}

#: 14 motorhomes + 15 campervans. The number to compare a real run against.
EXPECTED_PRODUCT_COUNT = 29


def _html(name: str) -> str:
    return (FIXTURES / f"weinsberg_{name}.html").read_text(encoding="utf-8")


def _pages(name: str) -> list[str]:
    raw = (FIXTURES / f"weinsberg_{name}_price_list_pages.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _price_list(name: str, url: str = "https://example.invalid/list.pdf"):
    return parse_price_list_pages(_pages(name), url)


def _spec(title: str) -> RangeSpec:
    return next(spec for spec in RANGES if spec.pdf_title == title)


# --------------------------------------------------------------------------------------
# Numbers: the German thousands separator
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3.500", 3500),
        ("88.995,-", 88995),
        ("699", 699),
        ("2.930", 2930),
        ("102.490", 102490),
        (None, None),
        ("–", None),
    ],
)
def test_thousands_reads_the_german_separator(raw: str | None, expected: int | None) -> None:
    assert _thousands(raw) == expected


def test_thousands_never_treats_the_dot_as_a_decimal_point() -> None:
    """`3.500` is 3500 kg, not 3.5 kg — nothing downstream bounds a mass."""
    assert _thousands("3.500") == 3500
    assert _thousands("3.500") != 3


def test_centimetres_become_millimetres() -> None:
    assert _centimetres_to_mm("699") == 6990
    assert _centimetres_to_mm(232) == 2320
    assert _centimetres_to_mm(None) is None


# --------------------------------------------------------------------------------------
# The roster, and the row guard that makes reading order safe
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["spicy", "carahome", "fire"])
def test_price_list_yields_exactly_its_published_roster(name: str) -> None:
    price_list = _price_list(name)
    titles = {title for title, _code in price_list.rows}
    for title in titles:
        codes = tuple(
            code for held_title, code in price_list.rows if held_title == title
        )
        assert codes == EXPECTED_ROSTER[title], title


def test_five_column_range_still_yields_its_wrapped_mtplm_row() -> None:
    """CaraSuite's five columns wrap `Technically maximum authorised laden mass (kg)`.

    The label is split across two lines in the PDF, so a parser anchored on a single line
    loses MTPLM on this range **only** — a first verification pass did exactly that, and
    every other range looked fine. Collapsing the page's whitespace is what fixes it.
    """
    price_list = _price_list("spicy")
    for code in EXPECTED_ROSTER["CaraSuite EDITION [SPICY]"]:
        row = price_list.rows[("CaraSuite EDITION [SPICY]", code)]
        assert row.mtplm_kilograms == 3500, code


def test_a_short_row_is_rejected_rather_than_sliced() -> None:
    """CaraHome prints `Lap seat belts against driving direction 2 2` for THREE models.

    The row is genuinely short in Weinsberg's own document, and coordinates cannot say
    which two layouts it belongs to — pypdf places most runs on that page at (0, 0). So it
    must be refused, not padded: slicing would let it swallow the next row's label and
    report a value for a layout that has none.

    Lap belts are excluded from the seat count by rule anyway (README, "Count three-point
    belts only"), so nothing depends on this row's values. It is kept as the test case
    because it is the only genuinely short row in any of these documents, and the guard it
    exercises protects every other row on the page.
    """
    page = next(
        text for text in _pages("carahome") if "Lap seat belts" in " ".join(text.split())
    )
    collapsed = " ".join(page.split())
    assert "Lap seat belts against driving direction 2 2" in collapsed
    assert _row_values(collapsed, "Lap seat belts against driving direction", 3) is None
    # ...while the full-width row beside it reads fine.
    assert _row_values(collapsed, "Three-point belts in driving direction", 3) == ["2", "2", "2"]


def test_a_row_longer_than_the_roster_is_also_rejected() -> None:
    assert _row_values("Beds (Hints: H141) 2 3 2 5", "Beds (Hints: H141)", 3) is None
    assert _row_values("Beds (Hints: H141) 2 3 2 5", "Beds (Hints: H141)", 4) == [
        "2", "3", "2", "5",
    ]


def test_chassis_capture_stops_before_the_engine_power_label() -> None:
    """`Chassis FIAT FIAT FIAT Engine power ...` — the `E` must not become a value.

    Anchoring on runs of two-or-more capitals is what keeps the count right; a single-letter
    class would take `Engine`'s `E` and silently push the row over its roster length.
    """
    text = "BASIC EQUIPMENT Chassis FIAT FIAT FIAT Engine power 103 kW / 140 PS"
    assert _chassis_values(text, 3) == ["FIAT", "FIAT", "FIAT"]
    assert _chassis_values("Chassis MERCEDES Engine power 110 kW / 150 PS", 1) == ["MERCEDES"]


def test_price_row_needs_its_own_parser_because_of_the_comma_dash_suffix() -> None:
    """`88.995,-` is not a bare number: a numeric capture stops dead at the comma."""
    text = "List price in GBP including 20% VAT 88.995,- 89.985,- 92.485,- FIAT Ducato"
    assert _price_values(text, 3) == ["88.995,-", "89.985,-", "92.485,-"]
    # The generic numeric reader sees one value where there are three, and refuses.
    assert _row_values(text, "List price in GBP including 20% VAT", 3) is None


# --------------------------------------------------------------------------------------
# The duplicated mass in running order
# --------------------------------------------------------------------------------------


def test_mass_in_running_order_is_printed_twice_on_every_range() -> None:
    """The requester's flagged trap: all 29 products print this row twice."""
    for name in ("spicy", "carahome", "fire"):
        for text in _pages(name):
            collapsed = " ".join(text.split())
            if "Mass in running order" not in collapsed:
                continue
            header_models = collapsed.count("Technical Data")
            assert header_models  # the page states its roster
            assert collapsed.count("Mass in running order") == 2, name


def test_the_first_of_the_two_masses_is_recorded_and_both_are_kept() -> None:
    """CaraCore's two rows differ by 12 kg; CaraBus FIRE's by 3 kg, the other way."""
    fire = _price_list("fire").rows[("CaraBus EDITION [FIRE]", "540 MQ")]
    assert fire.mro_published == (2675, 2672)
    assert fire.mro_kilograms == 2675, "the first figure is the recorded one"


def test_identical_duplicate_masses_are_still_both_carried() -> None:
    """CaraHome prints the same figure twice, which is the requester's screenshot."""
    row = _price_list("carahome").rows[("CaraHome", "600 DKG")]
    assert row.mro_published == (2858, 2858)
    assert row.mro_kilograms == 2858


def test_mass_cells_wrapped_mid_value_are_rejoined() -> None:
    """The PDF splits `2.930 (2.783` / `- 3.076)` across two lines."""
    raw = "Mass in running order (kg) (Hints: H140)\n2.930 (2.783\n- 3.076)\nTechnically"
    rows = _mass_rows(" ".join(raw.split()), 1)
    assert rows == [[(2930, 2783, 3076)]]


def test_mass_run_stops_at_a_gap_rather_than_reaching_forward() -> None:
    """Only contiguous band triples belong to the row; a later stray figure must not join."""
    text = "Mass in running order (kg) 2.930 (2.783 - 3.076) something else 9.999 (1 - 2)"
    assert _mass_rows(text, 2) == []
    assert _mass_rows(text, 1) == [[(2930, 2783, 3076)]]


# --------------------------------------------------------------------------------------
# The self-check
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["spicy", "carahome", "fire", "xpedition_european"])
def test_every_fixture_layout_reconciles(name: str) -> None:
    """The ±5% band held on all 28 UK layouts and on X-PEDITION in the survey."""
    rows = [row for row in _price_list(name).rows.values() if row.mro_kilograms is not None]
    assert rows
    for row in rows:
        assert reconciles(row), f"{name} {row.layout_code} {row.mro_kilograms} {row.mro_band}"


def test_a_misread_mass_fails_the_tolerance_band() -> None:
    """A swapped column is the realistic failure on a columnar page read in reading order."""
    good = _price_list("carahome").rows[("CaraHome", "600 DKG")]
    assert reconciles(good)
    assert not reconciles(replace(good, mro_kilograms=2500))


def test_a_missing_band_is_not_a_reason_to_drop_a_vehicle() -> None:
    row = PriceListRow(layout_code="600 DKG", mro_kilograms=2858, mro_band=None)
    assert reconciles(row)


def test_rounding_inside_a_kilogram_still_reconciles() -> None:
    row = PriceListRow(layout_code="x", mro_kilograms=2858, mro_band=(2715, 3000))
    assert reconciles(row)
    assert not reconciles(replace(row, mro_band=(2713, 3000)))


# --------------------------------------------------------------------------------------
# Currency: the downloads page's mislabelled "Price list, UK"
# --------------------------------------------------------------------------------------


def test_the_european_document_is_recognised_as_euro_priced_and_yields_no_price() -> None:
    """The single most valuable test here.

    `/en-uk/support/catalogues-price-lists/` labels these documents **"Price list, UK"**
    and they quote `List price in EUR including 19% VAT` — the word GBP appears nowhere in
    them. Reading the card would have put euro figures into `rrp_pounds` on every layout
    while sterling sat two clicks away on the range pages.
    """
    price_list = _price_list("xpedition_european")
    assert "X-PEDITION" in price_list.priced_in_euros
    row = price_list.rows[("X-PEDITION", "600 MQ")]
    assert row.rrp_pounds is None, "a euro figure must never reach rrp_pounds"
    # ...but the specification, which is currency-free, is read in full.
    assert (row.mro_kilograms, row.mtplm_kilograms) == (2835, 3500)
    assert (row.mh_length_mm, row.mh_width_mm, row.mh_height_mm) == (5940, 2060, 2830)
    assert row.base_vehicle_manufacturer == "Mercedes"


def test_the_uk_documents_are_not_flagged_as_euro_priced() -> None:
    for name in ("spicy", "carahome", "fire"):
        assert _price_list(name).priced_in_euros == set(), name


def test_uk_price_list_prices_are_sterling_and_plausible() -> None:
    prices = {
        code: row.rrp_pounds
        for (_title, code), row in _price_list("fire").rows.items()
    }
    assert prices["540 MQ"] == 63494
    assert all(60_000 < value < 120_000 for value in prices.values() if value)


# --------------------------------------------------------------------------------------
# Multi-range documents
# --------------------------------------------------------------------------------------


def test_rows_are_keyed_on_range_and_layout_together() -> None:
    """`600 MQ` exists in five Weinsberg ranges, and the European document holds several.

    Keying on the layout code alone would let one range's figures stand for all of them.
    """
    price_list = _price_list("xpedition_european")
    titles = {title for title, _code in price_list.rows}
    assert {"CaraBus", "X-PEDITION"} <= titles
    assert price_list.rows[("X-PEDITION", "600 MQ")].mro_kilograms == 2835
    assert price_list.rows[("CaraBus", "600 MQ")].mro_kilograms != 2835


def test_a_range_title_wrapped_across_lines_is_rejoined() -> None:
    """The PDF breaks the title mid-phrase, and differently in each document.

    `CaraBus EDITION [FIRE]` + `(2027)` on two lines in the FIRE list;
    `CaraBus GREY EDITION` + `[FIRE] (2027)` in the GREY one. Collapsing the page's
    whitespace before matching is what makes both read the same.
    """
    page = _pages("fire")[0]
    assert "CaraBus EDITION [FIRE]\n(2027)" in page, "the fixture really is wrapped"
    assert {title for title, _code in _price_list("fire").rows} == {"CaraBus EDITION [FIRE]"}

    wrapped_the_other_way = (
        "CaraBus GREY EDITION\n[FIRE] (2027)\nTechnical Data 540 MQ\nBeds (Hints: H141) 2\n"
    )
    titles = {title for title, _code in parse_price_list_pages([wrapped_the_other_way], "u").rows}
    assert titles == {"CaraBus GREY EDITION [FIRE]"}


def test_a_page_with_no_range_title_or_roster_contributes_nothing() -> None:
    assert parse_price_list_pages(["just some legal preamble, 3.500 kg"], "u").rows == {}


def test_a_campervan_ranges_two_roster_pages_merge_into_one_row_set() -> None:
    """CaraBus splits seven layouts 4+3, with the masses on one page and the seats on the next."""
    price_list = _price_list("fire")
    row = price_list.rows[("CaraBus EDITION [FIRE]", "600 MQH")]
    assert row.mro_kilograms == 2935, "from the second roster page"
    assert row.mh_passenger_seats_inc_driver == 2, "from the page after that"
    assert row.mh_height_mm == 3120


# --------------------------------------------------------------------------------------
# Berths and seats
# --------------------------------------------------------------------------------------


def test_berths_take_beds_not_max_number_of_beds() -> None:
    """They differ on 12 of 29 products; the CaraBus 540 MQ's extra two are the pop-up roof."""
    row = _price_list("fire").rows[("CaraBus EDITION [FIRE]", "540 MQ")]
    assert (row.berths, row.max_berths) == (2, 4)


def test_seats_take_the_standard_belt_count_not_the_fitment_ceiling() -> None:
    """CaraHome 600 DKG: 2 belted travel seats as standard, against a stated ceiling of 6."""
    row = _price_list("carahome").rows[("CaraHome", "600 DKG")]
    assert (row.mh_passenger_seats_inc_driver, row.max_belted_seats) == (2, 6)


def test_the_belt_row_reads_two_on_every_fixture_layout() -> None:
    """Recorded because it is the caveat: the row has no variance of its own here.

    Knaus's equivalent read 4 on two layouts, which corroborated it per layout. If this
    ever stops being uniformly 2, that is new evidence and this test should be updated
    deliberately rather than relaxed.
    """
    for name in ("spicy", "carahome", "fire"):
        for row in _price_list(name).rows.values():
            if row.mh_passenger_seats_inc_driver is not None:
                assert row.mh_passenger_seats_inc_driver == 2, f"{name} {row.layout_code}"


# --------------------------------------------------------------------------------------
# Payload
# --------------------------------------------------------------------------------------


def test_payload_is_derived_from_the_two_masses() -> None:
    row = _price_list("carahome").rows[("CaraHome", "600 DKG")]
    assert row.mh_payload_kilograms == 3500 - 2858 == 642


def test_the_documents_own_maximum_payload_is_never_read() -> None:
    """It reconciles with nothing and differs between the UK and euro editions.

    CaraHome prints `63 22 170` in sterling and `85 50 200` in euros for the same three
    layouts — a figure that changes with the market it is priced in is not a property of
    the vehicle.
    """
    uk = " ".join(" ".join(text.split()) for text in _pages("carahome"))
    assert "Maximum payload (kg) 63 22 170" in uk, "the row is present in the document"
    derived = [
        row.mh_payload_kilograms for row in _price_list("carahome").rows.values()
    ]
    assert derived == [642, 612, 602]
    assert 63 not in derived and 22 not in derived and 170 not in derived


# --------------------------------------------------------------------------------------
# Body type and the pop-up roof
# --------------------------------------------------------------------------------------


def test_the_pop_up_roof_is_optional_or_impossible_and_standard_on_no_layout() -> None:
    """The basis for every campervan's body type, checked every run rather than assumed."""
    assert pop_up_roof_is_standard(_pages("fire")) is False


def test_a_roof_marked_standard_anywhere_is_reported_as_such() -> None:
    page = (
        "CaraBus EDITION [FIRE] (2027) Features and Options "
        "103594-01 WEINSBERG pop-up roof KOMFORT, white (Hints: H151) 163 5.516,- s o o - - o -"
    )
    assert pop_up_roof_is_standard([page]) is True


def test_an_unreadable_roof_row_is_unknown_rather_than_assumed_optional() -> None:
    """`None`, not `False` — the difference decides whether body type is asserted."""
    assert pop_up_roof_is_standard(["nothing about roofs here"]) is None


def test_the_bed_size_and_hint_mentions_of_the_roof_are_not_mistaken_for_markings() -> None:
    """`Bed dimensions pop-up roof (cm)` and hint H135 carry no s/o/– markings at all."""
    assert pop_up_roof_is_standard(
        ["Bed dimensions pop-up roof (cm) (Hints: H192) 135 x 200 135 x 200 – Single bed – s"]
    ) is None
    assert pop_up_roof_is_standard(
        ["H135 Awning size differs for technical reasons when choosing the pop-up roof"]
    ) is None


def test_campervans_are_high_tops_when_the_roof_is_not_standard() -> None:
    spec = _spec("CaraBus EDITION [FIRE]")
    row = _price_list("fire").rows[("CaraBus EDITION [FIRE]", "540 MQ")]
    assert row.mh_height_mm == 2580 > HIGH_TOP_ABOVE_MM
    assert _body_type(spec, row, roof_standard=False) is BodyType.CAMPERVAN_HIGH_TOP


def test_a_campervan_gets_no_body_type_when_the_roof_may_be_standard() -> None:
    """An elevating roof fitted as standard changes what the vehicle is, so a reviewer decides."""
    spec = _spec("CaraBus EDITION [FIRE]")
    row = _price_list("fire").rows[("CaraBus EDITION [FIRE]", "540 MQ")]
    assert _body_type(spec, row, roof_standard=True) is None
    assert _body_type(spec, row, roof_standard=None) is None


def test_a_campervan_of_unknown_height_gets_no_body_type() -> None:
    spec = _spec("CaraBus EDITION [FIRE]")
    row = PriceListRow(layout_code="540 MQ", mh_height_mm=None)
    assert _body_type(spec, row, roof_standard=False) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("CaraCore", BodyType.A_CLASS),
        ("CaraHome", BodyType.COACH_BUILT_OVER_CAB_BED),
        ("CaraSuite EDITION [SPICY]", BodyType.COACH_BUILT_LOW_PROFILE),
        ("CaraCompact EDITION [PEPPER]", BodyType.COACH_BUILT_LOW_PROFILE),
    ],
)
def test_motorhome_body_types_come_from_weinsbergs_own_category_pages(
    title: str, expected: BodyType
) -> None:
    """Validated against all 34 current FMLV rows before adoption — 34 of 34 agree."""
    row = PriceListRow(layout_code="x", mh_height_mm=2790)
    assert _body_type(_spec(title), row, roof_standard=None) is expected


# --------------------------------------------------------------------------------------
# Discovery, and the 404 that returns HTTP 200
# --------------------------------------------------------------------------------------


def test_price_list_url_is_found_on_a_range_page() -> None:
    url = find_price_list_url(_html("caracore_range_page"))
    assert url is not None
    assert url.startswith("https://konfigurator.knaustabbert.de/rest/1/downloadPriceList/")


def test_the_404_page_is_detected_despite_its_http_200() -> None:
    """`/en-uk/motorhomes/caracore/layouts/650-meg/` is a real URL that 200s and is a 404.

    The UK site publishes no per-layout page at all. Anything reading the status code alone
    would treat this as a successful fetch of an empty specification.
    """
    assert is_not_found(_html("404_page"))
    assert not is_not_found(_html("caracore_range_page"))


def test_no_price_list_link_on_the_404_page() -> None:
    assert find_price_list_url(_html("404_page")) is None


def test_the_range_page_publishes_its_own_layout_count() -> None:
    assert parse_layout_count(_html("caracore_range_page")) == 3


def test_the_european_price_list_is_matched_on_its_path_not_its_dated_filename() -> None:
    url = find_european_price_list_url(_html("downloads_page"), "camper-van")
    assert url is not None
    assert "/preislisten/camper-van/" in url
    assert url.endswith(".pdf")


def test_the_glossy_catalogue_and_the_caravan_list_are_not_matched() -> None:
    """The downloads page holds six documents; only one of them is the campervan price list."""
    url = find_european_price_list_url(_html("downloads_page"), "camper-van")
    assert url is not None
    assert "/katalog/" not in url, "the glossy catalogue carries no spec table"
    assert "wohnwagen" not in url, "caravans are out of scope for the whole prototype"


def test_the_motorhome_segment_resolves_to_a_different_document() -> None:
    campervans = find_european_price_list_url(_html("downloads_page"), "camper-van")
    motorhomes = find_european_price_list_url(_html("downloads_page"), "wohnmobile")
    assert motorhomes is not None
    assert motorhomes != campervans


# --------------------------------------------------------------------------------------
# The index card, which is X-PEDITION's only sterling price
# --------------------------------------------------------------------------------------


def test_the_campervan_index_gives_x_pedition_its_sterling_price() -> None:
    prices = parse_index_prices(_html("campervan_index"))
    assert prices["X-PEDITION"] == 102490


def test_the_index_also_prices_the_ranges_that_have_their_own_lists() -> None:
    prices = parse_index_prices(_html("campervan_index"))
    assert prices["CaraBus EDITION [FIRE]"] == 63494
    assert prices["CaraBus GREY EDITION [FIRE]"] == 63494


def test_the_index_cards_link_nothing_so_it_cannot_be_used_as_a_roster() -> None:
    """Three of the four campervan cards are `<div>`s with no href — the reason `RANGES`
    is an explicit list and both EDITION [FIRE] slugs came from the German sitemap."""
    html = _html("campervan_index")
    for slug in ("edition-fire", "grey-edition-fire", "x-pedition"):
        assert f'href="/en-uk/camper-vans/{slug}/"' not in html


# --------------------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------------------


def test_manufacturer_matches_the_registry_join_key() -> None:
    """Not `Knaus Tabbert AG Weinsberg` — both strings are live in FMLV, and every
    current-model-year row carries this one. See `docs/adapters/weinsberg.md`."""
    assert MANUFACTURER == "Knaus Tabbert AG"
    assert MANUFACTURER_DISPLAY_NAME == "Weinsberg"


def test_default_ranges_cover_every_declared_range_with_unique_labels() -> None:
    labels = [label for _slug, label in DEFAULT_RANGES]
    assert len(labels) == len(set(labels)), "cli.resolve_ranges keys on the label"
    assert set(labels) == {spec.pdf_title for spec in RANGES} == set(EXPECTED_ROSTER)


def test_the_declared_rosters_sum_to_the_published_product_count() -> None:
    assert sum(len(codes) for codes in EXPECTED_ROSTER.values()) == EXPECTED_PRODUCT_COUNT


@pytest.mark.parametrize(
    ("title", "layout_code", "expected_range", "expected_model"),
    [
        ("CaraCore", "650 MF", "CaraCore", "650 MF"),
        ("CaraHome", "600 DKG", "CaraHome", "600 DKG"),
        # SPICY is deliberately NOT suffixed: FMLV holds all five CaraSuite rows bare.
        ("CaraSuite EDITION [SPICY]", "650 MF", "CaraSuite", "650 MF"),
        ("CaraCompact EDITION [PEPPER]", "600 MF", "CaraCompact", "600 MF Edition PEPPER"),
        ("CaraBus EDITION [FIRE]", "540 MQ", "CaraBus", "540 MQ Edition FIRE"),
        ("CaraBus GREY EDITION [FIRE]", "540 MQ", "CaraBus", "540 MQ GREY Edition FIRE"),
        ("X-PEDITION", "600 MQ", "X-Pedition", "600 MQ"),
    ],
)
def test_identity_is_emitted_as_fmlv_holds_it_not_as_the_price_list_prints_it(
    title: str, layout_code: str, expected_range: str, expected_model: str
) -> None:
    """Every one of these matched a real baseline row at exactly 1.000 in the first run."""
    spec = _spec(title)
    assert spec.fmlv_range == expected_range
    assert spec.fmlv_model(layout_code) == expected_model


# --------------------------------------------------------------------------------------
# Baseline scope for a --range-narrowed run
# --------------------------------------------------------------------------------------


def _baseline(manufacturer_range: str, model: str) -> Motorhome:
    return Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=manufacturer_range,
        model=model,
    )


def test_baseline_scope_matches_the_fmlv_range_not_the_selector() -> None:
    """The selector is `CaraSuite EDITION [SPICY]`; FMLV's range column says `CaraSuite`.

    The default scope compares the selector against `manufacturer_range`, which would find
    no baseline row at all and propose every layout as new — Wingamm's documented failure.
    """
    assert baseline_in_scope(_baseline("CaraSuite", "650 MF"), {"CaraSuite EDITION [SPICY]"})
    assert not baseline_in_scope(_baseline("CaraSuite", "650 MF"), {"CaraCore"})


def test_the_longest_matching_suffix_wins_so_grey_stays_with_grey() -> None:
    """Both CaraBus selectors share the FMLV range *and* the ` Edition FIRE` suffix ending.

    Without the longest-suffix rule the plain FIRE selector would claim the GREY rows too,
    and a narrowed GREY run would report seven live products as disappeared.
    """
    grey = _baseline("CaraBus", "540 MQ GREY Edition FIRE")
    plain = _baseline("CaraBus", "540 MQ Edition FIRE")

    assert baseline_in_scope(grey, {"CaraBus GREY EDITION [FIRE]"})
    assert not baseline_in_scope(grey, {"CaraBus EDITION [FIRE]"})
    assert baseline_in_scope(plain, {"CaraBus EDITION [FIRE]"})
    assert not baseline_in_scope(plain, {"CaraBus GREY EDITION [FIRE]"})


def test_a_row_with_no_edition_suffix_still_falls_in_scope_of_its_range() -> None:
    """FMLV's 2026 plain `CaraBus 540 MQ` must be reachable, so it can be reported gone."""
    assert baseline_in_scope(_baseline("CaraBus", "540 MQ"), {"CaraBus EDITION [FIRE]"})
    assert not baseline_in_scope(_baseline("CaraBus", "540 MQ"), {"CaraBus GREY EDITION [FIRE]"})


def test_the_withdrawn_mercedes_caracompact_rows_are_in_scope() -> None:
    """All three spellings FMLV holds of the one Mercedes vehicle, so all three can be
    reported as disappeared rather than going unnoticed."""
    assert baseline_in_scope(
        _baseline("CaraCompact", "640 MEG MB Edition PEPPER"),
        {"CaraCompact EDITION [PEPPER]"},
    )
    # The two rows filed under their own range spellings are genuinely out of this
    # selector's reach, which is why the survey lists them for the requester by hand.
    assert not baseline_in_scope(
        _baseline("CaraCompact MB", "640 MEG Edition PEPPER"),
        {"CaraCompact EDITION [PEPPER]"},
    )


def test_baseline_scope_ignores_a_row_with_no_range() -> None:
    assert not baseline_in_scope(_baseline(None, "650 MF"), {"CaraCore"})  # type: ignore[arg-type]


def test_baseline_scope_does_not_leak_across_ranges_sharing_a_layout_code() -> None:
    """`650 MEG` exists in CaraCore, CaraHome and CaraSuite."""
    assert not baseline_in_scope(_baseline("CaraHome", "650 MEG"), {"CaraCore"})
    assert baseline_in_scope(_baseline("CaraHome", "650 MEG"), {"CaraHome"})


# --------------------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------------------


def _extracted(title: str, layout_code: str, name: str):
    spec = _spec(title)
    row = _price_list(name).rows[(title, layout_code)]
    return _build_extracted_motorhome(
        spec,
        row,
        price_list_url="https://example.invalid/list.pdf",
        identity_url="https://example.invalid/range/",
        price_url="https://example.invalid/list.pdf",
        price_note="price note",
        roof_standard=False,
    )


def test_every_value_set_on_the_model_is_registered_in_provenance() -> None:
    """An unregistered field is never compared, never confirmed, and blank on a new
    product — the failure `docs/adapters/README.md` calls the hardest to notice."""
    for title, code, name in (
        ("CaraHome", "600 DKG", "carahome"),
        ("CaraBus EDITION [FIRE]", "540 MQ", "fire"),
        ("CaraSuite EDITION [SPICY]", "700 DX", "spicy"),
    ):
        extracted = _extracted(title, code, name)
        for field_name in (
            "manufacturer_range", "model", "base_vehicle_manufacturer", "rrp_pounds",
            "mro_kilograms", "mtplm_kilograms", "mh_payload_kilograms", "mh_length_mm",
            "mh_width_mm", "mh_height_mm", "berths", "mh_passenger_seats_inc_driver",
            "body_type",
        ):
            assert getattr(extracted.motorhome, field_name) is not None, (title, code, field_name)
            assert field_name in extracted.provenance, (title, code, field_name)


def test_body_type_is_registered_even_when_it_could_not_be_settled() -> None:
    """"I know what this is, but not which one" — the family is certain, the value is not."""
    spec = _spec("CaraBus EDITION [FIRE]")
    row = _price_list("fire").rows[("CaraBus EDITION [FIRE]", "540 MQ")]
    extracted = _build_extracted_motorhome(
        spec,
        row,
        price_list_url="u",
        identity_url="https://example.invalid/range/",
        price_url="u",
        price_note="n",
        roof_standard=None,
    )
    assert extracted.motorhome.body_type is None
    assert "body_type" in extracted.provenance
    assert "certainly a campervan" in extracted.provenance["body_type"].snippet


def test_range_and_model_provenance_say_they_move_together() -> None:
    extracted = _extracted("CaraBus EDITION [FIRE]", "540 MQ", "fire")
    for field_name in ("manufacturer_range", "model"):
        assert "both together" in extracted.provenance[field_name].snippet or (
            "Paired with the range above" in extracted.provenance[field_name].snippet
        )


def test_mass_provenance_shows_the_figure_that_was_discarded() -> None:
    extracted = _extracted("CaraBus EDITION [FIRE]", "540 MQ", "fire")
    snippet = extracted.provenance["mro_kilograms"].snippet
    assert "2675 kg / 2672 kg" in snippet
    assert "twice" in snippet


def test_seat_provenance_names_the_row_it_used_and_the_rows_it_refused() -> None:
    extracted = _extracted("CaraHome", "600 DKG", "carahome")
    snippet = extracted.provenance["mh_passenger_seats_inc_driver"].snippet
    assert "Three-point belts in driving direction" in snippet
    assert "Number of persons allowed in driving operation' is NOT this field" in snippet
    assert "Lap seat belts" in snippet, "the refused row must reach the reviewer"
    assert "not a safe adult travel seat" in snippet, (
        "the reviewer needs the reason the lap-belt row is refused, not just that it was"
    )
    assert "open question" not in snippet, "settled by the requester 3 September 2026"


def test_payload_provenance_says_it_is_derived_and_why() -> None:
    snippet = _extracted("CaraHome", "600 DKG", "carahome").provenance[
        "mh_payload_kilograms"
    ].snippet
    assert "derived" in snippet
    assert "Maximum payload" in snippet


def test_the_downloads_url_is_the_page_a_customer_sees() -> None:
    assert DOWNLOADS_URL.startswith("https://weinsberg.com/en-uk/support/")
