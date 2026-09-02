"""Morelo Reisemobile (morelo-reisemobile.de) — the second adapter.

See `docs/adapters/morelo.md` for the full write-up. The short version is that Morelo
is the opposite shape to Adria: **one document holds everything**, and no JavaScript is
involved at any point.

Morelo publishes an official English-language price list PDF covering every model year
configuration — around 60 floorplans across seven ranges — with a "TECHNICAL
SPECIFICATIONS" page per one or two floorplans giving weights, dimensions, base chassis
and price as plain extractable text. So the whole adapter is two plain `Fetcher` calls:
the catalogue page (to discover the current price list's URL, which carries a model-year
and date stamp that changes), then the PDF itself.

Two things about that PDF drive the shape of the parser:

* **Spec pages carry one or two floorplans side by side.** Values arrive as
  `label v1 v2` on one line, so a page's data is columnar and every column has to stay
  associated with the right name.
* **Reading order does not reliably match column order.** On some pages pypdf emits the
  right-hand model name before the left-hand one. Pairing by reading order therefore
  swaps two products' weights and prices — silently, and plausibly enough that nothing
  downstream would catch it. Names are ordered by x-coordinate instead, via
  `fetch.pdf.extract_positioned_text`.

As a second line of defence the parser checks Morelo's own published arithmetic:
`payload == max weight - mass in running order`, per column. A column-misalignment bug
breaks that identity, so a product whose figures don't reconcile is dropped with a
warning rather than proposed to a reviewer (see `_reconciles`).

Not extracted: berths and seats, which this price list simply does not state (it gives
bed dimensions, not a berth count). They stay `None` — the reviewer sees no proposed
change for them, rather than a guess derived from bed sizes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_positioned_text, extract_text
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://www.morelo-reisemobile.de"
CATALOGUE_PAGE_URL = f"{BASE_URL}/en/buy-and-rent/catalogues-and-price-lists"
MANUFACTURER = "Morelo"
MANUFACTURER_DISPLAY_NAME = "Morelo"

#: Morelo prices in euros; FMLV's `rrp_pounds` is sterling. Converting at all is a
#: judgement call Ben made deliberately (the alternative was leaving price empty), so
#: the rate is stated here as one obvious, greppable constant rather than being buried
#: in an expression — it *will* go stale and will need revisiting. Every converted
#: price records the original euro figure and this rate in its provenance, so a
#: reviewer always sees what the number was derived from and can overrule it.
EUR_TO_GBP_RATE = 0.855
EUR_TO_GBP_RATE_DATE = "2026-08-06"

#: Ranges as the price list names them, longest first so that "LOFT PREMIUM LINER"
#: is never matched as "LOFT". The display form is what goes into
#: `manufacturer_range`; the PDF shouts everything in capitals, which is not how the
#: FMLV export writes range names.
RANGES: tuple[tuple[str, str], ...] = (
    ("LOFT PREMIUM ALKOVEN", "Loft Premium Alkoven"),
    ("LOFT PREMIUM LINER", "Loft Premium Liner"),
    ("LOFT PREMIUM", "Loft Premium"),
    ("LOFT ALKOVEN", "Loft Alkoven"),
    ("LOFT LINER", "Loft Liner"),
    ("GRAND EMPIRE", "Grand Empire"),
    ("EMPIRE LINER", "Empire Liner"),
    ("PALACE LINER", "Palace Liner"),
    ("PALACE", "Palace"),
    ("LOFT", "Loft"),
    ("HOME", "Home"),
)

_SPEC_PAGE_MARKER = "TECHNICAL SPECIFICATIONS"

#: The price list's own English label for each numeric row this adapter reads, mapped
#: to the `Motorhome` field it fills. `Payload` is read but not stored directly — it's
#: used to check the other two weights reconcile (see `_reconciles`).
_ROW_LABELS: dict[str, str] = {
    "max. weight (kg)": "mtplm_kilograms",
    "Mass in running order (kg)": "mro_kilograms",
    "Payload (kg)": "mh_payload_kilograms",
    "Total length (mm)": "mh_length_mm",
    "Total width (mm)": "mh_width_mm",
    "Total height (mm)": "mh_height_mm",
}

#: A German-formatted integer: thousands separated by dots, e.g. `11.990` or `900`.
_NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})*(?![\d.,])")

#: A euro price, e.g. `312.500,00`. At least one thousands group is required, which is
#: what keeps this from matching a metric written German-style elsewhere on the same
#: page — `Interior standing height 2,06` would otherwise be read as a €2 vehicle.
#: Every Morelo is six figures, so demanding the group costs nothing.
_PRICE = re.compile(r"(\d{1,3}(?:\.\d{3})+),(\d{2})")

#: Chassis makes the price list names, for `base_vehicle_manufacturer`.
_BASE_VEHICLE = re.compile(r"\b(IVECO|Mercedes-Benz)\b")


def _to_int(text: str) -> int:
    """`'11.990'` -> `11990`. Morelo uses a dot as the thousands separator."""
    return int(text.replace(".", ""))


# --------------------------------------------------------------------------- #
# Discovering the current price list
# --------------------------------------------------------------------------- #

#: The English price list, e.g.
#: `/fileadmin/downloads/.../preisliste/morelo_preisliste_2027-2_260804_GB.pdf`.
#: Matched rather than hardcoded because the model year (`2027-2`) and the date stamp
#: both change; the catalogue page is the only place that says which is current.
#: Anchored on the `morelo_preisliste_` *filename* rather than on "preisliste"
#: anywhere in the path, because the containing directory is `kataloge_preislisten`
#: — so a looser match happily returns the glossy catalogue, which has no spec tables.
_PRICE_LIST_HREF = re.compile(
    r"""["'](/fileadmin/[^"']*morelo_preisliste_[^"']*_GB\.pdf)["']""", re.IGNORECASE
)


def find_price_list_url(catalogue_html: str) -> str | None:
    """The absolute URL of the current English price list, from the catalogue page.

    The page also links catalogues (glossy brochures, no spec tables) and price lists
    in six other languages; only the English price list carries the technical pages in
    a form this parser reads.
    """
    match = _PRICE_LIST_HREF.search(catalogue_html)
    return f"{BASE_URL}{match.group(1)}" if match else None


# --------------------------------------------------------------------------- #
# Parsing one "TECHNICAL SPECIFICATIONS" page
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MoreloProduct:
    """One floorplan, as read from one column of one spec page."""

    range_label: str
    model: str
    page_number: int
    base_vehicle_manufacturer: str | None
    price_eur: int | None
    mtplm_kilograms: int | None
    mro_kilograms: int | None
    mh_payload_kilograms: int | None
    mh_length_mm: int | None
    mh_width_mm: int | None
    mh_height_mm: int | None

    @property
    def rrp_pounds(self) -> int | None:
        if self.price_eur is None:
            return None
        return round(self.price_eur * EUR_TO_GBP_RATE)


def page_range(page_text: str) -> tuple[str, str] | None:
    """The (PDF spelling, display name) of the range a spec page belongs to.

    Read off the page's own `MORELO <RANGE>` heading. `RANGES` is ordered longest
    first, so a "MORELO LOFT PREMIUM LINER" page is never mistaken for a "LOFT" one.
    """
    for pdf_name, display in RANGES:
        if f"MORELO {pdf_name}" in page_text:
            return pdf_name, display
    return None


def _names_in(text: str, pdf_range_name: str) -> list[str]:
    r"""Floorplan names inside one run of text, in the order they are written.

    Splitting on the range name (rather than matching a trailing letter group) is what
    copes with two names run together with no separator at all, which this PDF does:
    `'LOFT LINER 85 MBLOFT LINER 85 LSB'`. The split is deliberately not anchored on a
    word boundary, because there isn't one inside `MBLOFT`. Requiring each fragment to
    begin with a digit is what makes that safe — splitting a `PALACE LINER` heading on
    `PALACE` leaves `' LINER 88 LB'`, which is correctly ignored.

    Matching is kept on one line — `[ \t]*`, never `\s*` — because the range name also
    appears in the page's own `MORELO LOFT ALKOVEN` heading, and the next line down can
    begin with a footnote (`1) see back`). Allowing the match to cross the newline turns
    that footnote marker into a phantom floorplan called "1".
    """
    if pdf_range_name not in text:
        return []
    names: list[str] = []
    for fragment in re.split(re.escape(pdf_range_name), text)[1:]:
        match = re.match(r"[ \t]*(\d+[ \t]*[A-Z]*)", fragment)
        if match:
            names.append(re.sub(r"\s+", " ", match.group(1)).strip())
    return names


def model_names_in_column_order(
    page_text: str, positioned: list[tuple[float, str]], pdf_range_name: str
) -> list[str]:
    """The page's floorplan names, left column first.

    Reading order is the starting point, and x-coordinates are used to correct it —
    rather than the other way round — because neither source is complete on its own:

    * Reading order is wrong on some pages: pypdf emits the right-hand name first on,
      for example, the two `110 GSB` pages, which would attach the wrong weights and
      price to both products.
    * Coordinates are missing on other pages: pypdf resolves some name runs to (0, 0)
      rather than their real position, and sorting on that puts them first wherever
      they actually sit — corrupting pages whose reading order was fine.

    So: take the names in reading order, and re-sort by x only when every name has a
    genuine position to sort on. Where positions are missing, reading order is left
    alone, which is what the (0, 0) pages need. Sorting is stable, so the two names
    inside a single run (`'PALACE 85 L PALACE 88 LB'`, one x for both) keep their
    written order.
    """
    names = _names_in(page_text, pdf_range_name)
    if not names:
        return []

    # y=0 marks a run pypdf could not place, not a run at the foot of the page: every
    # real title-row name sits high on the page.
    x_by_name: dict[str, float] = {}
    for x, text in positioned:
        for name in _names_in(text, pdf_range_name):
            x_by_name.setdefault(name, x)

    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    if any(x_by_name.get(name) is None for name in seen):
        return seen
    return sorted(seen, key=lambda name: x_by_name[name])


def _row_values(page_text: str, label: str) -> list[int]:
    """Every column's value from the row `label` introduces.

    Parenthesised figures are dropped first: Morelo writes an uprated chassis option as
    `5.600 (5.990)`, and the bracketed number is the optional upgrade, not this
    configuration's weight. FMLV wants the vehicle as specified, so the base figure is
    the right one — and leaving the brackets in would also double every column count.
    """
    # The optional character absorbs a footnote marker set immediately against the
    # label with no space (`Payload (kg)1 1.000`). It is not always a digit: on the
    # Alkoven pages the same marker is a superscript that extraction renders as U+FFFD
    # (`max. weight (kg)� 7.490`), which silently cost those pages every weight
    # until it was allowed for here. Requiring whitespace *after* the marker is what
    # stops its slot from eating the first digit of a real value on the unmarked rows,
    # where `Total length (mm) 8.690` would otherwise lose its 8.
    match = re.search(rf"{re.escape(label)}[\d�¹²³]?\s+(.+)", page_text)
    if not match:
        return []
    line = re.sub(r"\([^)]*\)", " ", match.group(1))
    return [_to_int(number) for number in _NUMBER.findall(line)]


def _price_values(page_text: str) -> list[int]:
    """Every column's headline price, in whole euros.

    Prices sit on an unlabelled line near the foot of the page (the euro sign is lost
    to encoding, so there is no symbol to anchor on) — but the `NNN.NNN,00` shape is
    unambiguous within a spec page, where every other figure is a plain integer.
    """
    for line in page_text.splitlines():
        matches = _PRICE.findall(line)
        if matches:
            return [_to_int(whole) for whole, _cents in matches]
    return []


def _reconciles(product: MoreloProduct) -> bool:
    """Whether Morelo's own three weights agree: payload == max weight - MIRO.

    This is the parser's own alignment check, not a data-quality opinion. All three
    numbers come from different columns of different rows, so if a page's columns were
    misread the identity almost certainly breaks. A product missing any of the three is
    not contradicted by anything and passes.
    """
    mtplm, mro, payload = (
        product.mtplm_kilograms,
        product.mro_kilograms,
        product.mh_payload_kilograms,
    )
    if mtplm is None or mro is None or payload is None:
        return True
    return mtplm - mro == payload


def parse_spec_page(
    page_text: str, positioned: list[tuple[float, str]], page_number: int
) -> list[MoreloProduct]:
    """Every floorplan on one "TECHNICAL SPECIFICATIONS" page, left column first.

    `positioned` is `(x, text)` for the runs pypdf could actually place — callers pass
    only items with a real position (see `collect`), because an unplaced run reports
    (0, 0) and would otherwise sort as the leftmost column.

    Returns `[]` for a page whose names and value columns don't line up, rather than
    guessing at the pairing — see the module docstring.
    """
    found = page_range(page_text)
    if found is None:
        return []
    pdf_range_name, range_label = found

    names = model_names_in_column_order(page_text, positioned, pdf_range_name)
    if not names:
        return []

    columns = {field: _row_values(page_text, label) for label, field in _ROW_LABELS.items()}
    prices = _price_values(page_text)
    base_vehicle = _BASE_VEHICLE.search(page_text)

    def value(field: str, index: int) -> int | None:
        values = columns.get(field) or []
        # A row with one value per name is trustworthy. Any other count means the row
        # wrapped or a footnote mark was read as a column, and guessing which value
        # belongs to which floorplan is exactly the mistake this module is built to
        # avoid — so that row is dropped for the whole page.
        return values[index] if len(values) == len(names) else None

    products: list[MoreloProduct] = []
    for index, name in enumerate(names):
        products.append(
            MoreloProduct(
                range_label=range_label,
                model=name,
                page_number=page_number,
                # The price list prints `Mercedes-Benz`; FMLV holds `Mercedes`.
                base_vehicle_manufacturer=(
                    fmlv_base_vehicle(base_vehicle.group(1)) if base_vehicle else None
                ),
                price_eur=prices[index] if len(prices) == len(names) else None,
                mtplm_kilograms=value("mtplm_kilograms", index),
                mro_kilograms=value("mro_kilograms", index),
                mh_payload_kilograms=value("mh_payload_kilograms", index),
                mh_length_mm=value("mh_length_mm", index),
                mh_width_mm=value("mh_width_mm", index),
                mh_height_mm=value("mh_height_mm", index),
            )
        )
    return products


# --------------------------------------------------------------------------- #
# Orchestration: fetch + parse -> ExtractedMotorhome
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(product: MoreloProduct, pdf_url: str) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        rrp_pounds=product.rrp_pounds,
        mro_kilograms=product.mro_kilograms,
        mtplm_kilograms=product.mtplm_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=product.mh_length_mm,
        mh_width_mm=product.mh_width_mm,
        mh_height_mm=product.mh_height_mm,
    )

    source = f"{pdf_url}#page={product.page_number}"
    label = f"{product.range_label} {product.model}"
    provenance: dict[str, Provenance] = {}

    if product.base_vehicle_manufacturer is not None:
        # A page-level fact, not a per-column one: one spec page's floorplans all sit
        # on the chassis its own heading names, so every column on the page shares it.
        provenance["base_vehicle_manufacturer"] = Provenance(
            source_url=source,
            snippet=(
                f"{label} — {product.base_vehicle_manufacturer}, the chassis make named "
                f"on this floorplan's own spec page in the price list"
            ),
        )

    if product.price_eur is not None:
        provenance["rrp_pounds"] = Provenance(
            source_url=source,
            snippet=(
                f"{label}: EUR {product.price_eur:,} (incl. German VAT) x "
                f"{EUR_TO_GBP_RATE} = GBP {product.rrp_pounds:,}. Converted at a fixed "
                f"rate recorded {EUR_TO_GBP_RATE_DATE}, not a live one — check before "
                f"accepting."
            ),
        )

    numeric_snippets = {
        "mro_kilograms": ("Mass in running order (kg)", product.mro_kilograms),
        "mtplm_kilograms": ("Technically permissible max. weight (kg)", product.mtplm_kilograms),
        "mh_payload_kilograms": ("Payload (kg)", product.mh_payload_kilograms),
        "mh_length_mm": ("Total length (mm)", product.mh_length_mm),
        "mh_width_mm": ("Total width (mm)", product.mh_width_mm),
        "mh_height_mm": ("Total height (mm)", product.mh_height_mm),
    }
    for field, (row_label, value) in numeric_snippets.items():
        if value is not None:
            provenance[field] = Provenance(
                source_url=source, snippet=f"{label} — {row_label}: {value:,}"
            )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Morelo needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    price_list_url: str | None = None,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every Morelo floorplan from the current English price list PDF.

    `price_list_url` pins a specific price list (re-running an old one, or testing a
    newly published one before the catalogue page links it); by default the current one
    is discovered from the catalogue page.

    Like `adria.collect`, a page that can't be parsed is narrated through `on_progress`
    and skipped rather than raised — one unreadable page out of thirty shouldn't cost
    the other twenty-nine.
    """
    if price_list_url is None:
        on_progress("finding the current price list...")
        catalogue = http.fetch(CATALOGUE_PAGE_URL)
        if catalogue.status_code != 200:
            msg = f"catalogue page returned {catalogue.status_code}"
            raise RuntimeError(msg)
        price_list_url = find_price_list_url(catalogue.file_path.read_text(encoding="utf-8"))
        if price_list_url is None:
            msg = (
                f"no English price list PDF linked from {CATALOGUE_PAGE_URL} — "
                f"the page's link format has probably changed"
            )
            raise RuntimeError(msg)

    on_progress(f"downloading {price_list_url} ...")
    pdf = http.fetch(price_list_url)
    if pdf.status_code != 200:
        msg = f"price list returned {pdf.status_code}"
        raise RuntimeError(msg)

    document = extract_text(pdf.file_path)
    if document.is_empty():
        msg = f"no text in {price_list_url} — it may have been published as page images"
        raise RuntimeError(msg)

    spec_pages = [page for page in document.pages if _SPEC_PAGE_MARKER in page.text]
    on_progress(f"{len(spec_pages)} technical-specification page(s) in {len(document.pages)}")

    results: list[ExtractedMotorhome] = []
    for page in spec_pages:
        # Sorted left-to-right here rather than relying on the extractor's order,
        # which is the page's own drawing order. Runs pypdf could not place report
        # (0, 0) and are dropped, since sorting them would put them leftmost wherever
        # they actually sit — see `model_names_in_column_order`.
        positioned = sorted(
            (
                (item.x, item.text)
                for item in extract_positioned_text(pdf.file_path, page.page_number)
                if item.y > 0
            ),
            key=lambda item: item[0],
        )
        products = parse_spec_page(page.text, positioned, page.page_number)
        if not products:
            on_progress(f"  p{page.page_number} — SKIPPED: no floorplan recognised")
            continue
        for product in products:
            label = f"{product.range_label} {product.model}"
            if not _reconciles(product):
                on_progress(
                    f"  p{page.page_number} {label} — SKIPPED: weights don't reconcile "
                    f"({product.mtplm_kilograms} - {product.mro_kilograms} != "
                    f"{product.mh_payload_kilograms}), so the columns may be misread"
                )
                continue
            results.append(_build_extracted_motorhome(product, price_list_url))
        on_progress(f"  p{page.page_number} — {products[0].range_label}: {len(products)} floorplan(s)")

    on_progress(f"{len(results)} product(s) collected")
    return results
