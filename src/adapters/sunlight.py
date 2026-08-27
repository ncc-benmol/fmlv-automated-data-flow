"""Sunlight (sunlight.de) — the fourth adapter, motorhomes and camper vans.

See `docs/adapters/sunlight.md` for the full write-up. Sunlight is the third
manufacturer in a row whose data lives in a published PDF rather than on the website,
and the best-behaved of the four so far. Two price lists — motorhomes and camper vans —
linked in plain HTML off `/en/info-material/`, no JavaScript, no form, no login.

Two things make it the easiest source yet:

* **The UK price list is already in sterling.** Sunlight is a German manufacturer, but
  it publishes a `United Kingdom & Ireland` edition quoting `Price £`. Unlike Morelo,
  no currency conversion is needed and no stale rate is baked into a proposed change.
* **Every table cell is its own text run.** The `Prices and technical data` pages read
  as a clean stream — the range name, then one run per model, then a row label followed
  by one run per model, repeating. Cell boundaries come free, so none of the splitting
  guesswork the Morelo and Swift adapters need applies here. It is the reason this
  adapter parses runs (via `fetch.pdf.extract_positioned_text`) rather than lines:
  joined into a line, `CLIFF 540 V` is indistinguishable from `CLIFF 540` followed by a
  stray `V`, and Sunlight sells both a `CLIFF 540` and a `CLIFF 540 V`.

26 products across 9 ranges from two fetches plus two PDFs.

Both price lists carry several model years at once, so the adapter picks the highest
`mjNN` it finds rather than the first — see `find_price_list_urls`.
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

BASE_URL = "https://www.sunlight.de"
INFO_MATERIAL_URL = f"{BASE_URL}/en/info-material/"
MANUFACTURER = "Sunlight"
MANUFACTURER_DISPLAY_NAME = "Sunlight"

#: (price list stem, category label). The two catalogues are separate PDFs with
#: identical internal structure, so the only difference is which one to fetch.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("reisemobile", "Motorhomes"),
    ("camper-vans", "Camper Vans"),
)

#: The marker that opens a technical-data page, and the run the table hangs off: the
#: run after it is the range name, and the runs after that are the model names.
_TABLE_MARKER = "Prices and technical data"

#: Row labels as the UK price list writes them, mapped to what they mean here. Matched
#: exactly rather than by prefix, because `Prices and technical data` also begins with
#: "Price" and a prefix match finds the page heading instead of the price row.
_PRICE_LABEL = re.compile(r"^Price\s*£$")
_ROW_LABELS: dict[str, str] = {
    "Permitted seats (including driver)*": "seats",
    "Berths": "berths",
    "Length / Width / Height (cm)": "dimensions",
    "Mass in running order* (kg)": "mro",
    "Technically permissible maximum laden mass* (kg)": "mtplm",
    "Standard chassis": "chassis",
}

#: `596 / 214 / 274` — length, width and height in centimetres, in one cell.
_DIMENSIONS = re.compile(r"^(\d+)\s*/\s*(\d+)\s*/\s*(\d+)$")

#: `2657 (2524 to 2790)*` — mass in running order, then the ±5% tolerance band that
#: type approval permits. Both are captured: the band is what the parse is checked
#: against (see `_reconciles`).
_MASS_WITH_BAND = re.compile(r"^(\d+)\s*\((\d+)\s*to\s*(\d+)\)")

#: `58,890.-` — a price in whole pounds, the `.-` standing in for `.00`.
_PRICE = re.compile(r"^([\d,]+)\.-$")

#: `2 - 3 OPT`, `4 - 5 OPT` or plain `4`. The leading figure is the standard
#: configuration; anything after it is reachable only with optional equipment.
_COUNT = re.compile(r"^(\d+)")

#: Price list filenames carry the model year: `reisemobile-mj27-uk.pdf`. Only the UK
#: price lists use this shape — the glossy catalogues on the same page are named
#: differently (`Sunlight-Kat-RM-2024-UK-IRL.pdf`) and have no technical tables.
_PRICE_LIST_HREF_TEMPLATE = r"https://[^\"'\s]*{stem}-mj(\d{{2}})-uk\.pdf[^\"'\s]*"

#: How far Sunlight's published tolerance band may sit from ±5% of the stated mass in
#: running order before the row is treated as misread. The band is rounded to whole
#: kilograms, so a kilogram or two of slack is expected; a column that has slipped is
#: out by far more, since it pairs one model's mass with another's band.
MASS_BAND_TOLERANCE_KG = 3


def _to_int(text: str) -> int:
    return int(text.replace(",", ""))


# --------------------------------------------------------------------------- #
# Finding the current price lists
# --------------------------------------------------------------------------- #


def find_price_list_urls(info_material_html: str, stem: str) -> str | None:
    """The newest UK price list URL for one catalogue, from the info-material page.

    The page lists every model year it has ever published — 2027 down to 2024 at the
    time of writing — so "the first link found" is not the current one and will not
    stay the current one. The `mjNN` in the filename is the model year, and the highest
    wins.

    The URLs are Dropbox share links carrying `rlkey` and `st` query parameters, the
    latter a short-lived token. They therefore cannot be reconstructed or cached
    between runs, which is the other reason this is discovered every time.
    """
    pattern = re.compile(_PRICE_LIST_HREF_TEMPLATE.format(stem=re.escape(stem)))
    matches = [(int(match.group(1)), match.group(0)) for match in pattern.finditer(info_material_html)]
    if not matches:
        return None
    return max(matches, key=lambda match: match[0])[1]


# --------------------------------------------------------------------------- #
# Parsing one "Prices and technical data" page
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SunlightProduct:
    """One layout, as read from one column of a technical-data page."""

    range_label: str
    model: str
    page_number: int
    base_vehicle_manufacturer: str | None = None
    #: The `Standard chassis` cell as printed, e.g. `Fiat Ducato` — kept for the
    #: provenance snippet, since the make alone does not tell a reviewer which of a
    #: make's vans the layout sits on.
    base_vehicle_text: str | None = None
    rrp_pounds: int | None = None
    berths: int | None = None
    berths_text: str | None = None
    mh_passenger_seats_inc_driver: int | None = None
    seats_text: str | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mro_kilograms: int | None = None
    mro_band: tuple[int, int] | None = None
    mtplm_kilograms: int | None = None

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload, which Sunlight does not state directly.

        Derived the same way `adria.py` derives it, from the two masses that *are*
        published. Sunlight's own "manufacturer-specified mass for optional equipment"
        is a different quantity — a cap on factory-fitted extras — and is deliberately
        not used for this.
        """
        if self.mro_kilograms is None or self.mtplm_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms


def _reconciles(product: SunlightProduct) -> bool:
    """Whether the stated mass in running order agrees with its own tolerance band.

    Sunlight prints each mass with the ±5% band type approval allows: `2657 (2524 to
    2790)`. The band is a function of the mass, so the pair has to be self-consistent —
    which makes it a free check that the value was read from the right column, in the
    spirit of Morelo's and Swift's payload arithmetic. Sunlight publishes no payload
    figure to check instead, so without this the adapter would have no self-check at
    all.

    A product with no band recorded passes: there is nothing to contradict.
    """
    if product.mro_kilograms is None or product.mro_band is None:
        return True
    low, high = product.mro_band
    return (
        abs(low - product.mro_kilograms * 0.95) <= MASS_BAND_TOLERANCE_KG
        and abs(high - product.mro_kilograms * 1.05) <= MASS_BAND_TOLERANCE_KG
    )


def _is_row_label(run: str) -> bool:
    """Whether a run opens a row rather than holding a value."""
    return run in _ROW_LABELS or bool(_PRICE_LABEL.match(run))


def _cells_after(runs: list[str], label_index: int, count: int) -> list[str]:
    """Up to `count` value runs following a row's label, stopping at the next row.

    Stopping matters: a plain slice of the next `count` runs will happily swallow the
    *following row's label* when a row is short, padding the list back to `count` and
    defeating the "wrong number of cells" guard that is supposed to catch exactly that.
    The caller then sees a full-looking row with a label where a value should be.
    """
    cells: list[str] = []
    for run in runs[label_index + 1 :]:
        if len(cells) == count or _is_row_label(run):
            break
        cells.append(run)
    return cells


def _cells(runs: list[str], label: str, count: int, *, start: int) -> list[str]:
    """The cells of the row `label` opens, or `[]` if that row isn't present.

    Every table cell is its own run, so a row is simply its label run followed by one
    run per model. Searching from `start` (the table marker) keeps a row label from
    matching an identically-worded run in the page's preamble.
    """
    for index in range(start, len(runs)):
        if runs[index] == label:
            return _cells_after(runs, index, count)
    return []


def _price_cells(runs: list[str], count: int, *, start: int) -> list[str]:
    """The price row's cells. Separate because its label is matched by pattern."""
    for index in range(start, len(runs)):
        if _PRICE_LABEL.match(runs[index]):
            return _cells_after(runs, index, count)
    return []


def parse_technical_page(runs: list[str], page_number: int) -> list[SunlightProduct]:
    """Every layout on one "Prices and technical data" page.

    `runs` is the page's text runs in the order the page draws them, which for these
    tables is reading order. Returns `[]` for a page that doesn't open with the table
    marker, or whose model names can't be read.

    A row whose cell count doesn't match the number of models is skipped rather than
    guessed at — the same rule the Morelo adapter applies, and for the same reason:
    a value attached to the wrong layout is worse than a value left blank.
    """
    if _TABLE_MARKER not in runs:
        return []
    marker = runs.index(_TABLE_MARKER)
    if marker + 2 >= len(runs):
        return []

    range_label = runs[marker + 1]

    # Model names run from just after the range name up to the price row's label,
    # which is the first row of the table proper.
    names: list[str] = []
    for run in runs[marker + 2 :]:
        if _PRICE_LABEL.match(run):
            break
        names.append(run)
    if not names:
        return []

    count = len(names)
    rows = {
        meaning: _cells(runs, label, count, start=marker)
        for label, meaning in _ROW_LABELS.items()
    }
    rows["price"] = _price_cells(runs, count, start=marker)

    def cell(meaning: str, index: int) -> str | None:
        values = rows.get(meaning) or []
        return values[index] if len(values) == count else None

    def matched(meaning: str, index: int, pattern: re.Pattern[str]) -> re.Match[str] | None:
        value = cell(meaning, index)
        return pattern.match(value) if value else None

    products: list[SunlightProduct] = []
    for index, name in enumerate(names):
        dimensions = matched("dimensions", index, _DIMENSIONS)
        mass = matched("mro", index, _MASS_WITH_BAND)
        price = matched("price", index, _PRICE)
        berths = matched("berths", index, _COUNT)
        seats = matched("seats", index, _COUNT)
        mtplm = matched("mtplm", index, _COUNT)
        chassis = cell("chassis", index)

        products.append(
            SunlightProduct(
                range_label=range_label,
                model=name,
                page_number=page_number,
                # "Fiat Ducato" / "Ford Transit" — the make is the first word.
                base_vehicle_manufacturer=fmlv_base_vehicle(chassis.split()[0]) if chassis else None,
                base_vehicle_text=chassis,
                rrp_pounds=_to_int(price.group(1)) if price else None,
                berths=int(berths.group(1)) if berths else None,
                berths_text=cell("berths", index),
                mh_passenger_seats_inc_driver=int(seats.group(1)) if seats else None,
                seats_text=cell("seats", index),
                # Sunlight publishes centimetres; FMLV stores millimetres.
                mh_length_mm=int(dimensions.group(1)) * 10 if dimensions else None,
                mh_width_mm=int(dimensions.group(2)) * 10 if dimensions else None,
                mh_height_mm=int(dimensions.group(3)) * 10 if dimensions else None,
                mro_kilograms=int(mass.group(1)) if mass else None,
                mro_band=(int(mass.group(2)), int(mass.group(3))) if mass else None,
                mtplm_kilograms=int(mtplm.group(1)) if mtplm else None,
            )
        )
    return products


# --------------------------------------------------------------------------- #
# Orchestration: fetch + parse -> ExtractedMotorhome
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(product: SunlightProduct, pdf_url: str) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        rrp_pounds=product.rrp_pounds,
        berths=product.berths,
        mh_passenger_seats_inc_driver=product.mh_passenger_seats_inc_driver,
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

    def record(field: str, snippet: str) -> None:
        provenance[field] = Provenance(source_url=source, snippet=f"{label} — {snippet}")

    if product.base_vehicle_manufacturer is not None:
        record(
            "base_vehicle_manufacturer",
            f"Standard chassis: {product.base_vehicle_text} "
            f"(make taken as {product.base_vehicle_manufacturer})",
        )
    if product.rrp_pounds is not None:
        record("rrp_pounds", f"Price £{product.rrp_pounds:,} (UK & Ireland price list)")
    if product.berths is not None:
        # The cell text is carried through verbatim, because "2 - 3 OPT" says something
        # the single number cannot: the third berth needs optional equipment.
        record("berths", f"Berths: {product.berths_text}")
    if product.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            f"Permitted seats (including driver): {product.seats_text}",
        )
    if product.mro_kilograms is not None and product.mro_band is not None:
        low, high = product.mro_band
        record(
            "mro_kilograms",
            f"Mass in running order: {product.mro_kilograms} kg ({low} to {high} kg permitted)",
        )
    if product.mtplm_kilograms is not None:
        record(
            "mtplm_kilograms",
            f"Technically permissible maximum laden mass: {product.mtplm_kilograms} kg",
        )
    if product.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"{product.mtplm_kilograms} kg laden mass - {product.mro_kilograms} kg "
            f"in running order = {product.mh_payload_kilograms} kg (derived, not stated)",
        )
    for field, axis, value in (
        ("mh_length_mm", "Length", product.mh_length_mm),
        ("mh_width_mm", "Width", product.mh_width_mm),
        ("mh_height_mm", "Height", product.mh_height_mm),
    ):
        if value is not None:
            record(field, f"{axis}: {value // 10} cm")

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Sunlight needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every Sunlight layout from the current UK price lists.

    `ranges` selects which of the two catalogues to read, so `--range "Camper Vans"`
    runs one of them. As with Swift, a "range" at this level is a whole catalogue; the
    model ranges inside it (Van Adventure, CLIFF X, …) come out of the PDF.

    The info-material page is fetched once per catalogue rather than once overall. That
    is one redundant request, in exchange for each catalogue being independently
    runnable and independently skippable when something about it fails.
    """
    results: list[ExtractedMotorhome] = []

    for stem, category in ranges:
        on_progress(f"[{category}] finding the current price list...")
        info = http.fetch(INFO_MATERIAL_URL)
        if info.status_code != 200:
            on_progress(f"[{category}] SKIPPED: {INFO_MATERIAL_URL} returned {info.status_code}")
            continue

        pdf_url = find_price_list_urls(
            info.file_path.read_text(encoding="utf-8", errors="replace"), stem
        )
        if pdf_url is None:
            on_progress(
                f"[{category}] SKIPPED: no '{stem}-mjNN-uk.pdf' link on {INFO_MATERIAL_URL}"
            )
            continue

        on_progress(f"[{category}] downloading {pdf_url} ...")
        pdf = http.fetch(pdf_url)
        if pdf.status_code != 200:
            on_progress(f"[{category}] SKIPPED: price list returned {pdf.status_code}")
            continue

        document = extract_text(pdf.file_path)
        if document.is_empty():
            on_progress(f"[{category}] SKIPPED: no text in the price list PDF")
            continue

        table_pages = [page.page_number for page in document.pages if _TABLE_MARKER in page.text]
        on_progress(
            f"[{category}] {len(table_pages)} technical-data page(s) in {len(document.pages)}"
        )

        for page_number in table_pages:
            runs = [item.text for item in extract_positioned_text(pdf.file_path, page_number)]
            products = parse_technical_page(runs, page_number)
            if not products:
                on_progress(f"  p{page_number} — SKIPPED: no layouts recognised")
                continue
            for product in products:
                label = f"{product.range_label} {product.model}"
                if not _reconciles(product):
                    low, high = product.mro_band or (0, 0)
                    on_progress(
                        f"  p{page_number} {label} — SKIPPED: mass in running order "
                        f"{product.mro_kilograms} kg doesn't match its own ±5% band "
                        f"({low} to {high}), so the columns may be misread"
                    )
                    continue
                results.append(_build_extracted_motorhome(product, pdf_url))
            on_progress(f"  p{page_number} — {products[0].range_label}: {len(products)} layout(s)")

    on_progress(f"{len(results)} product(s) collected")
    return results
