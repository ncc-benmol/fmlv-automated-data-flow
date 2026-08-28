"""Tests for the Bürstner adapter's pure parsing functions, against real captured text.

The fixtures are `extract_text` output from all five "Prices & Technical Data" PDFs
surveyed 19 August 2026 — see `docs/adapters/burstner.md`. No network and no PDF parsing
here; `fetch.pdf` is covered in `tests/fetch/test_pdf.py`.
"""

from __future__ import annotations

from pathlib import Path

from src.product_model.enums import BodyType

from src.adapters.burstner import (
    DOCUMENTS,
    _band_reconciles,
    _build_extracted_motorhome,
    _canonical_model,
    _extract,
    _find_blocks,
    body_type_for,
    build_document_urls,
    find_document_href,
    parse_document,
    published_chassis,
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
    assert products[0].base_vehicle_manufacturer == "Mercedes"
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


# --------------------------------------------------------------------------- #
# The base vehicle
#
# It reaches FMLV only if it is *registered as provenance*, not merely set on the
# model: `diff/compare.py` compares only the fields the provenance dict names, and
# `store/changes.py` proposes only those fields for a NEW product. An unregistered
# value is silently dropped — which is how all seven of the first run's new layouts
# (B66 C 640, Habiton HM/HMX 6.1, all four Signature SMT) reached the upload CSV with
# `base_vehicle_manufacturer` blank, a REQUIRED field, while the 13 that already
# existed in FMLV looked correct, their value carried through from the baseline.
# --------------------------------------------------------------------------- #


def _one_product(key: str):
    products, _count = parse_document(_fixture(key.replace("-", "_")), DOCUMENTS_BY_KEY[key])
    return products[0]


def test_every_document_names_its_own_chassis() -> None:
    # Not a per-column figure: the chassis is stated once per document, in its own
    # engine list, so all five are checked at document level.
    assert published_chassis(_fixture("b66_td"))[0] == "Fiat"
    assert published_chassis(_fixture("b66_c"))[0] == "Fiat"
    assert published_chassis(_fixture("signature_sft"))[0] == "Fiat"
    assert published_chassis(_fixture("signature_smt"))[0] == "Mercedes"
    assert published_chassis(_fixture("habiton"))[0] == "Mercedes"


def test_the_chassis_line_is_quoted_as_the_document_prints_it() -> None:
    make, line = published_chassis(_fixture("signature_smt"))

    # FMLV's spelling, which is shorter than the document's own "Mercedes Benz".
    assert make == "Mercedes"
    assert line == "Mercedes Benz Sprinter 4,5 t - 417 CDI"


def test_mercedes_branded_equipment_is_not_mistaken_for_a_chassis() -> None:
    # The Habiton document lists "Mercedes Comfort Seats" 34 lines from its real chassis
    # line, and "Mercedes emergency call system" nearer still. Matching the make alone
    # would read a seat trim option as the base vehicle.
    equipment_only = """Chassis Equipment
Mercedes Comfort Seats upholstered to match the living
Mercedes emergency call system
"""

    assert published_chassis(equipment_only) is None


def test_base_vehicle_is_registered_as_provenance_so_a_new_product_keeps_it() -> None:
    # The regression this section exists for. Setting the field is not enough.
    for key in ("b66-td", "b66-c", "signature-sft", "signature-smt", "habiton"):
        extracted = _build_extracted_motorhome(_one_product(key), "https://example/doc.pdf")

        assert extracted.motorhome.base_vehicle_manufacturer is not None, key
        assert "base_vehicle_manufacturer" in extracted.provenance, key


def test_the_provenance_snippet_quotes_the_document_rather_than_asserting_a_make() -> None:
    extracted = _build_extracted_motorhome(_one_product("habiton"), "https://example/doc.pdf")
    snippet = extracted.provenance["base_vehicle_manufacturer"].snippet

    assert extracted.motorhome.base_vehicle_manufacturer == "Mercedes"
    assert "Sprinter 317 CDI" in snippet  # the document's own words, not the adapter's


def _synthetic(chassis_line: str) -> str:
    """A minimal document in Signature's letter-first shape.

    One layout code on its own line, one readable label so the block is not discarded
    as an equipment chart, and whatever chassis line the caller wants to plant.
    """
    return (
        """SMT 7.0
Price 100,000.-
Overall length (approx. cm) 700
Headroom (approx. cm) 200
"""
        + chassis_line
    )


def test_a_document_that_changes_chassis_overrules_the_configured_make_and_says_so() -> None:
    # DOCUMENTS records Signature SMT as Mercedes. If Bürstner moves the range onto
    # a Ducato, the document is the live source and wins — but a reviewer must be told
    # the adapter expected otherwise, because the competing reading is that the document
    # changed shape and the line was misread.
    products, _count = parse_document(
        _synthetic("Fiat Ducato Multijet 3 - 2.2l - 140 hp"),
        DOCUMENTS_BY_KEY["signature-smt"],
    )

    assert products[0].base_vehicle_manufacturer == "Fiat"
    assert products[0].base_vehicle_expected == "Mercedes"
    extracted = _build_extracted_motorhome(products[0], "https://example/doc.pdf")
    snippet = extracted.provenance["base_vehicle_manufacturer"].snippet
    assert "expected Mercedes" in snippet
    assert "do not accept this blind" in snippet


def test_a_document_naming_no_chassis_falls_back_to_the_configured_make() -> None:
    # Still recorded and still registered — but the snippet must not claim the document
    # said something it does not say.
    products, _count = parse_document(_synthetic(""), DOCUMENTS_BY_KEY["signature-smt"])

    assert products[0].base_vehicle_manufacturer == "Mercedes"
    assert products[0].base_vehicle_published is None
    assert products[0].base_vehicle_expected is None
    extracted = _build_extracted_motorhome(products[0], "https://example/doc.pdf")
    snippet = extracted.provenance["base_vehicle_manufacturer"].snippet
    assert "names no chassis line of its own" in snippet


# --------------------------------------------------------------------------- #
# body_type
#
# Left unset until 27 August 2026, because FMLV's baseline holds two Bürstner
# classifications that no rule derivable from the source reproduces, and proposing a
# "correction" to a record that was actually right is worse than an honest gap.
#
# The requester then confirmed both are FMLV errors: TD 744 is a low profile, not an
# `a_class` ("even the photos on FMLV back that up"), and C 644 is a plain high-top
# campervan with no elevating roof as standard. With that settled the field is filled,
# and the two corrections are proposed rather than left for a manual edit.
#
# WIDTH is the discriminator, not height. Checked against the real baseline export:
# the rule reproduces FMLV on 11 of the 13 products it holds, and the two misses are
# exactly those confirmed errors. Height cannot do the job - FMLV's own stored heights
# are headroom, not overall (Habiton 1900mm, Signature 1980mm), and the documents' real
# heights overlap between the families (vans 2650-2850, coachbuilts 2800-2990).
# --------------------------------------------------------------------------- #


def test_a_panel_van_width_is_a_campervan_and_a_wider_body_is_a_coachbuilt() -> None:
    assert body_type_for(2050, 2650) == BodyType.CAMPERVAN_HIGH_TOP  # B66 C
    assert body_type_for(2040, 2730) == BodyType.CAMPERVAN_HIGH_TOP  # Habiton HM
    assert body_type_for(2300, 2950) == BodyType.COACH_BUILT_LOW_PROFILE  # B66 TD
    assert body_type_for(2350, 2840) == BodyType.COACH_BUILT_LOW_PROFILE  # Signature


def test_a_van_below_the_high_top_threshold_is_a_plain_campervan() -> None:
    # No Bürstner layout is currently this low, but the threshold is the shared one and
    # the rule should not silently promote a low-roof van to a high top.
    assert body_type_for(2050, 2200) == BodyType.CAMPERVAN


def test_body_type_is_unset_rather_than_guessed_when_a_measurement_is_missing() -> None:
    # A row dropped by the column self-check leaves these blank, and the family cannot be
    # told apart without the width.
    assert body_type_for(None, 2950) is None
    assert body_type_for(2050, None) is None  # a van whose roof height is unknown


def test_td_744_is_a_low_profile_despite_being_the_ranges_outlier() -> None:
    """FMLV holds `a_class`; the requester confirmed 27 August 2026 that is wrong.

    TD 744 genuinely is the odd one out of its range — its own single-column table, a
    4400kg chassis against its siblings' 3500/3650, and 2990mm against their 2950mm — so
    the risk was reading "different" as "A-class". Width is what settles it: an A-class
    body is wider than the semi-integrated it shares a range with, and every B66 TD is
    2300mm.
    """
    products, _count = parse_document(_fixture("b66_td"), DOCUMENTS_BY_KEY["b66-td"])
    by_model = {product.model: product for product in products}

    assert by_model["TD 744"].mh_width_mm == by_model["TD 594"].mh_width_mm == 2300
    assert by_model["TD 744"].mh_height_mm == 2990  # the tallest, not the shortest
    assert by_model["TD 744"].mtplm_kilograms == 4400  # and the heaviest by 750kg
    assert by_model["TD 744"].body_type == BodyType.COACH_BUILT_LOW_PROFILE
    assert by_model["TD 744"].body_type == by_model["TD 594"].body_type


def test_c_644_has_no_elevating_roof_despite_sleeping_four() -> None:
    """FMLV holds `campervan_high_top_elevating_roof`; also confirmed an error.

    C 644 sleeps 4 where its siblings sleep 2, which is the trap — the extra berths come
    from its own floorplan, not from a roof. Bürstner's van page prices the pop-up roof as
    an accessory ("Pop-up roof in Lanzarote Grey £420", "optionally available"), so it is
    standard on nothing.
    """
    products, _count = parse_document(_fixture("b66_c"), DOCUMENTS_BY_KEY["b66-c"])
    by_model = {product.model: product for product in products}

    assert by_model["C 644"].berths == 4
    assert by_model["C 600"].berths == 2
    assert by_model["C 644"].body_type == BodyType.CAMPERVAN_HIGH_TOP
    assert by_model["C 644"].body_type == by_model["C 600"].body_type


def test_every_layout_gets_a_body_type_and_it_is_registered_as_provenance() -> None:
    for key in ("b66-td", "b66-c", "signature-sft", "signature-smt", "habiton"):
        products, _count = parse_document(
            _fixture(key.replace("-", "_")), DOCUMENTS_BY_KEY[key]
        )
        for product in products:
            extracted = _build_extracted_motorhome(product, "https://example/doc.pdf")

            assert extracted.motorhome.body_type is not None, f"{key} {product.model}"
            assert "body_type" in extracted.provenance, f"{key} {product.model}"


def test_the_body_type_snippet_does_not_cite_b66_evidence_for_another_range() -> None:
    """The B66 pages say nothing about Signature, and the snippet must not imply they do."""
    products, _count = parse_document(
        _fixture("signature_smt"), DOCUMENTS_BY_KEY["signature-smt"]
    )
    snippet = _build_extracted_motorhome(products[0], "u").provenance["body_type"].snippet

    assert "B66" not in snippet
    assert "was not read" in snippet  # says plainly what it could not check
