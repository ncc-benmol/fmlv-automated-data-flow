"""Tests for the Swift adapter's pure parsing functions, against real brochure text.

The fixtures are the "Specification at a glance" pages of Swift's own 2026 motorhome
and campervan brochures, as `pypdf` extracts them — see `docs/adapters/swift.md`. The
two brochures are shaped differently on purpose (the motorhome one splits dimensions
and weights across two tables; the campervan one uses a single table with named rather
than numbered models), so both are exercised end to end.

No network and no PDF parsing here; `fetch.pdf` is covered in `tests/fetch/test_pdf.py`.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.swift import (
    SwiftProduct,
    _reconciles,
    find_brochure_url,
    parse_campervan_specs,
    parse_motorhome_specs,
)

FIXTURES = Path(__file__).parent / "fixtures"
MOTORHOME_SPECS = (FIXTURES / "swift_motorhome_spec_table.txt").read_text(encoding="utf-8")
CAMPERVAN_SPECS = (FIXTURES / "swift_campervan_spec_table.txt").read_text(encoding="utf-8")


def _by_key(products: list[SwiftProduct]) -> dict[tuple[str, str], SwiftProduct]:
    return {product.key: product for product in products}


# --------------------------------------------------------------------------- #
# Motorhomes — two tables, joined
# --------------------------------------------------------------------------- #


def test_every_motorhome_layout_is_found() -> None:
    # Swift's own motorhomes page says "20 layouts across four exceptional ranges".
    products = parse_motorhome_specs(MOTORHOME_SPECS)

    assert len(products) == 20
    assert {product.range_label for product in products} == {
        "Voyager",
        "Trekker",
        "Escape",
        "Kon-Tiki",
    }


def test_motorhome_dimensions_and_weights_tables_are_joined_per_layout() -> None:
    # These come from two separate tables on the page, matched on (range, layout).
    product = _by_key(parse_motorhome_specs(MOTORHOME_SPECS))[("Voyager", "505")]

    assert product.berths == 4
    assert product.mh_passenger_seats_inc_driver == 2
    assert (product.mh_length_mm, product.mh_width_mm, product.mh_height_mm) == (
        6190,
        2370,
        2870,
    )
    assert (product.mtplm_kilograms, product.mro_kilograms) == (3500, 2837)
    assert product.mh_payload_kilograms == 663


def test_footnote_marks_on_the_trailing_weight_columns_do_not_hide_a_row() -> None:
    """The Escape and Kon-Tiki rows, which an earlier pattern dropped in full.

    Their trailer and gross-train figures carry a `#` mark (`2000kg#`) that the Voyager
    and Trekker rows don't. Requiring those two columns to be unmarked silently cost
    eight of the twenty motorhomes every weight they publish.
    """
    products = _by_key(parse_motorhome_specs(MOTORHOME_SPECS))

    assert products[("Escape", "674")].mtplm_kilograms == 4500
    assert products[("Kon-Tiki", "894")].mro_kilograms == 3935
    assert all(
        product.mtplm_kilograms is not None
        for product in products.values()
        if product.range_label in {"Escape", "Kon-Tiki"}
    )


def test_layouts_repeated_across_ranges_stay_separate_products() -> None:
    # Voyager and Trekker both sell a 540, 584 and 594 on different specifications —
    # so the join key has to be (range, layout), not the layout number alone.
    products = _by_key(parse_motorhome_specs(MOTORHOME_SPECS))

    assert products[("Voyager", "540")].mro_kilograms == 3012
    assert products[("Trekker", "540")].mro_kilograms == 3042


# --------------------------------------------------------------------------- #
# Campervans — one table, named models
# --------------------------------------------------------------------------- #


def test_every_campervan_layout_is_found() -> None:
    products = parse_campervan_specs(CAMPERVAN_SPECS)

    assert len(products) == 10
    assert {product.range_label for product in products} == {"Monza", "Trekker", "Carrera"}


def test_multi_word_model_names_are_not_truncated() -> None:
    """Trekker, Trekker X and Trekker XL are three different campervans.

    A model name is not always a single token, and a lazy match without an explicit
    engine-column anchor stops at "Trekker" for all three — collapsing them into one
    product and losing two.
    """
    trekkers = [
        product for product in parse_campervan_specs(CAMPERVAN_SPECS)
        if product.range_label == "Trekker"
    ]

    assert [product.model for product in trekkers] == ["Trekker", "Trekker X", "Trekker XL"]
    assert [product.mh_length_mm for product in trekkers] == [5530, 5980, 5980]
    assert [product.berths for product in trekkers] == [4, 4, 2]


def test_campervan_row_yields_dimensions_and_weights_together() -> None:
    (monza,) = [
        product for product in parse_campervan_specs(CAMPERVAN_SPECS)
        if product.range_label == "Monza"
    ]

    assert monza.model == "Monza"
    assert (monza.berths, monza.mh_passenger_seats_inc_driver) == (4, 5)
    assert (monza.mh_length_mm, monza.mh_width_mm, monza.mh_height_mm) == (5050, 2150, 2070)
    assert (monza.mtplm_kilograms, monza.mro_kilograms) == (3175, 2724)


def test_footnotes_and_legend_text_are_not_read_as_layouts() -> None:
    # These pages carry numbered footnotes and a symbol legend alongside the table.
    models = {product.model for product in parse_campervan_specs(CAMPERVAN_SPECS)}

    assert models == {"Monza", "Trekker", "Trekker X", "Trekker XL", *"122 132 144 184 194 244".split()}


# --------------------------------------------------------------------------- #
# Cross-cutting: units, reconciliation, brochure discovery
# --------------------------------------------------------------------------- #


def test_dimensions_are_converted_from_metres_to_millimetres() -> None:
    # Swift publishes "7.54m"; FMLV stores millimetres.
    product = _by_key(parse_motorhome_specs(MOTORHOME_SPECS))[("Voyager", "475")]

    assert product.mh_length_mm == 7540


def test_every_real_product_reconciles_against_swifts_own_arithmetic() -> None:
    # payload == MTPLM - MRO, for all 30. A failure here means the tables misjoined.
    products = parse_motorhome_specs(MOTORHOME_SPECS) + parse_campervan_specs(CAMPERVAN_SPECS)

    assert len(products) == 30
    assert [product.key for product in products if not _reconciles(product)] == []


def test_a_misjoined_weight_is_caught_by_the_reconciliation_check() -> None:
    # Voyager 505's payload against Voyager 540's weights: out by hundreds of kg.
    misjoined = SwiftProduct(
        range_label="Voyager",
        model="505",
        mtplm_kilograms=3500,
        mro_kilograms=3012,
        mh_payload_kilograms=663,
    )

    assert _reconciles(misjoined) is False


def test_a_product_with_no_weights_is_not_treated_as_contradictory() -> None:
    assert _reconciles(SwiftProduct(range_label="Escape", model="640")) is True


def test_find_brochure_url_returns_an_absolute_url() -> None:
    html = '<a href="/media/noeb4jei/2026_swift_motorhome_brochure.pdf">Download</a>'

    assert find_brochure_url(html) == (
        "https://www.swiftgroup.co.uk/media/noeb4jei/2026_swift_motorhome_brochure.pdf"
    )


def test_find_brochure_url_returns_none_when_the_link_is_gone() -> None:
    # The media path is an opaque key that can't be reconstructed, so there is nothing
    # sensible to fall back to — better to report the page changed.
    assert find_brochure_url("<a href='/motorhomes/product/42117/'>Kon-Tiki</a>") is None
