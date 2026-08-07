"""Matching + diff against the real Adria baseline export and real Phase 4 fixtures.

No network — reuses the same captured `/livewire/update` JSON and PDF text as
`tests/adapters/test_adria.py`, run through the real `motorhome-campervans.xlsx`
baseline. This is the Phase 5 analogue of the manual validation recorded in
docs/adapters/adria.md: that write-up found the "670 DC" configuration's MRO and
MTPLM higher than the baseline's (3650kg vs 3500kg — an "extended homologation"
chassis option), read as a genuine current-vs-baseline delta, not a parse bug. This
test pins that finding through the real matching + diff pipeline: token-based
matching must still land on the right baseline row (`"Supreme 670 DC"`, product_id
4147) even though the scraped model string is worded completely differently
(`"670 DC Supreme Alde RHD"`), and the diff must surface exactly that discrepancy.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.adria import (
    _build_extracted_motorhome,
    parse_livewire_products,
    parse_technical_data_pdf,
)
from src.diff import ChangeKind, diff_products, match_products
from src.product_model.io import read_xlsx

FIXTURES = Path(__file__).parent.parent / "adapters" / "fixtures"
BASELINE_EXPORT = (
    Path(__file__).parent.parent.parent
    / "resources"
    / "csv-examples"
    / "1785753111-adria-caravans-motorhomes-product-exports"
    / "motorhome-campervans.xlsx"
)


def _real_scraped_670dc():
    body = (FIXTURES / "adria_matrix_livewire_response.json").read_bytes()
    products = parse_livewire_products(body)
    supreme_alde = next(p for p in products if p.trim_label == "Supreme Alde RHD")
    pdf_text = (FIXTURES / "adria_matrix_670dc_pdf_text.txt").read_text(encoding="utf-8")
    specs = parse_technical_data_pdf(pdf_text)
    return _build_extracted_motorhome(
        supreme_alde,
        "Matrix",
        "https://www.adria.co.uk/motorhomes/matrix",
        "https://configure.adria-mobil.com/gb/25-26/x/pdf",
        specs,
    )


def _matrix_baseline_rows():
    result = read_xlsx(BASELINE_EXPORT)
    return [
        motorhome
        for motorhome in result.motorhomes
        if motorhome.manufacturer_range and "matrix" in motorhome.manufacturer_range.lower()
    ]


def test_reworded_scraped_model_matches_the_right_baseline_row() -> None:
    scraped = _real_scraped_670dc()
    assert scraped.motorhome.model == "670 DC Supreme Alde RHD"

    matrix_rows = _matrix_baseline_rows()
    results = match_products([scraped], matrix_rows)

    assert len(results) == 1
    assert results[0].baseline is not None
    assert results[0].baseline.model == "Supreme 670 DC"
    assert results[0].baseline.product_id == 4147
    assert results[0].method == "fuzzy"


def test_diff_surfaces_the_documented_extended_homologation_discrepancy() -> None:
    scraped = _real_scraped_670dc()
    matrix_rows = _matrix_baseline_rows()

    diffs = diff_products([scraped], matrix_rows)

    matched = next(d for d in diffs if d.fmlv_product_id == 4147)
    assert matched.kind == ChangeKind.CHANGED_FIELD

    by_field = {change.field: (change.old_value, change.new_value) for change in matched.changes}
    assert by_field["mtplm_kilograms"] == (3500, 3650)
    assert by_field["mro_kilograms"] == (3184, 3228)

    # Dimensions the PDF also carries were checked and matched — a first-class
    # "verified unchanged" result per DESIGN.md §6.5, not silence.
    assert "mh_length_mm" in matched.confirmed_fields
    assert "mh_width_mm" in matched.confirmed_fields
    assert "mh_height_mm" in matched.confirmed_fields
