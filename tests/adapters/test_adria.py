"""Tests for the Adria adapter's pure parsing functions, against real captured data.

The fixtures here are real snapshots (see `docs/adapters/adria.md`). From the Phase 4
survey: the `/livewire/update` JSON response for the Matrix range's layout-selector
component, and the text `pypdf` extracts from the technical-data PDF for one
configuration (Matrix Supreme 670 DC, "Supreme Alde RHD" trim). Added 2026-08-20 with
the 60Y editions: the same pair for Matrix 60Y, plus a Supersonic spec sheet, which is
here for one reason — it is Mercedes-based where every other fixture is Fiat, so it is
what stops `parse_base_vehicle_manufacturer` passing by returning a constant.

No network, no browser — the fetch side is covered separately in
`tests/fetch/test_browser.py`.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.adria import (
    DEFAULT_RANGES,
    RANGES,
    LivewireProduct,
    _build_extracted_motorhome,
    baseline_in_scope,
    cross_source_disagreements,
    parse_base_vehicle_manufacturer,
    parse_livewire_products,
    parse_technical_data_pdf,
    pdf_describes_layout,
    pdf_title,
    range_config,
    technical_data_pdf_url,
    unwrap_livewire,
)
from src.product_model.model import Motorhome

FIXTURES = Path(__file__).parent / "fixtures"
LIVEWIRE_RESPONSE = FIXTURES / "adria_matrix_livewire_response.json"
PDF_TEXT = FIXTURES / "adria_matrix_670dc_pdf_text.txt"
SIXTY_YEAR_LIVEWIRE_RESPONSE = FIXTURES / "adria_60y_matrix_livewire_response.json"
SIXTY_YEAR_PDF_TEXT = FIXTURES / "adria_60y_matrix_670sl_pdf_text.txt"
MERCEDES_PDF_TEXT = FIXTURES / "adria_supersonic_780dc_pdf_text.txt"


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


def test_spec_snippet_keeps_the_qualifier_that_the_recorded_figure_drops() -> None:
    # docs/adapters/README.md: record the base figure, carry the published wording into
    # the snippet. The 60Y Matrix sheet prints seats as "3 AT 3,500KG (4 AT 3,650KG)" —
    # the 3 is what FMLV records, and the reviewer cannot judge it without the rest.
    specs = parse_technical_data_pdf(SIXTY_YEAR_PDF_TEXT.read_text(encoding="utf-8"))

    seats = specs["mh_passenger_seats_inc_driver"]
    assert seats.value == 3
    assert seats.snippet == "Nr. of seats 3 AT 3,500KG (4 AT 3,650KG)"

    mro = specs["mro_kilograms"]
    assert mro.value == 3134
    assert "WITHOUT LUXE OR ALL INC' PACK" in mro.snippet


# --------------------------------------------------------------------------- #
# Self-checks: is this the right vehicle's spec sheet?
# --------------------------------------------------------------------------- #


def test_pdf_title_is_read_from_the_running_footer() -> None:
    text = PDF_TEXT.read_text(encoding="utf-8")

    assert pdf_title(text) == "MATRIX SUPREME 670 DC"


def test_pdf_describes_layout_confirms_a_matching_sheet() -> None:
    text = PDF_TEXT.read_text(encoding="utf-8")

    assert pdf_describes_layout(text, "670 DC") is True


def test_pdf_describes_layout_rejects_another_vehicles_sheet() -> None:
    # The failure this adapter uniquely risks: a constructed PDF URL resolving to a
    # different product. The numbers would be plausible and nothing downstream catches
    # it, so a False here is what stops the product being proposed at all.
    text = PDF_TEXT.read_text(encoding="utf-8")

    assert pdf_describes_layout(text, "780 SL") is False


def test_pdf_describes_layout_is_undecided_without_a_title_or_a_layout() -> None:
    # None is not False: an unanswerable question must not drop a product.
    assert pdf_describes_layout("no footer here at all", "670 DC") is None
    assert pdf_describes_layout(PDF_TEXT.read_text(encoding="utf-8"), None) is None


def test_cross_source_disagreement_is_reported_with_both_figures() -> None:
    specs = parse_technical_data_pdf(PDF_TEXT.read_text(encoding="utf-8"))
    product = LivewireProduct(
        layout_label="670 DC",
        trim_label="Supreme Alde RHD",
        product_id="x",
        price_pounds=None,
        price_string=None,
        berths=3,  # the sheet says 4
        seats=None,
        configurator_url=None,
    )

    assert cross_source_disagreements(product, specs) == {"berths": (3, 4)}


def test_agreeing_sources_report_nothing() -> None:
    specs = parse_technical_data_pdf(PDF_TEXT.read_text(encoding="utf-8"))
    body = LIVEWIRE_RESPONSE.read_bytes()
    supreme_alde = next(
        p for p in parse_livewire_products(body) if p.trim_label == "Supreme Alde RHD"
    )

    assert cross_source_disagreements(supreme_alde, specs) == {}


def test_a_disagreement_puts_both_figures_in_front_of_the_reviewer() -> None:
    specs = parse_technical_data_pdf(PDF_TEXT.read_text(encoding="utf-8"))
    product = LivewireProduct(
        layout_label="670 DC",
        trim_label="Supreme Alde RHD",
        product_id="x",
        price_pounds=None,
        price_string=None,
        berths=3,
        seats=None,
        configurator_url=None,
    )

    extracted = _build_extracted_motorhome(
        product,
        range_config("motorhomes/matrix", "Matrix"),
        "https://www.adria.co.uk/motorhomes/matrix",
        "https://configure.adria-mobil.com/gb/25-26/x/pdf",
        specs,
        "Fiat",
        cross_source_disagreements(product, specs),
    )

    # The spec sheet's figure is the one recorded...
    assert extracted.motorhome.berths == 4
    # ...but the range page's disagreeing figure is not lost.
    assert "3" in extracted.provenance["berths"].snippet
    assert "range page" in extracted.provenance["berths"].snippet


# --------------------------------------------------------------------------- #
# Base vehicle manufacturer
# --------------------------------------------------------------------------- #


def test_base_vehicle_manufacturer_reads_the_chassis_section_heading() -> None:
    text = PDF_TEXT.read_text(encoding="utf-8")

    assert parse_base_vehicle_manufacturer(text) == "Fiat"


def test_base_vehicle_manufacturer_is_not_a_constant() -> None:
    text = MERCEDES_PDF_TEXT.read_text(encoding="utf-8")

    assert parse_base_vehicle_manufacturer(text) == "Mercedes"


def test_base_vehicle_manufacturer_is_unset_rather_than_guessed_when_ambiguous() -> None:
    text = "CA. Fiat Chassis\nsome equipment\nCB. Mercedes Chassis\nmore equipment\n"

    assert parse_base_vehicle_manufacturer(text) is None


def test_base_vehicle_manufacturer_ignores_the_chassis_type_line() -> None:
    # "Chassis type FIAT special" describes the variant, not the manufacturer, and is
    # the wrong shape for base_vehicle_manufacturer.
    assert parse_base_vehicle_manufacturer("Chassis type FIAT special\n") is None


# --------------------------------------------------------------------------- #
# The 60Y anniversary editions
# --------------------------------------------------------------------------- #


def test_sixty_year_page_yields_its_single_layout() -> None:
    products = parse_livewire_products(SIXTY_YEAR_LIVEWIRE_RESPONSE.read_bytes())

    assert len(products) == 1
    assert products[0].layout_label == "670 SL"


def test_sixty_year_product_is_named_the_way_fmlv_names_it() -> None:
    # FMLV product 8195: manufacturer_range "Matrix", model "670 SL 60Y". The site's own
    # trim label for this configuration is "60 years RHD" and must not reach the model.
    products = parse_livewire_products(SIXTY_YEAR_LIVEWIRE_RESPONSE.read_bytes())
    specs = parse_technical_data_pdf(SIXTY_YEAR_PDF_TEXT.read_text(encoding="utf-8"))

    extracted = _build_extracted_motorhome(
        products[0],
        range_config("60y/matrix", "Matrix 60Y"),
        "https://www.adria.co.uk/60y/matrix",
        "https://configure.adria-mobil.com/gb/25-26/x/pdf",
        specs,
        "Fiat",
        {},
    )

    assert extracted.motorhome.manufacturer_range == "Matrix"
    assert extracted.motorhome.model == "670 SL 60Y"


def test_an_ordinary_range_still_names_its_products_by_layout_and_trim() -> None:
    body = LIVEWIRE_RESPONSE.read_bytes()
    supreme_alde = next(
        p for p in parse_livewire_products(body) if p.trim_label == "Supreme Alde RHD"
    )
    specs = parse_technical_data_pdf(PDF_TEXT.read_text(encoding="utf-8"))

    extracted = _build_extracted_motorhome(
        supreme_alde,
        range_config("motorhomes/matrix", "Matrix"),
        "https://www.adria.co.uk/motorhomes/matrix",
        "https://configure.adria-mobil.com/gb/25-26/x/pdf",
        specs,
        "Fiat",
        {},
    )

    assert extracted.motorhome.manufacturer_range == "Matrix"
    assert extracted.motorhome.model == "670 DC Supreme Alde RHD"


def test_sixty_year_sheet_confirms_its_own_identity() -> None:
    text = SIXTY_YEAR_PDF_TEXT.read_text(encoding="utf-8")

    assert pdf_title(text) == "MATRIX 670 SL 60Y"
    assert pdf_describes_layout(text, "670 SL") is True


def test_range_selectors_are_unique_so_a_range_flag_is_unambiguous() -> None:
    # `--range Matrix` and `--range "Matrix 60Y"` must select different pages, which is
    # the whole reason RangeConfig separates `label` from `fmlv_range`.
    labels = [label for _path, label in DEFAULT_RANGES]
    assert len(labels) == len(set(labels))
    assert {"Matrix", "Matrix 60Y", "Coral 60Y", "TWIN 60Y"} <= set(labels)


def test_default_ranges_stays_the_two_element_shape_the_cli_reads() -> None:
    assert all(len(entry) == 2 for entry in DEFAULT_RANGES)
    assert len(DEFAULT_RANGES) == len(RANGES)


def _baseline_row(manufacturer_range: str, model: str) -> Motorhome:
    return Motorhome(
        manufacturer="Adria Mobil", manufacturer_range=manufacturer_range, model=model
    )


def test_a_sixty_year_run_sees_the_sixty_year_baseline_row() -> None:
    # FMLV product 8195. Without this it has no baseline, is classified NEW_PRODUCT,
    # and uploading would duplicate a product the NCC already holds.
    row = _baseline_row("Matrix", "670 SL 60Y")

    assert baseline_in_scope(row, {"Matrix 60Y"}) is True


def test_a_sixty_year_run_does_not_pull_in_the_ordinary_range() -> None:
    row = _baseline_row("Matrix", "Supreme 670 DC")

    assert baseline_in_scope(row, {"Matrix 60Y"}) is False


def test_an_ordinary_range_run_does_not_pull_in_the_sixty_year_row() -> None:
    # A baseline row a narrowed run pulls in but never sweeps is reported as
    # DISAPPEARED — so being too generous here invents a disappearance notice for a
    # product that is very much still on sale.
    ordinary = _baseline_row("Matrix", "Supreme 670 DC")
    sixty_year = _baseline_row("Matrix", "670 SL 60Y")

    assert baseline_in_scope(ordinary, {"Matrix"}) is True
    assert baseline_in_scope(sixty_year, {"Matrix"}) is False


def test_baseline_scope_covers_every_selector_in_a_multi_range_run() -> None:
    labels = {"Matrix 60Y", "Coral 60Y", "TWIN 60Y"}

    assert baseline_in_scope(_baseline_row("TWIN", "640 SGX 60Y"), labels) is True
    assert baseline_in_scope(_baseline_row("Coral", "670 DL 60Y"), labels) is True
    assert baseline_in_scope(_baseline_row("Supersonic", "780 DC"), labels) is False


def test_an_unknown_range_pair_falls_back_to_the_label_as_the_fmlv_range() -> None:
    config = range_config("motorhomes/whatever", "Whatever")

    assert config.fmlv_range == "Whatever"
    assert config.model_suffix is None
