"""Tests for the Adria adapter's pure parsing functions, against real captured data.

The fixtures here are real snapshots taken during the Phase 4 survey (see
`docs/adapters/adria.md`): the `/livewire/update` JSON response for the Matrix range's
layout-selector component, and the text `pypdf` extracts from the technical-data PDF
for one configuration (Matrix Supreme 670 DC, "Supreme Alde RHD" trim). No network,
no browser — the fetch side is covered separately in `tests/fetch/test_browser.py`.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.adria import (
    LivewireProduct,
    parse_livewire_products,
    parse_technical_data_pdf,
    technical_data_pdf_url,
    unwrap_livewire,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIVEWIRE_RESPONSE = FIXTURES / "adria_matrix_livewire_response.json"
PDF_TEXT = FIXTURES / "adria_matrix_670dc_pdf_text.txt"


def test_unwrap_livewire_unpacks_array_wire_format() -> None:
    wrapped = {"apiData": [[{"label": "670 DC"}], {"s": "arr"}], "plain": "value"}

    unwrapped = unwrap_livewire(wrapped)

    assert unwrapped == {"apiData": [{"label": "670 DC"}], "plain": "value"}


def test_unwrap_livewire_leaves_ordinary_dicts_alone() -> None:
    # A real product dict has far more than an "s" key — must not be mistaken for
    # Livewire's [value, meta] wrapper shape.
    product = {"id": "14", "label": "Supreme Alde RHD", "price": {"retail_price": 93920}}

    assert unwrap_livewire(product) == product


def test_parse_livewire_products_reads_real_matrix_response() -> None:
    body = LIVEWIRE_RESPONSE.read_bytes()

    products = parse_livewire_products(body)

    assert len(products) > 0
    supreme_alde = next(p for p in products if p.trim_label == "Supreme Alde RHD")
    assert supreme_alde.layout_label == "670 DC"
    assert supreme_alde.product_id == "100351-2526-gxajsm5200w031-14"
    assert supreme_alde.price_pounds == 93920
    assert supreme_alde.price_string == "£93,920.00"
    assert supreme_alde.configurator_url is not None
    assert "configure.adria-mobil.com" in supreme_alde.configurator_url


def test_parse_livewire_products_skips_nodes_without_an_id() -> None:
    # The layout-level "base vehicle" entry has id=null and chassis dims but isn't a
    # sellable configuration — it must not show up as a product.
    body = LIVEWIRE_RESPONSE.read_bytes()

    products = parse_livewire_products(body)

    assert all(p.product_id for p in products)


def test_technical_data_pdf_url_derives_market_and_period_from_configurator_url() -> None:
    product = LivewireProduct(
        layout_label="670 DC",
        trim_label="Supreme Alde RHD",
        product_id="100351-2526-gxajsm5200w031-14",
        price_pounds=93920,
        price_string="£93,920.00",
        berths=4,
        seats=None,
        configurator_url="https://configure.adria-mobil.com/gb/25-26?link=1&range=A",
    )

    url = technical_data_pdf_url(product)

    assert url == "https://configure.adria-mobil.com/gb/25-26/100351-2526-gxajsm5200w031-14/pdf"


def test_technical_data_pdf_url_is_none_without_a_configurator_url() -> None:
    product = LivewireProduct(
        layout_label="670 DC",
        trim_label=None,
        product_id="x",
        price_pounds=None,
        price_string=None,
        berths=None,
        seats=None,
        configurator_url=None,
    )

    assert technical_data_pdf_url(product) is None


def test_parse_technical_data_pdf_reads_real_matrix_670dc_sheet() -> None:
    text = PDF_TEXT.read_text(encoding="utf-8")

    specs = parse_technical_data_pdf(text)

    assert specs["mh_length_mm"].value == 7485
    assert specs["mh_width_mm"].value == 2299
    assert specs["mh_height_mm"].value == 2905
    assert specs["mro_kilograms"].value == 3228
    assert specs["mtplm_kilograms"].value == 3650
    assert specs["berths"].value == 4
    assert specs["mh_passenger_seats_inc_driver"].value == 4
    # Snippets are what a reviewer sees next to the proposed value — should be the
    # actual matched text, not just the bare number.
    assert "Mass in running order" in specs["mro_kilograms"].snippet


def test_parse_technical_data_pdf_is_missing_but_not_crashing_on_unrelated_text() -> None:
    specs = parse_technical_data_pdf("This PDF has no spec table at all.")

    assert specs == {}
