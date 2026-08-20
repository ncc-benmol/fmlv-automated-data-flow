"""Tests for the Bürstner adapter's pure parsing functions, against real captured text.

The fixtures are `extract_text` output from all five "Prices & Technical Data" PDFs
surveyed 19 August 2026 — see `docs/adapters/burstner.md`. No network and no PDF parsing
here; `fetch.pdf` is covered in `tests/fetch/test_pdf.py`.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.burstner import (
    DOCUMENTS,
    _band_reconciles,
    _canonical_model,
    _extract,
    _find_blocks,
    build_document_urls,
    find_document_href,
    parse_document,
)

FIXTURES = Path(__file__).parent / "fixtures"
DOCUMENTS_BY_KEY = {config.key: config for config in DOCUMENTS}


def _fixture(name: str) -> str:
    return (FIXTURES / f"burstner_{name}.txt").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Model code canonicalisation
# --------------------------------------------------------------------------- #


def test_number_first_token_is_reordered_to_fmlvs_letter_first_form() -> None:
    # B66's own tables print "594 TD"; FMLV holds "TD 594".
    assert _canonical_model("594 TD", "number_first") == "TD 594"


def test_letter_first_token_is_already_fmlvs_form() -> None:
    # Signature and Habiton already print "SFT 7.0" / "HM 6.0", FMLV's own order.
    assert _canonical_model("SFT 7.0", "letter_first") == "SFT 7.0"


# --------------------------------------------------------------------------- #
# Column-value extraction
# --------------------------------------------------------------------------- #


def test_plain_integers_are_read_per_column() -> None:
    assert _extract("int", "3500 3650 3650 3500", count=4) == [3500, 3650, 3650, 3500]


def test_a_dual_figure_takes_the_base_one_and_drops_the_second() -> None:
    # B66 Campervans' own height row: "265  / 275 265  / 275 265" for 3 columns, where
    # the second figure of each pair is a roof-up/optional variant, not the base vehicle.
    # docs/adapters/README.md: record the base vehicle.
    assert _extract("cm", "265  / 275 265  / 275 265", count=3) == [2650, 2650, 2650]


def test_a_row_whose_column_count_disagrees_is_dropped_not_guessed() -> None:
    # Two columns' worth of numbers for a 3-column table: which two, is unknowable.
    assert _extract("int", "3500 3500", count=3) == [None, None, None]


def test_price_reads_the_burstner_dot_dash_suffix() -> None:
    assert _extract("price", "80,795.- 82,495.-", count=2) == [80795, 82495]


def test_mro_band_is_read_across_a_line_wrap() -> None:
    # extract_text renders the closing figure on the next line: "3056 (2903 to\n3209)*".
    wrapped = "3056 (2903 to\n3209)*"
    assert _extract("mro_band", wrapped, count=1) == [(3056, 2903, 3209)]


def test_seats_row_mixing_a_plain_figure_and_a_range_reads_both() -> None:
    # Habiton's own row: "4   3 - 4" for its two columns (HM 6.0 plain, HM 6.1 ranged).
    assert _extract("range_or_int", "4 3 - 4", count=2) == [
        (4, "4"),
        (3, "3 - 4"),
    ]


def test_range_only_row_takes_the_standard_lower_figure() -> None:
    assert _extract("range_or_int", "2 - 4 2 - 5", count=2) == [
        (2, "2 - 4"),
        (2, "2 - 5"),
    ]


# --------------------------------------------------------------------------- #
# Mass-in-running-order self-check
# --------------------------------------------------------------------------- #


def test_a_band_matching_its_own_mass_reconciles() -> None:
    assert _band_reconciles((3056, 2903, 3209)) is True


def test_a_band_from_a_different_column_does_not_reconcile() -> None:
    # The signature of a misaligned column: this is B66 TD 594's mass paired with a
    # neighbour's band rather than its own.
    assert _band_reconciles((3056, 3036, 3356)) is False


def test_no_band_is_not_treated_as_a_contradiction() -> None:
    assert _band_reconciles(None) is True


# --------------------------------------------------------------------------- #
# Table discovery and deduplication
# --------------------------------------------------------------------------- #


def test_a_differently_grouped_header_with_no_readable_fields_contributes_no_products() -> None:
    # The real document's own equipment-comparison list repeats the layout codes as a
    # THIRD header, grouping all five models on one line rather than the 4+1 split the
    # Price table uses — so it is a distinct header, not caught by the same-codes
    # dedup in `_find_blocks`, and has no Price or weight row anywhere near it. The
    # first version of this parser read that as a second, empty copy of every model.
    products, _count = parse_document(
        "594 TD 644 TD\nPrice 80,795.- 82,495.-\nOverall length (approx. cm) 599 699\n"
        "Technically permissible maximum laden mass (kg)* 3500 3650\n"
        "\n594 TD 644 TD 684 TD\nColour coded bumpers Yes Yes Yes\nAlloy wheels Yes Yes Yes\n",
        DOCUMENTS_BY_KEY["b66-td"],
    )
    assert [product.model for product in products] == ["TD 594", "TD 644"]


def test_a_continuation_of_the_same_table_does_not_duplicate_its_models() -> None:
    # The real document repeats "594 TD 644 TD 684 TD 690 TD" verbatim on a later page to
    # continue with rows this adapter doesn't need (bed sizes, water capacity). Only the
    # first, Price-bearing occurrence should produce a block — the repeat is dropped
    # entirely by `_find_blocks`, not returned as a second entry.
    blocks = _find_blocks(
        "594 TD 644 TD\nPrice 80,795.- 82,495.-\n"
        "594 TD 644 TD\nFresh water supply (approx. l) 105 101\n",
        "number_first",
    )
    assert [codes for codes, _block in blocks] == [("TD 594", "TD 644")]
    (_codes, block) = blocks[0]
    assert "Price" in block
    assert "Fresh water supply" not in block  # the continuation's rows are unreachable


# --------------------------------------------------------------------------- #
# Whole-document parsing against the real fixtures
# --------------------------------------------------------------------------- #


def test_b66_motorhomes_parses_all_five_layouts() -> None:
    products, table_count = parse_document(_fixture("b66_td"), DOCUMENTS_BY_KEY["b66-td"])

    assert table_count == 3  # the 4-column table, the 744 solo table, the equipment list
    assert [product.model for product in products] == [
        "TD 594",
        "TD 644",
        "TD 684",
        "TD 690",
        "TD 744",
    ]
    by_model = {product.model: product for product in products}
    assert by_model["TD 690"].rrp_pounds == 79995
    assert by_model["TD 690"].mh_length_mm == 6990
    assert by_model["TD 690"].mtplm_kilograms == 3500
    assert by_model["TD 690"].mro_kilograms == 3141
    assert by_model["TD 690"].mh_payload_kilograms == 359
    assert by_model["TD 690"].berths == 2
    assert by_model["TD 690"].berths_published == "2 - 5"
    assert by_model["TD 744"].mtplm_kilograms == 4400  # the one 4400kg outlier


def test_b66_campervans_parses_three_layouts_with_a_mixed_berths_row() -> None:
    products, _count = parse_document(_fixture("b66_c"), DOCUMENTS_BY_KEY["b66-c"])

    assert [product.model for product in products] == ["C 600", "C 640", "C 644"]
    by_model = {product.model: product for product in products}
    # "Sleeping berths standard / max. 2 - 5 2 - 5 4" — the third column is plain, not
    # a range, and the mixed-shape extractor must still read it as its own column.
    assert by_model["C 600"].berths == 2
    assert by_model["C 644"].berths == 4
    assert by_model["C 644"].berths_published == "4"


def test_signature_sft_parses_all_four_layouts() -> None:
    products, _count = parse_document(
        _fixture("signature_sft"), DOCUMENTS_BY_KEY["signature-sft"]
    )

    assert [product.model for product in products] == [
        "SFT 7.0",
        "SFT 7.1",
        "SFT 7.4",
        "SFT 7.5",
    ]
    by_model = {product.model: product for product in products}
    assert by_model["SFT 7.0"].rrp_pounds == 94895
    assert by_model["SFT 7.0"].base_vehicle_manufacturer == "Fiat"
    # "Permitted number of seats (including driver)* 4 - 5 4 - 5 4 - 5 4 - 5" — every
    # column is itself a range, and the standard (lower) figure is what FMLV records.
    assert by_model["SFT 7.0"].mh_passenger_seats_inc_driver == 4
    assert by_model["SFT 7.0"].seats_published == "4 - 5"


def test_signature_smt_parses_all_four_layouts_on_the_mercedes_chassis() -> None:
    products, _count = parse_document(
        _fixture("signature_smt"), DOCUMENTS_BY_KEY["signature-smt"]
    )

    assert [product.model for product in products] == [
        "SMT 7.0",
        "SMT 7.1",
        "SMT 7.4",
        "SMT 7.5",
    ]
    assert products[0].base_vehicle_manufacturer == "Mercedes-Benz"
    assert products[0].mtplm_kilograms == 4500


def test_habiton_parses_both_habiton_and_habiton_x_from_one_document() -> None:
    products, table_count = parse_document(_fixture("habiton"), DOCUMENTS_BY_KEY["habiton"])

    assert table_count == 2  # HABITON HM, then HABITON X HMX
    assert [product.model for product in products] == [
        "HM 6.0",
        "HM 6.1",
        "HMX 6.0",
        "HMX 6.1",
    ]
    by_model = {product.model: product for product in products}
    assert by_model["HM 6.0"].rrp_pounds == 88995
    assert by_model["HM 6.1"].mh_passenger_seats_inc_driver == 3  # "3 - 4" -> standard 3
    # HMX's mass-in-running-order row prints one band for two columns — a genuine gap in
    # the source, not a misparse — so both HMX layouts are missing it and their payload.
    assert by_model["HMX 6.0"].mro_kilograms is None
    assert by_model["HMX 6.0"].mh_payload_kilograms is None
    assert by_model["HMX 6.0"].mtplm_kilograms == 4100


# --------------------------------------------------------------------------- #
# Discovering the current document URLs
# --------------------------------------------------------------------------- #


def test_find_document_href_reads_the_path_folder_and_slug() -> None:
    html = (
        '<a href="/buerstner/01-relaunch-2025/technische-daten/26-08-17-uk/'
        'buerstner-technical-data-2027-b66-td-gb.pdf">Download</a>'
    )

    assert find_document_href(html) == (
        "/buerstner/01-relaunch-2025/technische-daten/26-08-17-uk/"
        "buerstner-technical-data-2027-b66-td-gb.pdf",
        "26-08-17-uk",
        "b66-td",
    )


def test_find_document_href_returns_none_when_the_link_format_changes() -> None:
    assert find_document_href("<a href='/gb/configurator'>Configure</a>") is None


def test_build_document_urls_reconstructs_the_three_unlinked_documents() -> None:
    linked = {
        "b66-td": "https://www.buerstner.com/buerstner/01-relaunch-2025/technische-daten"
        "/26-08-17-uk/buerstner-technical-data-2027-b66-td-gb.pdf",
        "b66-c": "https://www.buerstner.com/buerstner/01-relaunch-2025/technische-daten"
        "/26-08-17-uk/buerstner-technical-data-2027-b66-c-gb.pdf",
    }

    urls = build_document_urls("26-08-17-uk", linked)

    assert urls["b66-td"] == linked["b66-td"]  # linked documents pass through unchanged
    assert urls["signature-sft"] == (
        "https://www.buerstner.com/buerstner/01-relaunch-2025/technische-daten"
        "/26-08-17-uk/buerstner-technical-data-2027-signature-sft-gb.pdf"
    )
    assert urls["habiton"] == (
        "https://www.buerstner.com/buerstner/01-relaunch-2025/technische-daten"
        "/26-08-17-uk/buerstner-technical-data-2027-habiton-gb.pdf"
    )
