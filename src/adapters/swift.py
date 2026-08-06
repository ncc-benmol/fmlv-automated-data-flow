"""Swift Group (swiftgroup.co.uk) — the third adapter, motorhomes and campervans.

See `docs/adapters/swift.md` for the full write-up. Swift confirms the pattern Morelo
suggested: **look for a brochure before surveying the website.** Each of the two index
pages links one brochure PDF directly (no form, no login), and at the back of each is a
"Specification at a glance" table covering every layout the range sells:

    475 Ford 130 Bhp 165 Bhp Auto 2.0ltr 360Nm 1 4.52m 5 5 7.54m 2.37m 2.98m Thule ...
    475 3550kg+ 3094kg‡ 456kg‡ 2000kg 5500kg THREE Truma Neo 12"

Two fetches per *catalogue*, and the richest per-product data of the three
manufacturers surveyed: berths, seat belts, length, width, height, MTPLM, MRO and
payload, all published for every layout.

The two brochures are laid out differently and the adapter handles both:

* **Motorhomes** split the data across *two* tables — dimensions and berths in one,
  weights in another — keyed by range and layout number, and joined back together here.
* **Campervans** put all of it in one table, and their models are named (`Trekker XL`)
  rather than numbered.

Parsing is anchored on each row's *tail* rather than counted across columns. A row's
leading columns are engine prose of unpredictable width (`165 Bhp Auto` against
`130 Bhp` against `N/A`), but its trailing columns are a fixed run of typed values —
metres, then integers, then a known literal. Anchoring there means the variable part
never has to be parsed at all. As with Morelo, Swift publishes MTPLM, MRO *and*
payload, so the arithmetic reconciles as a self-check on the join.

Not extracted: price. Neither brochure quotes one anywhere (the motorhome PDF contains
a single "£", in unrelated prose) — see the write-up.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.swiftgroup.co.uk"
MANUFACTURER = "Swift Group Ltd"
MANUFACTURER_DISPLAY_NAME = "Swift"

#: (index page path, category label). Both are ordinary server-rendered pages whose
#: only job here is to name the current brochure — the layout data is entirely in the
#: PDFs. Campervans are included on the same basis as Adria's: FMLV treats them as
#: motorhomes, and the export's Adria rows cover both.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes", "Motorhomes"),
    ("campervans", "Campervans"),
)

#: The brochure link on each index page, e.g.
#: `/media/noeb4jei/2026_swift_motorhome_brochure.pdf`. The directory segment is an
#: opaque, changing media key and the filename carries the model year, so this is
#: matched per run rather than hardcoded.
_BROCHURE_HREF = re.compile(r"""["'](/media/[^"']+_brochure\.pdf)["']""", re.IGNORECASE)

_SPEC_TABLE_MARKER = "Specification at a glance"

#: A range heading inside the spec table: a short line of letters, no figures. Sits on
#: its own line above that range's layout rows (`Voyager`, `Kon-Tiki`, `Carrera`).
#: Deliberately not a hardcoded list of range names, so a new Swift range is picked up
#: without a code change.
_RANGE_HEADING = re.compile(r"^[A-Z][A-Za-z][A-Za-z\- ]{0,18}$")

#: `4.52m 5 5 7.54m 2.37m 2.98m` — wheelbase, belts, berths, then L/W/H. The shared
#: tail of every layout row in both brochures, and the anchor everything hangs off.
_DIMENSIONS_TAIL = (
    r"(\d+\.\d{2})m\s+(\d+)\s+(\d+)\s+(\d+\.\d{2})m\s+(\d+\.\d{2})m\s+(\d+\.\d{2})m"
)

#: Where a row's engine columns begin, and therefore where its model name ends. Needed
#: because a model name is not always one token: the campervans are `Trekker`,
#: `Trekker X` and `Trekker XL`, and a lazy match without this stops at `Trekker` and
#: collapses all three into one product. The chassis make is matched as a capitalised
#: word of three letters or more precisely so that `X` and `XL` are not mistaken for
#: one — Swift writes `475 Ford 130 Bhp` but `Trekker X 165 Bhp`, with no make at all.
_ENGINE_COLUMN = r"(?=[A-Z][a-z]{2,}\s+\d+\s*Bhp|\d+\s*Bhp)"

#: Motorhome dimensions row. Anchored on the awning column's `Thule` literal, which
#: marks the end of the run and stops the match from wandering into the next row.
_MOTORHOME_DIMENSIONS_ROW = re.compile(
    rf"^(.+?)\s+{_ENGINE_COLUMN}.*?{_DIMENSIONS_TAIL}\s+Thule"
)

#: Motorhome weights row (a separate table): MTPLM, MRO, payload, then trailer and
#: train weights. `\S*` after *every* `kg` absorbs Swift's footnote marks, which are
#: not confined to the three columns actually read — `3550kg+`, `3094kg‡`, `343kg△`,
#: but also `2000kg#` and `5500kg#` on the trailing two. Requiring those last two to
#: be unmarked silently dropped every Escape and Kon-Tiki weight.
_MOTORHOME_WEIGHTS_ROW = re.compile(
    r"^(.+?)\s+(\d+)kg\S*\s+(\d+)kg\S*\s+(\d+)kg\S*\s+(\d+)kg\S*\s+(\d+)kg\S*\s"
)

#: Campervan row — one table, so the dimensions tail is followed directly by the three
#: weights. No `Thule` column to anchor on; the three `kg` figures end the row instead.
_CAMPERVAN_ROW = re.compile(
    rf"^(.+?)\s+{_ENGINE_COLUMN}.*?{_DIMENSIONS_TAIL}"
    rf"\s+(\d+)kg\S*\s+(\d+)kg\S*\s+(\d+)kg\S*\s*$"
)


def _metres_to_mm(metres: str) -> int:
    """`'7.54'` -> `7540`. Swift publishes dimensions in metres, FMLV stores mm."""
    return round(float(metres) * 1000)


@dataclass(frozen=True)
class SwiftProduct:
    """One layout, as read from the brochure's specification table."""

    range_label: str
    model: str
    berths: int | None = None
    mh_passenger_seats_inc_driver: int | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    mh_payload_kilograms: int | None = None

    @property
    def key(self) -> tuple[str, str]:
        """What the motorhome brochure's two tables are joined on."""
        return self.range_label, self.model


def _reconciles(product: SwiftProduct) -> bool:
    """Whether Swift's own three weights agree: payload == MTPLM - MRO.

    Swift publishes all three independently, so this is a free check on the join
    between the motorhome brochure's two tables: pair the wrong layout's weights to a
    set of dimensions and the identity is very unlikely to survive. A product missing
    any of the three passes, having nothing to contradict.

    Swift rounds and annotates some figures (`*` marks an estimate, `†`/`‡` flag an
    automatic-transmission adjustment applied to MRO and payload together), so a small
    discrepancy is expected and tolerated rather than treated as a parse failure.
    """
    mtplm, mro, payload = (
        product.mtplm_kilograms,
        product.mro_kilograms,
        product.mh_payload_kilograms,
    )
    if mtplm is None or mro is None or payload is None:
        return True
    return abs((mtplm - mro) - payload) <= WEIGHT_TOLERANCE_KG


#: How far Swift's published payload may sit from `MTPLM - MRO` before the row is
#: treated as misparsed rather than merely rounded. A genuine row mismatch pairs two
#: different layouts and is out by tens or hundreds of kg, so this stays tight.
WEIGHT_TOLERANCE_KG = 2


# --------------------------------------------------------------------------- #
# Finding the brochures
# --------------------------------------------------------------------------- #


def find_brochure_url(index_html: str) -> str | None:
    """The absolute URL of the brochure linked from one index page.

    Returns `None` rather than guessing at a URL: the media path is an opaque key that
    cannot be reconstructed, so a missing link means the page changed and is worth
    reporting as such.
    """
    match = _BROCHURE_HREF.search(index_html)
    return f"{BASE_URL}{match.group(1)}" if match else None


# --------------------------------------------------------------------------- #
# Parsing the specification tables
# --------------------------------------------------------------------------- #


def _rows(text: str, pattern: re.Pattern[str]) -> list[tuple[str, str, re.Match[str]]]:
    """Every line matching `pattern`, tagged with the range heading above it.

    One pass, tracking the most recent heading. A line that is neither a layout row nor
    a heading — the footnotes and legend that share these pages — is skipped, and a
    layout row appearing before any heading is dropped rather than filed under a made-up
    range.
    """
    found: list[tuple[str, str, re.Match[str]]] = []
    range_label: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = pattern.match(stripped)
        if match:
            if range_label is not None:
                found.append((range_label, match.group(1).strip(), match))
            continue
        if _RANGE_HEADING.match(stripped):
            range_label = stripped
    return found


def parse_motorhome_specs(text: str) -> list[SwiftProduct]:
    """Every motorhome layout, joining the brochure's dimensions and weights tables.

    The two tables list the same layouts in the same order under the same range
    headings, but they are separate tables — so they are joined on (range, layout)
    rather than by position. A layout in only one of the two still comes back, carrying
    whichever half was published; a half-known product is worth reviewing, and the
    fields it lacks simply propose no change.
    """
    products: dict[tuple[str, str], SwiftProduct] = {}

    for range_label, model, match in _rows(text, _MOTORHOME_DIMENSIONS_ROW):
        _wheelbase, belts, berths, length, width, height = match.groups()[1:]
        product = SwiftProduct(
            range_label=range_label,
            model=model,
            berths=int(berths),
            mh_passenger_seats_inc_driver=int(belts),
            mh_length_mm=_metres_to_mm(length),
            mh_width_mm=_metres_to_mm(width),
            mh_height_mm=_metres_to_mm(height),
        )
        products[product.key] = product

    for range_label, model, match in _rows(text, _MOTORHOME_WEIGHTS_ROW):
        mtplm, mro, payload = (int(value) for value in match.groups()[1:4])
        key = (range_label, model)
        existing = products.get(key) or SwiftProduct(range_label=range_label, model=model)
        products[key] = replace(
            existing,
            mtplm_kilograms=mtplm,
            mro_kilograms=mro,
            mh_payload_kilograms=payload,
        )

    return list(products.values())


def parse_campervan_specs(text: str) -> list[SwiftProduct]:
    """Every campervan layout. One table, so no join — every field comes off one row."""
    products: list[SwiftProduct] = []
    for range_label, model, match in _rows(text, _CAMPERVAN_ROW):
        _wheelbase, belts, berths, length, width, height, mtplm, mro, payload = match.groups()[1:]
        products.append(
            SwiftProduct(
                range_label=range_label,
                model=model,
                berths=int(berths),
                mh_passenger_seats_inc_driver=int(belts),
                mh_length_mm=_metres_to_mm(length),
                mh_width_mm=_metres_to_mm(width),
                mh_height_mm=_metres_to_mm(height),
                mtplm_kilograms=int(mtplm),
                mro_kilograms=int(mro),
                mh_payload_kilograms=int(payload),
            )
        )
    return products


# --------------------------------------------------------------------------- #
# Orchestration: fetch + parse -> ExtractedMotorhome
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(product: SwiftProduct, brochure_url: str) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        berths=product.berths,
        mh_passenger_seats_inc_driver=product.mh_passenger_seats_inc_driver,
        mro_kilograms=product.mro_kilograms,
        mtplm_kilograms=product.mtplm_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=product.mh_length_mm,
        mh_width_mm=product.mh_width_mm,
        mh_height_mm=product.mh_height_mm,
    )

    label = f"{product.range_label} {product.model}"
    snippets = {
        "berths": ("Berths", product.berths),
        "mh_passenger_seats_inc_driver": ("Seat Belts", product.mh_passenger_seats_inc_driver),
        "mh_length_mm": ("Overall Length", product.mh_length_mm),
        "mh_width_mm": ("Overall Width", product.mh_width_mm),
        "mh_height_mm": ("Overall Height", product.mh_height_mm),
        "mtplm_kilograms": ("Standard MTPLM", product.mtplm_kilograms),
        "mro_kilograms": ("Standard MRO", product.mro_kilograms),
        "mh_payload_kilograms": ("Standard Max User Payload", product.mh_payload_kilograms),
    }
    provenance = {
        field: Provenance(
            source_url=brochure_url,
            snippet=f"{label} — Specification at a glance, {column}: {value}",
        )
        for field, (column, value) in snippets.items()
        if value is not None
    }

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Swift needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every Swift motorhome and campervan layout from the current brochures.

    `ranges` selects which of the two catalogues to read, so `--range Campervans` runs
    one of them — the same escape hatch `cli.resolve_ranges` offers for Adria. Note
    that a Swift "range" at this level is a whole catalogue, not a model range; the
    model ranges inside it (Voyager, Carrera, …) are discovered from the brochure.

    A catalogue that can't be read is narrated and skipped rather than raised, so a
    change to one brochure doesn't cost the other.
    """
    results: list[ExtractedMotorhome] = []

    for path, category in ranges:
        index_url = f"{BASE_URL}/{path}/"
        on_progress(f"[{category}] finding the current brochure...")
        index = http.fetch(index_url)
        if index.status_code != 200:
            on_progress(f"[{category}] SKIPPED: {index_url} returned {index.status_code}")
            continue

        brochure_url = find_brochure_url(index.file_path.read_text(encoding="utf-8", errors="replace"))
        if brochure_url is None:
            on_progress(f"[{category}] SKIPPED: no brochure link found on {index_url}")
            continue

        on_progress(f"[{category}] downloading {brochure_url} ...")
        brochure = http.fetch(brochure_url)
        if brochure.status_code != 200:
            on_progress(f"[{category}] SKIPPED: brochure returned {brochure.status_code}")
            continue

        document = extract_text(brochure.file_path)
        spec_text = "\n".join(
            page.text for page in document.pages if _SPEC_TABLE_MARKER in page.text
        )
        if not spec_text:
            on_progress(
                f"[{category}] SKIPPED: no '{_SPEC_TABLE_MARKER}' page in the brochure"
            )
            continue

        parse = parse_campervan_specs if path == "campervans" else parse_motorhome_specs
        products = parse(spec_text)
        on_progress(f"[{category}] {len(products)} layout(s) found")

        for product in products:
            label = f"{product.range_label} {product.model}"
            if not _reconciles(product):
                on_progress(
                    f"[{category}] {label} — SKIPPED: weights don't reconcile "
                    f"({product.mtplm_kilograms} - {product.mro_kilograms} != "
                    f"{product.mh_payload_kilograms}), so the tables may be misjoined"
                )
                continue
            results.append(_build_extracted_motorhome(product, brochure_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
