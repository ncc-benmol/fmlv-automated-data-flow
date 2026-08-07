"""Tests for the Sunlight adapter's pure parsing functions, against real page runs.

The fixtures are the text runs `pypdf` reports for four real "Prices and technical
data" pages of Sunlight's UK price lists (model year 2027) — see
`docs/adapters/sunlight.md`. Runs rather than lines, because that is what the adapter
parses: every table cell is its own run, which is the only thing that distinguishes
`CLIFF 540 V` from `CLIFF 540` followed by a stray `V`.

The four were picked to cover what varies between pages: three models with mixed berth
notation, four on a different chassis with optional seating, five in one table, and a
single-model page whose model name contains a space.

No network and no PDF parsing here; `fetch.pdf` is covered in `tests/fetch/test_pdf.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.adapters.sunlight import (
    SunlightProduct,
    _reconciles,
    find_price_list_urls,
    parse_technical_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _runs(stem: str) -> list[str]:
    return json.loads((FIXTURES / f"{stem}.json").read_text(encoding="utf-8"))


VAN_ADVENTURE = _runs("sunlight_p4_van_adventure_runs")
LOW_PROFILE_UNLTD = _runs("sunlight_p24_low_profile_unltd_runs")
CLIFF_ADVENTURE = _runs("sunlight_p4_cliff_adventure_runs")
CLIFF_VANLIFE = _runs("sunlight_p25_cliff_vanlife_runs")


# --------------------------------------------------------------------------- #
# Reading a table
# --------------------------------------------------------------------------- #


def test_range_and_every_layout_are_read_from_the_table_head() -> None:
    products = parse_technical_page(VAN_ADVENTURE, page_number=4)

    assert [product.model for product in products] == ["V 60", "V 66", "V 67S"]
    assert {product.range_label for product in products} == {"Van Adventure"}


def test_every_column_of_a_row_lands_on_its_own_layout() -> None:
    v60, v66, v67s = parse_technical_page(VAN_ADVENTURE, page_number=4)

    assert (v60.rrp_pounds, v66.rrp_pounds, v67s.rrp_pounds) == (59090, 61690, 62590)
    assert (v60.mro_kilograms, v66.mro_kilograms, v67s.mro_kilograms) == (2657, 2719, 2804)
    assert (v60.mh_length_mm, v66.mh_length_mm, v67s.mh_length_mm) == (5960, 6660, 6980)


def test_a_model_name_containing_a_space_survives() -> None:
    """The reason this adapter parses runs rather than lines.

    Sunlight sells both a `CLIFF 540` (in CLIFF Adventure) and a `CLIFF 540 V` (in
    CLIFF Vanlife). Joined into a line, the second is indistinguishable from the first
    followed by a stray `V` — and reading it as `CLIFF 540` would collide with a real,
    different product.
    """
    (vanlife,) = parse_technical_page(CLIFF_VANLIFE, page_number=25)

    assert vanlife.model == "CLIFF 540 V"
    assert vanlife.range_label == "CLIFF Vanlife"
    assert vanlife.rrp_pounds == 63690


def test_the_same_model_name_in_two_ranges_stays_two_products() -> None:
    # CLIFF 600 is sold in both CLIFF Adventure and CLIFF X, on different weights and
    # prices — so a product's identity has to include its range.
    adventure = {p.model: p for p in parse_technical_page(CLIFF_ADVENTURE, page_number=4)}

    assert adventure["CLIFF 600"].rrp_pounds == 56990
    assert adventure["CLIFF 600"].mro_kilograms == 2825
    assert len(adventure) == 5


# --------------------------------------------------------------------------- #
# Field-level conversions
# --------------------------------------------------------------------------- #


def test_dimensions_are_split_and_converted_from_centimetres() -> None:
    # Sunlight publishes all three axes in one cell, in cm: "596 / 214 / 274".
    v60 = parse_technical_page(VAN_ADVENTURE, page_number=4)[0]

    assert (v60.mh_length_mm, v60.mh_width_mm, v60.mh_height_mm) == (5960, 2140, 2740)


def test_an_optional_extra_berth_is_not_counted_as_standard() -> None:
    """`2 - 3 OPT` means two berths, with a third only via optional equipment.

    The standard figure is the one recorded, but the cell's own wording is kept for the
    reviewer, since the single number cannot express the "OPT" part.
    """
    v60, v66, _v67s = parse_technical_page(VAN_ADVENTURE, page_number=4)

    assert (v60.berths, v60.berths_text) == (2, "2 - 3 OPT")
    assert (v66.berths, v66.berths_text) == (2, "2")


def test_optional_seating_is_treated_the_same_way() -> None:
    products = parse_technical_page(LOW_PROFILE_UNLTD, page_number=24)
    first, second = products[0], products[1]

    assert (first.mh_passenger_seats_inc_driver, first.seats_text) == (4, "4")
    assert (second.mh_passenger_seats_inc_driver, second.seats_text) == (3, "3 - 4 OPT")


def test_price_is_read_in_sterling_without_conversion() -> None:
    # Sunlight is German but publishes a UK & Ireland list quoting "Price £" — so
    # unlike Morelo there is no exchange rate involved anywhere.
    products = parse_technical_page(LOW_PROFILE_UNLTD, page_number=24)

    assert [product.rrp_pounds for product in products] == [71490, 72990, 73690, 73690]


def test_base_vehicle_manufacturer_comes_from_the_chassis_row() -> None:
    # The UNLTD range is the one built on Ford rather than Fiat.
    products = parse_technical_page(LOW_PROFILE_UNLTD, page_number=24)

    assert {product.base_vehicle_manufacturer for product in products} == {"Ford"}
    assert {p.base_vehicle_manufacturer for p in parse_technical_page(VAN_ADVENTURE, 4)} == {
        "Fiat"
    }


def test_payload_is_derived_from_the_two_published_masses() -> None:
    # Sunlight states no payload figure, so it is computed — and must not be confused
    # with its "manufacturer-specified mass for optional equipment", a different thing.
    v60 = parse_technical_page(VAN_ADVENTURE, page_number=4)[0]

    assert (v60.mtplm_kilograms, v60.mro_kilograms) == (3500, 2657)
    assert v60.mh_payload_kilograms == 843


def test_payload_is_none_when_a_mass_is_missing() -> None:
    assert SunlightProduct(
        range_label="Van Adventure", model="V 60", page_number=4, mtplm_kilograms=3500
    ).mh_payload_kilograms is None


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def test_every_real_layout_agrees_with_its_own_tolerance_band() -> None:
    products = [
        product
        for runs, page in (
            (VAN_ADVENTURE, 4),
            (LOW_PROFILE_UNLTD, 24),
            (CLIFF_ADVENTURE, 4),
            (CLIFF_VANLIFE, 25),
        )
        for product in parse_technical_page(runs, page_number=page)
    ]

    assert len(products) == 13
    assert [p.model for p in products if not _reconciles(p)] == []


def test_a_mass_paired_with_another_layouts_band_is_rejected() -> None:
    # What a slipped column looks like: V 60's mass against V 67S's ±5% band.
    misread = SunlightProduct(
        range_label="Van Adventure",
        model="V 60",
        page_number=4,
        mro_kilograms=2657,
        mro_band=(2664, 2944),
    )

    assert _reconciles(misread) is False


def test_rounding_in_the_published_band_is_tolerated() -> None:
    # 2657 x 0.95 = 2524.15 and x 1.05 = 2789.85; Sunlight prints whole kilograms.
    rounded = SunlightProduct(
        range_label="Van Adventure",
        model="V 60",
        page_number=4,
        mro_kilograms=2657,
        mro_band=(2524, 2790),
    )

    assert _reconciles(rounded) is True


def test_a_layout_with_no_band_is_not_treated_as_contradictory() -> None:
    assert _reconciles(
        SunlightProduct(range_label="VW IBEX", model="604D", page_number=35)
    ) is True


# --------------------------------------------------------------------------- #
# Rows and pages that should not produce products
# --------------------------------------------------------------------------- #


def test_a_page_without_the_table_marker_yields_nothing() -> None:
    assert parse_technical_page(["Footnotes", "1) Before driving"], page_number=52) == []


def test_a_row_with_the_wrong_number_of_cells_is_dropped_not_guessed() -> None:
    # Three models but two prices: which layout the missing one belongs to is
    # unknowable, so none of them gets a price.
    runs = [
        "Prices and technical data",
        "Van Adventure",
        "V 60",
        "V 66",
        "V 67S",
        "Price £",
        "59,090.-",
        "61,690.-",
        "Technically permissible maximum laden mass* (kg)",
        "3500",
        "3500",
        "3500",
    ]

    products = parse_technical_page(runs, page_number=4)

    assert [product.rrp_pounds for product in products] == [None, None, None]
    assert [product.mtplm_kilograms for product in products] == [3500, 3500, 3500]


# --------------------------------------------------------------------------- #
# Finding the current price list
# --------------------------------------------------------------------------- #


#: The info-material page lists every model year Sunlight has published, newest first
#: at the time of writing — but that ordering is not something to depend on.
_INFO_MATERIAL = """
  <a href="https://www.dropbox.com/scl/fi/aaa/camper-vans-mj25-uk.pdf?rlkey=k1&st=s1&dl=1">CV 2025</a>
  <a href="https://www.dropbox.com/scl/fi/bbb/reisemobile-mj27-uk.pdf?rlkey=k2&st=s2&dl=1">MH 2027</a>
  <a href="https://www.dropbox.com/scl/fi/ccc/camper-vans-mj27-uk.pdf?rlkey=k3&st=s3&dl=1">CV 2027</a>
  <a href="https://www.dropbox.com/scl/fi/ddd/reisemobile-mj26-uk.pdf?rlkey=k4&st=s4&dl=1">MH 2026</a>
  <a href="https://www.dropbox.com/s/eee/Sunlight-Kat-RM-2024-UK-IRL.pdf?dl=1">Catalogue 2024</a>
"""


def test_the_newest_model_year_wins_not_the_first_listed() -> None:
    url = find_price_list_urls(_INFO_MATERIAL, "reisemobile")

    assert url is not None
    assert "reisemobile-mj27-uk.pdf" in url


def test_each_catalogue_resolves_to_its_own_price_list() -> None:
    campervans = find_price_list_urls(_INFO_MATERIAL, "camper-vans")

    assert campervans is not None
    assert "camper-vans-mj27-uk.pdf" in campervans


def test_the_dropbox_query_string_is_kept() -> None:
    # `rlkey` and `st` are required for the download to work and cannot be
    # reconstructed, so the whole URL has to survive the match.
    url = find_price_list_urls(_INFO_MATERIAL, "reisemobile")

    assert url is not None
    assert "rlkey=k2" in url
    assert "dl=1" in url


def test_the_glossy_catalogue_is_not_mistaken_for_a_price_list() -> None:
    # It has no technical tables; only the mjNN-uk.pdf files do.
    catalogue_only = '<a href="https://www.dropbox.com/s/eee/Sunlight-Kat-RM-2024-UK-IRL.pdf?dl=1">x</a>'

    assert find_price_list_urls(catalogue_only, "reisemobile") is None
