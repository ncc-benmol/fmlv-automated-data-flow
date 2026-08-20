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

Because step 2 *constructs* a URL rather than following a link, this adapter carries
self-checks that others do not need: the spec sheet has to name the layout it was
fetched for, and its two masses have to imply a positive payload. See `collect`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
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

@dataclass(frozen=True)
class RangeConfig:
    """One page to sweep, and how its products are named in the FMLV export.

    `label` and `fmlv_range` are separate because the 60Y anniversary editions need
    them to differ. `label` is the *selector* — what `fmlv run --range` and
    `config/schedule.csv` name, so it has to be unique across `RANGES` — while
    `fmlv_range` is what lands in `Motorhome.manufacturer_range`, and FMLV files the
    60Y editions under the ordinary range (`Matrix`, not `Matrix 60Y`), marking them
    in the *model* instead.
    """

    #: URL path under `BASE_URL`.
    path: str
    #: Unique selector for `--range`; also what `on_progress` narrates.
    label: str
    #: What the NCC export calls this range.
    fmlv_range: str
    #: Appended to the model, e.g. `670 SL` -> `670 SL 60Y`.
    model_suffix: str | None = None
    #: Whether the JSON's trim label forms part of the model name. See `_model_name`.
    model_includes_trim: bool = True


#: Every range this adapter sweeps. The nine ordinary ranges were read off the site's
#: own navigation during the Phase 4 survey and re-confirmed against `/motorhomes` and
#: `/campervans` on 2026-08-20 — still exactly these nine. Not discovered dynamically
#: (yet): a nice follow-up would be to read them off the two index pages instead of
#: hardcoding them, so a new range doesn't need a code change to be picked up. Note
#: that would *not* have found the three 60Y pages below, which are listed in neither
#: index — `docs/adapters/README.md`'s "no single menu is a complete roster" again.
RANGES: tuple[RangeConfig, ...] = (
    RangeConfig("motorhomes/supersonic", "Supersonic", "Supersonic"),
    RangeConfig("motorhomes/sonic", "Sonic", "Sonic"),
    RangeConfig("motorhomes/matrix", "Matrix", "Matrix"),
    RangeConfig("motorhomes/coral", "Coral", "Coral"),
    RangeConfig("motorhomes/compact-max", "Compact Max", "Compact Max"),
    RangeConfig("motorhomes/compact", "Compact", "Compact"),
    RangeConfig("campervans/supertwin", "Supertwin", "Supertwin"),
    RangeConfig("campervans/twin-sports", "Twin Sports", "Twin Sports"),
    RangeConfig("campervans/twin-supreme", "Twin Supreme", "Twin Supreme"),
    # Adria's 60th-anniversary editions, one layout each, on their own `/60y/` pages.
    # They are in no menu and no sitemap entry found, and none of the three appears in
    # its ordinary range's own Livewire payload (checked 2026-08-20: `/motorhomes/matrix`
    # returns seven configurations, none of them the 60Y), so sweeping these pages adds
    # products rather than duplicating any.
    #
    # `fmlv_range`/`model_suffix` are taken from the real FMLV rows, not from the site:
    # product 8195 is range `Matrix`, model `670 SL 60Y`. `model_includes_trim=False`
    # because the JSON's trim label is useless here — it is a different shape on each of
    # the three pages (`60 years RHD`, `Coral 60Y 670 DL`, `Twin 60Y 640 SGX`), and on
    # two of them it merely repeats the layout code. The layout code plus `60Y` is what
    # FMLV holds, and it is also exactly what each PDF titles itself (`MATRIX 670 SL 60Y`).
    RangeConfig("60y/matrix", "Matrix 60Y", "Matrix", model_suffix="60Y", model_includes_trim=False),
    RangeConfig("60y/coral", "Coral 60Y", "Coral", model_suffix="60Y", model_includes_trim=False),
    RangeConfig("60y/twin", "TWIN 60Y", "TWIN", model_suffix="60Y", model_includes_trim=False),
)

#: `(path, label)` pairs, the shape `cli.resolve_ranges` reads with `getattr` and the
#: `Adapter` protocol documents. Derived from `RANGES` so the two can never drift.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = tuple(
    (config.path, config.label) for config in RANGES
)

_RANGE_BY_LABEL: dict[str, RangeConfig] = {config.label: config for config in RANGES}


#: Every model suffix any range uses, for telling a special edition's baseline rows
#: apart from its ordinary range-mates — see `baseline_in_scope`.
_MODEL_SUFFIXES: frozenset[str] = frozenset(
    config.model_suffix.upper() for config in RANGES if config.model_suffix
)


def baseline_in_scope(motorhome: Motorhome, labels: Iterable[str]) -> bool:
    """Whether one baseline row is in scope for a run narrowed to `labels`.

    The opt-in hook `cli.baseline_scope` looks for, and the reason it has to be a
    predicate over rows rather than a set of range names: FMLV does not record 60Y-ness
    in `manufacturer_range` at all, so no filter on that column alone can separate the
    one `Matrix` row that is a 60Y edition from the 27 that are not. The distinction
    lives in `model` (`670 SL 60Y`), so that is what this reads.

    Both directions matter, and getting either wrong is worse than noisy:

    * `--range "Matrix 60Y"` must see baseline row 8195 (`Matrix` / `670 SL 60Y`).
      Filtering on the selector label finds no baseline at all, and a product with no
      baseline to match is classified `NEW_PRODUCT` — which on upload means a duplicate
      of a product the NCC already holds.
    * `--range Matrix` must *not* see it. Every baseline row a narrowed run pulls in but
      does not sweep is reported as `DISAPPEARED` (`diff/classify.py`), so a range
      filter that is too generous manufactures disappearance notices for live products.
    """
    for label in labels:
        config = _RANGE_BY_LABEL.get(label)
        if config is None:
            if motorhome.manufacturer_range == label:
                return True
            continue
        if motorhome.manufacturer_range != config.fmlv_range:
            continue
        model = (motorhome.model or "").upper()
        if config.model_suffix is not None:
            if model.endswith(config.model_suffix.upper()):
                return True
            continue
        if not any(model.endswith(suffix) for suffix in _MODEL_SUFFIXES):
            return True
    return False


def range_config(path: str, label: str) -> RangeConfig:
    """The `RangeConfig` for one `(path, label)` pair as `collect` receives it.

    `collect` takes `(path, label)` pairs rather than `RangeConfig`s so that
    `cli.resolve_ranges` — which knows only the two-element shape — can keep narrowing a
    run to one range. An unrecognised label (a caller passing its own ad hoc pair) falls
    back to treating the label as the FMLV range name, which is what this adapter did
    for every range before the 60Y editions existed.
    """
    config = _RANGE_BY_LABEL.get(label)
    return config if config is not None else RangeConfig(path=path, label=label, fmlv_range=label)

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

#: Each pattern captures the figure in group 1 and then runs to the end of the line, so
#: `PdfSpecMatch.snippet` carries whatever *qualifies* that figure. This matters more
#: here than the bare number does: Adria writes `Nr. of berths 2 (OPTIONAL 3RD BERTH)`
#: and `Nr. of seats 3 AT 3,500KG (4 AT 3,650KG)`, and `docs/adapters/README.md` requires
#: the recorded value to be the base figure (2, 3) *and* the published wording to reach
#: the reviewer. Before this, the snippet stopped at the digit and the qualifier was
#: silently dropped — which on a seats row that differs by chassis rating is the whole
#: story. Same for masses: `Mass in running order (MIRO-min, kg) 3228 (WITHOUT ALL INC'
#: PACK)` says which of Adria's two published figures this is.
_SPEC_PATTERNS: dict[str, re.Pattern[str]] = {
    "mh_length_mm": re.compile(r"Body length \(mm\)\s*(\d+)([^\n]*)"),
    "mh_width_mm": re.compile(r"Total width \(mm\)\s*(\d+)([^\n]*)"),
    "mh_height_mm": re.compile(r"Total height \(mm\)\s*(\d+)([^\n]*)"),
    "mro_kilograms": re.compile(r"Mass in running order \(MIRO-min, kg\)\s*(\d+)([^\n]*)"),
    "mtplm_kilograms": re.compile(r"Max authorised weight \(kg\)\s*(\d+)([^\n]*)"),
    "berths": re.compile(r"Nr\. of berths\s*(\d+)([^\n]*)"),
    "mh_passenger_seats_inc_driver": re.compile(r"Nr\. of seats\s*(\d+)([^\n]*)"),
}

#: The document's own running title, which every page repeats immediately above its
#: `Created date:` footer — `MATRIX SUPREME 670 DC`, `TWIN 640 SGX 60Y`. Anchoring on
#: the footer rather than on "the first line of the file" is what makes this the
#: document *stating* which vehicle it describes, and it is the whole basis of the
#: identity self-check in `pdf_describes_layout`.
_PDF_TITLE = re.compile(r"([^\n]+)\nCreated date:")

#: A chassis section heading: `CA. Fiat Chassis`, `CB. Mercedes Chassis`. The brand as
#: Adria prints it here is already the string FMLV holds in `base_vehicle_manufacturer`
#: — `Fiat`, `Mercedes`, `MAN`, `Renault` are the four in the real baseline export, and
#: `Mercedes` rather than `Mercedes-Benz` matches on both sides. Deliberately *not* read
#: from the `Chassis type ...` line, which gives the chassis *variant* (`special`,
#: `panel van`, `AL - KO`) and not its manufacturer at all.
_CHASSIS_SECTION = re.compile(r"^[A-Z]{1,2}\.\s*([A-Z][A-Za-z-]*)\s+Chassis\s*$", re.MULTILINE)


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

    Where a row publishes a base figure and a qualified alternative, group 1 takes the
    base one per `docs/adapters/README.md` and the qualifier is preserved in the
    snippet — see `_SPEC_PATTERNS`.
    """
    matches: dict[str, PdfSpecMatch] = {}
    for field_name, pattern in _SPEC_PATTERNS.items():
        match = pattern.search(text)
        if match:
            matches[field_name] = PdfSpecMatch(
                value=int(match.group(1)),
                snippet=" ".join(match.group(0).split()),
            )
    return matches


def pdf_title(text: str) -> str | None:
    """The vehicle the spec sheet says it describes, or `None` if it doesn't say."""
    match = _PDF_TITLE.search(text)
    return " ".join(match.group(1).split()) if match else None


def pdf_describes_layout(text: str, layout_label: str | None) -> bool | None:
    """Whether this PDF's own title names the layout it was fetched for.

    `True`/`False` when the question can be answered, `None` when it cannot — the
    document carries no recognisable title, or the JSON gave no layout label to check
    against. The three outcomes are genuinely different to a caller: a `False` is
    positive evidence that a product's weights and dimensions belong to a *different*
    vehicle, which is the one failure mode of this adapter that nothing downstream could
    catch (see `collect`), while a `None` is only an unanswered question.
    """
    if not layout_label:
        return None
    title = pdf_title(text)
    if title is None:
        return None
    return " ".join(layout_label.split()).upper() in title.upper()


def parse_base_vehicle_manufacturer(text: str) -> str | None:
    """The chassis manufacturer, from the spec sheet's own chassis section headings.

    A sheet repeats the heading once per page the section spans, so several matches are
    normal and expected to be identical. Two *different* brands in one document is not
    something any surveyed sheet does; it would mean the heading pattern is matching
    something other than the chassis section, so the field is left unset rather than
    guessed from the first hit.
    """
    brands = {match.group(1) for match in _CHASSIS_SECTION.finditer(text)}
    return brands.pop() if len(brands) == 1 else None


# --------------------------------------------------------------------------- #
# Orchestration: fetch + parse -> ExtractedMotorhome
# --------------------------------------------------------------------------- #


def _model_name(product: LivewireProduct, config: RangeConfig) -> str | None:
    """The model as FMLV writes it: layout code, the trim where it means something, suffix.

    The trim is part of the identity for an ordinary range, where one layout is sold in
    several trims that differ in price and weight (`670 DC` in `Supreme Alde RHD`), but
    not for a one-layout special edition — see `RANGES`.
    """
    parts = [product.layout_label]
    if config.model_includes_trim:
        parts.append(product.trim_label)
    parts.append(config.model_suffix)
    return " ".join(part for part in parts if part) or None


def cross_source_disagreements(
    product: LivewireProduct, pdf_specs: dict[str, PdfSpecMatch]
) -> dict[str, tuple[int, int]]:
    """Fields where the range page's JSON and the spec-sheet PDF disagree.

    Keyed by field name, valued `(JSON figure, PDF figure)`. Only fields *both* sources
    publish are compared — the JSON omits seats entirely on every range surveyed, and
    omits berths on some.

    This is the redundancy `docs/adapters/README.md` asks every adapter to find. Adria
    publishes no payload to reconcile against its two masses, and the one figure that
    would (`Max loading weight ... with All Inclusive Pack weight deducted`) measures
    something subtly different, so the check that is available here is a cross-*source*
    one rather than an arithmetic one: two independently maintained descriptions of the
    same configuration, one of which the adapter reached by constructing a URL.
    """
    disagreements: dict[str, tuple[int, int]] = {}
    for field_name, json_value in (
        ("berths", product.berths),
        ("mh_passenger_seats_inc_driver", product.seats),
    ):
        match = pdf_specs.get(field_name)
        if json_value is not None and match is not None and match.value != json_value:
            disagreements[field_name] = (json_value, match.value)
    return disagreements


def _build_extracted_motorhome(
    product: LivewireProduct,
    config: RangeConfig,
    range_url: str,
    pdf_url: str,
    pdf_specs: dict[str, PdfSpecMatch],
    base_vehicle_manufacturer: str | None,
    disagreements: dict[str, tuple[int, int]],
) -> ExtractedMotorhome:
    def spec(field_name: str) -> int | None:
        match = pdf_specs.get(field_name)
        return match.value if match else None

    mro = spec("mro_kilograms")
    mtplm = spec("mtplm_kilograms")

    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=config.fmlv_range,
        model=_model_name(product, config),
        base_vehicle_manufacturer=base_vehicle_manufacturer,
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
        snippet = match.snippet
        if field_name in disagreements:
            json_value, _pdf_value = disagreements[field_name]
            # The reviewer decides this one, so both figures have to reach them. The
            # PDF's is recorded because it is the homologation document; the range
            # page's is the one a customer sees, and their differing is the finding.
            snippet = (
                f"{snippet} — note: the range page's own listing says {json_value} "
                f"for this configuration"
            )
        provenance[field_name] = Provenance(source_url=pdf_url, snippet=snippet)
    if base_vehicle_manufacturer is not None:
        provenance["base_vehicle_manufacturer"] = Provenance(
            source_url=pdf_url,
            snippet=f"chassis section heading: '{base_vehicle_manufacturer} Chassis'",
        )
    if motorhome.mh_payload_kilograms is not None:
        provenance["mh_payload_kilograms"] = Provenance(
            source_url=pdf_url,
            snippet=(
                f"derived: {mtplm}kg max authorised weight - {mro}kg mass in running "
                f"order = {motorhome.mh_payload_kilograms}kg (not published directly)"
            ),
        )

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
    fetch, a PDF that yielded no spec fields (see `_SPEC_PATTERNS`), or one that failed
    a self-check. None of those raise, by design (a mid-sweep parser hiccup shouldn't
    abort every other product), which is exactly why they're worth narrating rather than
    only being visible after the fact by diffing snapshot counts. Defaults to a no-op so
    calling this from a test, or any caller that doesn't want console output, needs
    nothing extra; `cli.py` wires this to `print` for an interactive `fmlv run`.

    **The self-checks, and why two of them drop a product where the third does not.**
    This adapter reaches its numbers by *constructing* a URL out of an id, which no
    other adapter does, so the failure it has to defend against is a whole spec sheet
    belonging to the wrong vehicle — plausible, internally consistent, and invisible
    downstream. A product is therefore dropped when:

    * **the PDF's own title does not name the layout it was fetched for**
      (`pdf_describes_layout`) — direct evidence of exactly that failure; or
    * **mass in running order is not below max authorised weight**, which makes the
      derived payload zero or negative. That is arithmetically impossible for a real
      vehicle, so it means a mis-parse, and a negative payload would sail through
      `validation.py`'s `payload == mtplm - mro` reconciliation check by construction.

    A **cross-source disagreement** on berths or seats (`cross_source_disagreements`)
    only warns, and the product is still proposed. Once the title check has confirmed
    the document is the right vehicle's, the remaining explanation is a definitional
    difference between the two sources rather than a misattribution — Adria's own seats
    row varies by chassis rating, for instance — and dropping the product would throw
    away a correct price and correct dimensions over a question a reviewer is better
    placed to settle. Both figures go into the provenance snippet instead.
    """
    results: list[ExtractedMotorhome] = []

    for range_path, range_label in ranges:
        config = range_config(range_path, range_label)
        range_url = f"{BASE_URL}/{config.path}"
        on_progress(f"[{config.label}] loading range page...")
        _page_result, captured = browser.fetch_with_capture(
            range_url, capture_url_contains=_LIVEWIRE_UPDATE_MARKER, scroll=True
        )
        if not captured:
            on_progress(
                f"[{config.label}] WARNING: the range page made no {_LIVEWIRE_UPDATE_MARKER} "
                f"call, so it yielded no configurations — the layout-selector component "
                f"may have moved, or never scrolled into view"
            )
        for response in captured:
            products = parse_livewire_products(response.file_path.read_bytes())
            on_progress(f"[{config.label}] {len(products)} configuration(s) found")
            for index, product in enumerate(products, start=1):
                label = " / ".join(
                    part for part in (product.layout_label, product.trim_label) if part
                ) or product.product_id
                prefix = f"[{config.label}] ({index}/{len(products)}) {label}"

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

                describes = pdf_describes_layout(pdf_text, product.layout_label)
                if describes is False:
                    on_progress(
                        f"{prefix} — SKIPPED: the spec sheet at {pdf_url} calls itself "
                        f"'{pdf_title(pdf_text)}', which does not name layout "
                        f"'{product.layout_label}' — it is a different vehicle's document"
                    )
                    continue
                if describes is None:
                    on_progress(
                        f"{prefix} — WARNING: could not confirm from the PDF's own title "
                        f"that it describes this layout"
                    )

                pdf_specs = parse_technical_data_pdf(pdf_text)
                if not pdf_specs:
                    on_progress(f"{prefix} — WARNING: no spec fields found in PDF text")

                mro = pdf_specs.get("mro_kilograms")
                mtplm = pdf_specs.get("mtplm_kilograms")
                if mro is not None and mtplm is not None and mro.value >= mtplm.value:
                    on_progress(
                        f"{prefix} — SKIPPED: mass in running order ({mro.value}kg) is not "
                        f"below max authorised weight ({mtplm.value}kg), so the payload "
                        f"would be {mtplm.value - mro.value}kg — the masses have mis-parsed"
                    )
                    continue

                disagreements = cross_source_disagreements(product, pdf_specs)
                for field_name, (json_value, pdf_value) in disagreements.items():
                    on_progress(
                        f"{prefix} — WARNING: {field_name} is {pdf_value} in the spec sheet "
                        f"but {json_value} on the range page; recording the spec sheet's "
                        f"figure and showing both to the reviewer"
                    )

                results.append(
                    _build_extracted_motorhome(
                        product,
                        config,
                        range_url,
                        pdf_url,
                        pdf_specs,
                        parse_base_vehicle_manufacturer(pdf_text),
                        disagreements,
                    )
                )

    on_progress(f"{len(results)} product(s) collected")
    return results
