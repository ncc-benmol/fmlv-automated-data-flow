"""Tests for the Morelo adapter's pure parsing functions, against real captured pages.

The fixtures are three real pages of Morelo's own English price list PDF (model year
2027-2), each chosen because it broke an earlier version of the parser — see
`docs/adapters/morelo.md`:

* **page 58** (Palace Liner 103/110 GSB) — pypdf emits the two model names in the
  opposite order to their value columns.
* **page 54** (Palace Liner 88 LB / 90 M) — pypdf can't place one of the names and
  reports it at (0, 0), so x-coordinates alone would reorder a page that was already
  right.
* **page 24** (Loft Alkoven 92 LS / 92 M) — footnote markers that extract as U+FFFD
  rather than digits, plus a `1) see back` footnote positioned to look like a
  floorplan name.

Each is stored as the text `pypdf` extracts plus the positioned runs it reports, so the
column-ordering logic is tested on exactly what the real document produces. No network
and no PDF parsing here; `fetch.pdf` is covered in `tests/fetch/test_pdf.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.adapters.morelo import (
    EUR_TO_GBP_RATE,
    MoreloProduct,
    _build_extracted_motorhome,
    _reconciles,
    find_price_list_url,
    model_names_in_column_order,
    page_range,
    parse_spec_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _page(stem: str) -> tuple[str, list[tuple[float, str]]]:
    """One fixture page as `(text, positioned)`, as `parse_spec_page` wants it.

    Runs pypdf could not place are filtered out on y, exactly as `collect` does.
    """
    text = (FIXTURES / f"{stem}_text.txt").read_text(encoding="utf-8")
    raw = json.loads((FIXTURES / f"{stem}_positions.json").read_text(encoding="utf-8"))
    return text, [(x, run) for x, y, run in raw if y > 0]


REVERSED_PAGE = "morelo_page58_palace_liner_reversed"
UNPOSITIONED_PAGE = "morelo_page54_palace_liner_unpositioned"
ALKOVEN_PAGE = "morelo_page24_loft_alkoven"


# --------------------------------------------------------------------------- #
# Range and model identification
# --------------------------------------------------------------------------- #


def test_page_range_prefers_the_longest_matching_range_name() -> None:
    # "MORELO PALACE LINER" must not be read as the separate "Palace" range.
    text, _positions = _page(REVERSED_PAGE)

    assert page_range(text) == ("PALACE LINER", "Palace Liner")


def test_model_names_follow_x_order_not_reading_order() -> None:
    """The whole reason coordinates are consulted at all.

    Page 58 lists 103 GSB in the left column and 110 GSB in the right, but pypdf emits
    the right-hand name first. Taking reading order here would give both products the
    other's weights and price.
    """
    text, positions = _page(REVERSED_PAGE)

    assert model_names_in_column_order(text, positions, "PALACE LINER") == [
        "103 GSB",
        "110 GSB",
    ]


def test_model_names_keep_reading_order_when_a_name_has_no_position() -> None:
    """The counter-case that stops the fix above from breaking working pages.

    On page 54 pypdf places "88 LB" but reports "90 M" at (0, 0) — filtered out before
    it gets here. Sorting on the one remaining coordinate would be sorting on nothing,
    so reading order, which is correct on this page, has to survive untouched.
    """
    text, positions = _page(UNPOSITIONED_PAGE)

    assert model_names_in_column_order(text, positions, "PALACE LINER") == ["88 LB", "90 M"]


def test_footnote_below_the_range_heading_is_not_read_as_a_floorplan() -> None:
    # Page 24's "MORELO LOFT ALKOVEN" heading is followed on the next line by
    # "1) see back", which a newline-crossing match turns into a floorplan called "1".
    text, positions = _page(ALKOVEN_PAGE)

    assert model_names_in_column_order(text, positions, "LOFT ALKOVEN") == ["92 LS", "92 M"]


def test_model_names_run_together_without_a_separator_are_split() -> None:
    # Real shape from the Loft Liner pages: no space between one name and the next.
    joined = "LOFT LINER 85 MBLOFT LINER 85 LSB"

    assert model_names_in_column_order(joined, [], "LOFT LINER") == ["85 MB", "85 LSB"]


# --------------------------------------------------------------------------- #
# Whole-page parsing
# --------------------------------------------------------------------------- #


def test_parse_spec_page_assigns_each_column_to_the_right_floorplan() -> None:
    text, positions = _page(REVERSED_PAGE)

    products = parse_spec_page(text, positions, page_number=58)

    assert [product.model for product in products] == ["103 GSB", "110 GSB"]
    shorter, longer = products
    assert (shorter.mh_length_mm, longer.mh_length_mm) == (10850, 11280)
    assert (shorter.mro_kilograms, longer.mro_kilograms) == (8910, 8995)
    assert (shorter.price_eur, longer.price_eur) == (484950, 495050)
    # Normalised to FMLV's spelling; the price list itself prints "Mercedes-Benz".
    assert shorter.base_vehicle_manufacturer == "Mercedes"


def test_parse_spec_page_reads_weights_past_a_non_digit_footnote_marker() -> None:
    # The Alkoven pages mark the weight rows with a superscript that extracts as
    # U+FFFD ("max. weight (kg)� 7.490"), which once cost these pages every weight.
    text, positions = _page(ALKOVEN_PAGE)

    products = parse_spec_page(text, positions, page_number=24)

    assert [product.mtplm_kilograms for product in products] == [7490, 7490]
    assert [product.mro_kilograms for product in products] == [5440, 5440]
    assert [product.mh_payload_kilograms for product in products] == [2050, 2050]


def test_parse_spec_page_ignores_the_optional_uprated_chassis_weight() -> None:
    # Morelo writes an optional uprating in brackets: "5.600 (5.990)". FMLV wants the
    # vehicle as specified, and counting the bracket would double the column count.
    page_text = (
        "MORELO HOME\nTECHNICAL SPECIFICATIONS\nHOME 78 L\n"
        "max. weight (kg)1 5.600 (5.990)\n"
        "Mass in running order (kg)1 4.600\n"
        "Payload (kg)1 1.000 (1.390)\n"
        "Total length (mm) 7.810\n"
        "211.650,00\n"
    )

    (product,) = parse_spec_page(page_text, [], page_number=6)

    assert product.mtplm_kilograms == 5600
    assert product.mh_payload_kilograms == 1000


def test_parse_spec_page_drops_a_row_whose_column_count_disagrees() -> None:
    # Two floorplans but only one length: the row wrapped, or a mark was miscounted.
    # Which product the single value belongs to is unknowable, so neither gets it.
    page_text = (
        "MORELO PALACE\nTECHNICAL SPECIFICATIONS\nPALACE 85 L PALACE 88 LB\n"
        "Total length (mm) 8.690\n"
        "Total width (mm) 2.450 2.450\n"
    )

    products = parse_spec_page(page_text, [], page_number=48)

    assert [product.mh_length_mm for product in products] == [None, None]
    assert [product.mh_width_mm for product in products] == [2450, 2450]


def test_a_metric_written_german_style_is_not_read_as_a_price() -> None:
    # "Interior standing height 2,06" was once extracted as a EUR 2 motorhome.
    page_text = (
        "MORELO PALACE\nTECHNICAL SPECIFICATIONS\nPALACE 92 G\n"
        "Interior standing height (m) 2,06\n"
        "348.800,00\n"
    )

    (product,) = parse_spec_page(page_text, [], page_number=52)

    assert product.price_eur == 348800


# --------------------------------------------------------------------------- #
# Weight reconciliation and price conversion
# --------------------------------------------------------------------------- #


def _product(**overrides: object) -> MoreloProduct:
    defaults: dict[str, object] = {
        "range_label": "Palace",
        "model": "85 L",
        "page_number": 48,
        "base_vehicle_manufacturer": "IVECO",
        "price_eur": 312500,
        "mtplm_kilograms": 7490,
        "mro_kilograms": 5570,
        "mh_payload_kilograms": 1920,
        "mh_length_mm": 8690,
        "mh_width_mm": 2450,
        "mh_height_mm": 3580,
    }
    return MoreloProduct(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_weights_that_agree_with_morelos_own_arithmetic_reconcile() -> None:
    assert _reconciles(_product()) is True


def test_weights_that_contradict_each_other_do_not_reconcile() -> None:
    # The signature of a misread column: payload no longer equals MTPLM - MIRO.
    assert _reconciles(_product(mh_payload_kilograms=1810)) is False


def test_a_product_missing_a_weight_is_not_treated_as_contradictory() -> None:
    # Nothing to contradict — this must not be confused with a misaligned page.
    assert _reconciles(_product(mro_kilograms=None)) is True


def test_price_is_converted_from_euros_at_the_recorded_rate() -> None:
    product = _product(price_eur=312500)

    assert product.rrp_pounds == round(312500 * EUR_TO_GBP_RATE)


def test_no_euro_price_means_no_sterling_price() -> None:
    assert _product(price_eur=None).rrp_pounds is None


# --------------------------------------------------------------------------- #
# Finding the current price list
# --------------------------------------------------------------------------- #


def test_find_price_list_url_picks_the_english_price_list() -> None:
    # The real page links seven languages of price list plus three catalogues; only
    # the English price list has the technical pages this parser reads.
    html = """
      <a href="/fileadmin/downloads/kataloge_preislisten/pdfs/morelo_katalog_2025_251211_GB.pdf">Catalogue</a>
      <a href="/fileadmin/downloads/kataloge_preislisten/pdfs/preisliste/morelo_preisliste_2027-2_260804_DE.pdf">DE</a>
      <a href="/fileadmin/downloads/kataloge_preislisten/pdfs/preisliste/morelo_preisliste_2027-2_260804_GB.pdf">GB</a>
    """

    assert find_price_list_url(html) == (
        "https://www.morelo-reisemobile.de/fileadmin/downloads/kataloge_preislisten"
        "/pdfs/preisliste/morelo_preisliste_2027-2_260804_GB.pdf"
    )


def test_find_price_list_url_returns_none_when_the_link_format_changes() -> None:
    # Better to report "the page changed" than to fetch a catalogue and find no specs.
    assert find_price_list_url("<a href='/en/contact'>Contact us</a>") is None


# --------------------------------------------------------------------------- #
# The base vehicle
#
# A value set on the model but never registered as provenance cannot reach FMLV:
# `diff/compare.py` compares only the fields the provenance dict names, and
# `store/changes.py` proposes only those fields for a NEW product. So an unregistered
# base vehicle looks correct on every product FMLV already holds — the baseline value
# carries through untouched — and lands blank on every genuinely new one, even though
# it is a REQUIRED field.
# --------------------------------------------------------------------------- #


def test_base_vehicle_is_registered_as_provenance_so_a_new_product_keeps_it() -> None:
    extracted = _build_extracted_motorhome(_product(), "https://example/price-list.pdf")

    assert extracted.motorhome.base_vehicle_manufacturer == "IVECO"
    assert "base_vehicle_manufacturer" in extracted.provenance


def test_the_base_vehicle_snippet_points_at_the_page_it_was_read_from() -> None:
    # Morelo states the chassis per spec page, not per column, so the snippet must send
    # a reviewer to that page rather than implying a per-floorplan row.
    extracted = _build_extracted_motorhome(
        _product(base_vehicle_manufacturer="Mercedes", page_number=54),
        "https://example/price-list.pdf",
    )
    entry = extracted.provenance["base_vehicle_manufacturer"]

    assert entry.source_url.endswith("#page=54")
    assert "Mercedes" in entry.snippet
    assert "spec page" in entry.snippet
