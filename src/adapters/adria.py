"""Adria Mobil (UK importer site, adria.co.uk) — the first adapter.

See `docs/adapters/adria.md` for the full write-up of how this site works and why the
adapter is shaped this way. In short, two fetches per product:

1. A model-range page (e.g. `/motorhomes/matrix`) renders almost empty on load — the
   real layout/trim/price data only exists in a Laravel Livewire component that mounts
   when it scrolls into view, firing an AJAX call. `BrowserFetcher.fetch_with_capture`
   (scroll=True) drives that and snapshots the JSON response, which gives layout code,
   trim name, berths/seats, RRP, and a per-configuration `id`.
2. That `id` plugs into a predictable, unauthenticated, non-JS PDF URL
   (`configure.adria-mobil.com/<market>/<period>/<id>/pdf`) which is the manufacturer's
   own technical-data sheet: dimensions, MIRO (mass in running order) and max
   authorised weight (MTPLM) are all in there as plain text, one fetch per product,
   through the ordinary `Fetcher`.

Weights/dimensions are *not* attempted from the HTML/JSON — confirmed absent from that
payload during the Phase 4 survey (see the write-up). The PDF is the only source found
for them, matching DESIGN.md's anticipated PDF fallback.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..fetch.browser import BrowserFetcher
from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.adria.co.uk"
MANUFACTURER = "Adria Mobil"
MANUFACTURER_DISPLAY_NAME = "Adria"

#: (URL path under BASE_URL, display name matching the range as the NCC export writes
#: it). Read off the site's own navigation during the Phase 4 survey — see the
#: write-up. Not discovered dynamically (yet): a nice follow-up would be to read these
#: off the `/motorhomes` and `/campervans` index pages instead of hardcoding them, so
#: a new range doesn't need a code change to be picked up.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes/supersonic", "Supersonic"),
    ("motorhomes/sonic", "Sonic"),
    ("motorhomes/matrix", "Matrix"),
    ("motorhomes/coral", "Coral"),
    ("motorhomes/compact-max", "Compact Max"),
    ("motorhomes/compact", "Compact"),
    ("campervans/supertwin", "Supertwin"),
    ("campervans/twin-sports", "Twin Sports"),
    ("campervans/twin-supreme", "Twin Supreme"),
)

_LIVEWIRE_UPDATE_MARKER = "livewire/update"

# --------------------------------------------------------------------------- #
# Livewire JSON: layout/trim/price/id per configuration
# --------------------------------------------------------------------------- #


def unwrap_livewire(value: Any) -> Any:
    """Undo Livewire v3's wire-format wrapping of arrays: `[value, {"s": ...}]`.

    Livewire's "synthesizers" serialise every array/collection as a 2-element
    `[data, meta]` pair, where `meta` is a dict carrying at least an `"s"` (shape) key.
    A plain product dict never collides with this shape — it always has far more keys
    than just `"s"`/`"class"` — so matching on it is safe.
    """
    if isinstance(value, list):
        if len(value) == 2 and isinstance(value[1], dict) and "s" in value[1]:
            return unwrap_livewire(value[0])
        return [unwrap_livewire(item) for item in value]
    if isinstance(value, dict):
        return {key: unwrap_livewire(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class LivewireProduct:
    """One sellable layout+trim configuration, as read from the Livewire JSON."""

    layout_label: str | None
    trim_label: str | None
    product_id: str
    price_pounds: int | None
    price_string: str | None
    berths: int | None
    seats: int | None
    configurator_url: str | None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def parse_livewire_products(response_body: bytes) -> list[LivewireProduct]:
    """Extract every priced configuration from one `/livewire/update` response body."""
    outer = json.loads(response_body)
    components = outer.get("components") or []
    if not components:
        return []

    snapshot_raw = components[0].get("snapshot")
    snapshot = json.loads(snapshot_raw) if isinstance(snapshot_raw, str) else snapshot_raw
    data = unwrap_livewire((snapshot or {}).get("data", {}))

    products: list[LivewireProduct] = []
    for layout in data.get("apiData") or []:
        if not isinstance(layout, dict):
            continue
        for node in layout.get("products") or []:
            if not isinstance(node, dict) or not node.get("id"):
                continue
            price = node.get("price") or {}
            products.append(
                LivewireProduct(
                    layout_label=layout.get("label"),
                    trim_label=node.get("label"),
                    product_id=str(node["id"]),
                    price_pounds=_to_int(price.get("retail_price_with_tax")),
                    price_string=node.get("priceString"),
                    berths=_to_int(node.get("berths")),
                    seats=_to_int(node.get("seats")),
                    configurator_url=node.get("configuratorURL"),
                )
            )
    return products


def technical_data_pdf_url(product: LivewireProduct) -> str | None:
    """The direct, unauthenticated PDF URL for one configuration's technical data.

    Derived from `configuratorURL` (e.g. `.../gb/25-26?link=1&...`) rather than a
    hardcoded market/period, so it tracks whatever season/market the site is currently
    serving.
    """
    if not product.configurator_url:
        return None
    path_parts = [p for p in urlparse(product.configurator_url).path.split("/") if p]
    if len(path_parts) < 2:
        return None
    market, period = path_parts[0], path_parts[1]
    return f"https://configure.adria-mobil.com/{market}/{period}/{product.product_id}/pdf"


# --------------------------------------------------------------------------- #
# Technical-data PDF: dimensions and weights
# --------------------------------------------------------------------------- #

_SPEC_PATTERNS: dict[str, re.Pattern[str]] = {
    "mh_length_mm": re.compile(r"Body length \(mm\)\s*(\d+)"),
    "mh_width_mm": re.compile(r"Total width \(mm\)\s*(\d+)"),
    "mh_height_mm": re.compile(r"Total height \(mm\)\s*(\d+)"),
    "mro_kilograms": re.compile(r"Mass in running order \(MIRO-min, kg\)\s*(\d+)"),
    "mtplm_kilograms": re.compile(r"Max authorised weight \(kg\)\s*(\d+)"),
    "berths": re.compile(r"Nr\. of berths\s*(\d+)"),
    "mh_passenger_seats_inc_driver": re.compile(r"Nr\. of seats\s*(\d+)"),
}


@dataclass(frozen=True)
class PdfSpecMatch:
    value: int
    snippet: str


def parse_technical_data_pdf(text: str) -> dict[str, PdfSpecMatch]:
    """Pull the numeric fields this adapter cares about out of the spec-sheet text.

    Only the "B. Dimensions and weights" / "O. Collection" sections are targeted —
    the PDF also lists ~50 optional-equipment lines per product (ticked/crossed-out),
    which is a much harder parse and, per DESIGN.md §4.3, a lower priority than the
    numeric fields for an *existing* product.
    """
    matches: dict[str, PdfSpecMatch] = {}
    for field_name, pattern in _SPEC_PATTERNS.items():
        match = pattern.search(text)
        if match:
            matches[field_name] = PdfSpecMatch(value=int(match.group(1)), snippet=match.group(0))
    return matches


# --------------------------------------------------------------------------- #
# Orchestration: fetch + parse -> ExtractedMotorhome
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(
    product: LivewireProduct,
    range_label: str,
    range_url: str,
    pdf_url: str,
    pdf_specs: dict[str, PdfSpecMatch],
) -> ExtractedMotorhome:
    model = " ".join(part for part in (product.layout_label, product.trim_label) if part)

    def spec(field_name: str) -> int | None:
        match = pdf_specs.get(field_name)
        return match.value if match else None

    mro = spec("mro_kilograms")
    mtplm = spec("mtplm_kilograms")

    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=range_label,
        model=model or None,
        berths=spec("berths") or product.berths,
        mh_passenger_seats_inc_driver=spec("mh_passenger_seats_inc_driver") or product.seats,
        rrp_pounds=product.price_pounds,
        mro_kilograms=mro,
        mtplm_kilograms=mtplm,
        mh_payload_kilograms=(mtplm - mro) if mro is not None and mtplm is not None else None,
        mh_length_mm=spec("mh_length_mm"),
        mh_width_mm=spec("mh_width_mm"),
        mh_height_mm=spec("mh_height_mm"),
    )

    provenance: dict[str, Provenance] = {}
    if product.price_string:
        provenance["rrp_pounds"] = Provenance(
            source_url=range_url,
            snippet=f"{product.layout_label} / {product.trim_label}: {product.price_string}",
        )
    for field_name, match in pdf_specs.items():
        provenance[field_name] = Provenance(source_url=pdf_url, snippet=match.snippet)

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: BrowserFetcher,
    snapshot_dir: Path,
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every product across the given Adria ranges (all of them, by default).

    `on_progress` is called with one line of text at each range/product boundary and
    whenever a configuration is silently skipped — a missing PDF URL, a non-200 PDF
    fetch, or a PDF that yielded no spec fields (see `_SPEC_PATTERNS`). None of those
    three raise, by design (a mid-sweep parser hiccup shouldn't abort every other
    product), which is exactly why they're worth narrating rather than only being
    visible after the fact by diffing snapshot counts. Defaults to a no-op so calling
    this from a test, or any caller that doesn't want console output, needs nothing
    extra; `cli.py` wires this to `print` for an interactive `fmlv run`.
    """
    results: list[ExtractedMotorhome] = []

    for range_path, range_label in ranges:
        range_url = f"{BASE_URL}/{range_path}"
        on_progress(f"[{range_label}] loading range page...")
        _page_result, captured = browser.fetch_with_capture(
            range_url, capture_url_contains=_LIVEWIRE_UPDATE_MARKER, scroll=True
        )
        for response in captured:
            products = parse_livewire_products(response.file_path.read_bytes())
            on_progress(f"[{range_label}] {len(products)} configuration(s) found")
            for index, product in enumerate(products, start=1):
                label = " / ".join(
                    part for part in (product.layout_label, product.trim_label) if part
                ) or product.product_id
                prefix = f"[{range_label}] ({index}/{len(products)}) {label}"

                pdf_url = technical_data_pdf_url(product)
                if pdf_url is None:
                    on_progress(f"{prefix} — SKIPPED: no configuratorURL, can't build a PDF URL")
                    continue

                on_progress(f"{prefix} — fetching PDF...")
                pdf_result = http.fetch(pdf_url)
                if pdf_result.status_code != 200:
                    on_progress(f"{prefix} — SKIPPED: PDF returned {pdf_result.status_code}")
                    continue

                pdf_text = extract_text(pdf_result.file_path).text
                pdf_specs = parse_technical_data_pdf(pdf_text)
                if not pdf_specs:
                    on_progress(f"{prefix} — WARNING: no spec fields found in PDF text")
                results.append(
                    _build_extracted_motorhome(
                        product, range_label, range_url, pdf_url, pdf_specs
                    )
                )

    return results
