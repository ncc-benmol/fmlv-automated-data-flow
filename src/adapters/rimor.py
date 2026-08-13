"""Rimor (rimor.it) — the fifth adapter, Italian coachbuilts and vans.

See `docs/adapters/rimor.md` for the full write-up. Rimor is the first manufacturer to
invert the rule at the top of `docs/adapters/README.md` — but not for the obvious
reason. Its catalogue is *richer* than the website, not thinner: it adds wheelbase,
MTPLM, engine, tanks and equipment. It loses on **attribution**. Its spec pages put two
or three models side by side and print a value once where it spans several columns, and
pypdf returns the whole row as one run, so no number can be tied to one model (see
`parse_catalogue`). The website gives every layout its own page, which makes attribution
free, and is fully server-rendered — no JavaScript, no login, no AJAX.

41 layouts across 5 ranges, from three levels of plain HTML:

    /int/en/gamma/<range>                    body-style links + the range leaflet PDF
      /int/en/gamma/<range>/<body-style>     the model cards (name, seats, berths)
        /int/en/gamma/<range>/modello/<slug> dimensions, bedding solution

Three things shape this adapter:

* **Body type comes free from the URL.** `/low-profile`, `/overcab` and `/vans` map
  straight onto `BodyType`. No other manufacturer surveyed hands this over so cleanly.
* **Rimor publishes no price and no payload.** This one *is* about availability rather
  than parsing: no price, mass in running order or payload figure appears in the HTML,
  the leaflets or the catalogue, so `rrp_pounds`, `mro_kilograms` and
  `mh_payload_kilograms` are never proposed. The catalogue does give MTPLM and the base
  chassis — see `parse_catalogue` — and MTPLM is 3500 kg for every layout Rimor makes.
* **The self-check is cross-document.** There is no payload arithmetic to lean on, so
  each layout's `length x width` is checked against the range leaflet, which publishes
  the same pairs independently. Compared as an unordered multiset, never by position —
  the leaflets extract in scrambled reading order.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.enums import BedType, BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.rimor.it"
MANUFACTURER = "Rimor"
MANUFACTURER_DISPLAY_NAME = "Rimor"

#: `(range slug, label)`. There is no models index on the site — `/int/en/gamma` is a
#: 404 and there is no sitemap — so the five ranges are listed here rather than
#: discovered. The label is also the `manufacturer_range` written to the product.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("horus", "Horus"),
    ("kilig", "Kilig"),
    ("sarus", "Sarus"),
    ("sailer", "Sailer"),
    ("super-brig", "Super Brig"),
)

#: The body-style URL segment *is* the body type. Any other segment is not a body-style
#: page and is skipped, so a new one appearing does not silently become the wrong type.
BODY_TYPES: dict[str, BodyType] = {
    "low-profile": BodyType.COACH_BUILT_LOW_PROFILE,
    "overcab": BodyType.COACH_BUILT_OVER_CAB_BED,
    "vans": BodyType.CAMPERVAN,
}

#: "Bedding solution : Twin beds" -> the FMLV bed type. Ordered longest-first, because
#: several of these are prefixes of each other: matching `Double bed` before
#: `Double bunk beds` or `Double superimposed bunk beds` turns a bunk layout into a
#: fixed one. A solution matching nothing here leaves `bed_types` empty and is narrated,
#: rather than being guessed at.
BEDDING_SOLUTIONS: tuple[tuple[str, BedType], ...] = (
    ("double superimposed bunk beds", BedType.FIXED_BUNKS),
    ("xl front drop-down bed", BedType.DROP_DOWN),
    ("two drop-down beds", BedType.DROP_DOWN),
    ("double drop-down beds", BedType.DROP_DOWN),
    ("front drop-down bed", BedType.DROP_DOWN),
    ("double bunk beds", BedType.FIXED_BUNKS),
    ("drop-down bed", BedType.DROP_DOWN),
    ("transverse bed", BedType.TRANSVERSE),
    ("rear suite bed", BedType.FIXED),
    ("central bed", BedType.ISLAND),
    ("island bed", BedType.ISLAND),
    ("french bed", BedType.FIXED),
    ("bunk beds", BedType.FIXED_BUNKS),
    ("twin beds", BedType.FIXED_SEPARATE),
    ("double bed", BedType.FIXED),
)

#: Where the catalogue PDF lives. It is linked from **no page on the site** — the
#: "browse the catalogue" button leads to a lead-generation form, while the PDF itself
#: is unauthenticated at this path — so unlike every other adapter the URL cannot be
#: rediscovered per run and has to be probed. Both the season and the per-language
#: version move, hence `catalogue_urls`.
CATALOGUE_PATH = (
    "/public/local/simplex/Marchi/rimor/Lingue/catalogo/raw/RIMOR - Catalogo {season} - EU - V{version}.pdf"
)

#: Highest catalogue version to probe down from. Versions have reached V7, so this
#: leaves headroom without making the probe unreasonably chatty: a miss costs at most
#: `MAX_CATALOGUE_VERSION` requests per season, once per run rather than per range.
MAX_CATALOGUE_VERSION = 9

#: Vehicle dimensions in a leaflet or catalogue read as `6970x2340`. Bed and garage
#: openings use the same notation (`1280x850`), so candidates are filtered to plausible
#: vehicle sizes before being compared.
_PAIR = re.compile(r"\b(\d{4})\s*x\s*(\d{4})\b")
_MIN_LENGTH_MM, _MAX_LENGTH_MM = 5000, 8000
_MIN_WIDTH_MM, _MAX_WIDTH_MM = 2000, 2500

#: The overview block on a model page. Scoping to it is not optional: every model page
#: also carries an "other range models" list whose cards repeat the same seats/berths
#: markup for *every other layout in the range*, and an unscoped match takes whichever
#: comes first in the file.
_OVERVIEW = re.compile(r'id="panoramica-modello"(.*?)END PANORAMICA MODELLO', re.S)

#: Seats and berths are distinguishable **only** by these Italian `title` attributes.
#: The site is in English but the attributes are not translated, and the two spans are
#: otherwise identical. Never read them by position.
_SEATS_TITLE = "numero posti omologati"
_BERTHS_TITLE = "numero posti letto"

_MODEL_CARD = re.compile(
    r'href="(/int/en/gamma/[a-z-]+/modello/[^"]+)"[^>]*class="stretched-link[^"]*"[^>]*>\s*([^<]+?)\s*</a>'
)
_BODY_STYLE_LINK = re.compile(r'href="/int/en/gamma/([a-z-]+)/([a-z-]+)"')
_LEAFLET_LINK = re.compile(r'href="(/public/[^"]+\.pdf)"')

_RANGE_NAME = re.compile(r'class="gamma[^"]*"[^>]*>\s*([^<]+?)\s*</a>')
_MODEL_NAME = re.compile(r'<div class="modello">\s*([^<]+?)\s*</div>')
_BODY_STYLE_OF_MODEL = re.compile(r'href="/int/en/gamma/[a-z-]+/([a-z-]+)"[^>]*class="tipologia')

_LENGTH = re.compile(r"outside length</td>\s*<td[^>]*>\s*(\d+)\s*mm", re.S)
_WIDTH = re.compile(r"outside width - inside width</td>\s*<td[^>]*>\s*(\d+)\s*-\s*(\d+)\s*mm", re.S)
_HEIGHT = re.compile(
    r"maximum outside height\s*-?\s*inside height</td>\s*<td[^>]*>\s*(\d+)\s*-\s*(\d+)\s*mm", re.S
)
_BEDDING = re.compile(r"Bedding solution\s*</span>\s*:\s*<span>\s*([^<]+?)\s*</span>", re.S)

#: `4`, `4 (+1 opt)`, `4 (+ 2 opt)`, `4 (+2+1 opt)`, `6 (+1 opt 4400 kg)`. The standard
#: figure is the leading integer; everything after it needs optional equipment (or, in
#: the last case, an uprated chassis) and is deliberately dropped — the same convention
#: `sunlight.py` applies to its `2 - 3 OPT` cells.
_COUNT = re.compile(r"^\s*(\d+)")

#: Catalogue spec pages. Both values taken from them are constant down the whole page,
#: which is what makes them safe: pypdf returns an entire spec row as one text run
#: (`'Outside length (mm) 5413 5998'` for three models), so per-model column alignment
#: is unrecoverable and nothing that varies per column may be read. See `parse_catalogue`.
_SPEC_PAGE_MARKER = "DIMENSIONS AND WEIGHTS"
_CATALOGUE_MTPLM = re.compile(r"Maximum overall weight \(kg\)\s+(\d+)")
_CATALOGUE_ENGINE = re.compile(r"Engine\s+([A-Za-z][A-Za-z ]*?)\s*\n")


def _titled_value(title: str) -> re.Pattern[str]:
    """Matches the value span belonging to the `caratteristica-modello` named `title`."""
    return re.compile(
        rf'title="{re.escape(title)}".*?valore-caratteristica-modello">\s*([^<]*?)\s*</span>',
        re.S,
    )


_SEATS = _titled_value(_SEATS_TITLE)
_BERTHS = _titled_value(_BERTHS_TITLE)


def _leading_int(text: str | None) -> int | None:
    if not text:
        return None
    match = _COUNT.match(text)
    return int(match.group(1)) if match else None


def _is_vehicle_pair(length: int, width: int) -> bool:
    return _MIN_LENGTH_MM <= length <= _MAX_LENGTH_MM and _MIN_WIDTH_MM <= width <= _MAX_WIDTH_MM


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RimorCard:
    """One layout as advertised on a body-style listing page.

    Carries the seats and berths a second time so they can be checked against the
    model's own page — see `_reconciles`.
    """

    url: str
    name: str
    seats: int | None
    berths: int | None


@dataclass(frozen=True)
class RimorModel:
    """One layout, from its own page plus the card that linked to it."""

    range_label: str
    model: str
    url: str
    body_type: BodyType | None = None
    body_style: str | None = None
    mh_passenger_seats_inc_driver: int | None = None
    seats_text: str | None = None
    berths: int | None = None
    berths_text: str | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    bedding_solution: str | None = None
    bed_types: list[BedType] = field(default_factory=list)
    #: Repeated from the listing card, purely so the two can be compared.
    card_seats: int | None = None
    card_berths: int | None = None

    @property
    def dimensions(self) -> tuple[int, int] | None:
        if self.mh_length_mm is None or self.mh_width_mm is None:
            return None
        return (self.mh_length_mm, self.mh_width_mm)


def parse_body_style_links(range_html: str, range_slug: str) -> list[str]:
    """The body-style segments linked from one range page, in page order.

    Only segments in `BODY_TYPES` are returned. A new one would otherwise have no body
    type to map to, and guessing is worse than skipping it loudly.
    """
    seen: list[str] = []
    for slug, segment in _BODY_STYLE_LINK.findall(range_html):
        if slug == range_slug and segment in BODY_TYPES and segment not in seen:
            seen.append(segment)
    return seen


def parse_leaflet_url(range_html: str) -> str | None:
    """The range leaflet PDF linked from a range page, if there is one."""
    match = _LEAFLET_LINK.search(range_html)
    return match.group(1) if match else None


def parse_model_cards(body_style_html: str) -> list[RimorCard]:
    """Every model card on a body-style listing page.

    The model list is rendered **twice** — once in the main content and once again in a
    footer block — so cards are deduplicated on URL. Slugs are not all numeric
    (`modello/5` sits beside `modello/66-plus` and `modello/suite`), which is why the
    pattern does not anchor on digits.
    """
    cards: dict[str, RimorCard] = {}
    for match in _MODEL_CARD.finditer(body_style_html):
        url, name = match.group(1), match.group(2)
        if url in cards:
            continue
        # The two figures belong to this card, so look only as far as the next one.
        following = _MODEL_CARD.search(body_style_html, match.end())
        block = body_style_html[match.end() : following.start() if following else len(body_style_html)]
        seats = _SEATS.search(block)
        berths = _BERTHS.search(block)
        cards[url] = RimorCard(
            url=url,
            name=name,
            seats=_leading_int(seats.group(1)) if seats else None,
            berths=_leading_int(berths.group(1)) if berths else None,
        )
    return list(cards.values())


def parse_model_page(html: str, url: str, card: RimorCard) -> RimorModel | None:
    """One layout from its own page, or `None` if the overview block isn't there.

    Everything numeric is read from inside the overview block only. The rest of the page
    repeats the same markup for every *other* layout in the range, so an unscoped read
    silently attributes a sibling's seats and berths to this product.
    """
    overview_match = _OVERVIEW.search(html)
    if overview_match is None:
        return None
    overview = overview_match.group(1)

    range_match = _RANGE_NAME.search(html)
    model_match = _MODEL_NAME.search(html)
    if range_match is None:
        return None
    # The `modello` heading is the model designation on its own ("12", "66 Plus",
    # "Suite"). Falling back to the card's text keeps a product rather than dropping it,
    # since the card already names it in full.
    model = model_match.group(1) if model_match else card.name

    body_style_match = _BODY_STYLE_OF_MODEL.search(html)
    body_style = body_style_match.group(1) if body_style_match else None

    length = _LENGTH.search(overview)
    width = _WIDTH.search(overview)
    height = _HEIGHT.search(overview)
    seats = _SEATS.search(overview)
    berths = _BERTHS.search(overview)
    bedding = _BEDDING.search(overview)

    solution = bedding.group(1) if bedding else None
    return RimorModel(
        range_label=range_match.group(1),
        model=model,
        url=url,
        body_type=BODY_TYPES.get(body_style or ""),
        body_style=body_style,
        mh_passenger_seats_inc_driver=_leading_int(seats.group(1)) if seats else None,
        seats_text=seats.group(1) if seats else None,
        berths=_leading_int(berths.group(1)) if berths else None,
        berths_text=berths.group(1) if berths else None,
        mh_length_mm=int(length.group(1)) if length else None,
        # Only the first of each pair is the outside figure; the second is internal.
        mh_width_mm=int(width.group(1)) if width else None,
        mh_height_mm=int(height.group(1)) if height else None,
        bedding_solution=solution,
        bed_types=bed_types_for(solution),
        card_seats=card.seats,
        card_berths=card.berths,
    )


def bed_types_for(solution: str | None) -> list[BedType]:
    """The FMLV bed types a "Bedding solution" phrase implies.

    Returns `[]` for anything unrecognised rather than falling back to a default — an
    unmapped phrase is a new layout style worth noticing, not worth guessing at.
    """
    if not solution:
        return []
    text = solution.strip().lower()
    for phrase, bed_type in BEDDING_SOLUTIONS:
        if phrase in text:
            return [bed_type]
    return []


def parse_leaflet_dimensions(leaflet_text: str) -> Counter[tuple[int, int]]:
    """Every `length x width` pair a leaflet publishes, as an unordered multiset.

    A multiset, and not a sequence, on purpose. Leaflet text extracts in scrambled
    reading order — on the Kilig leaflet a layout count is emitted next to the wrong
    length band — so any check that depends on *where* a pair appeared is unreliable.
    Membership does not.
    """
    return Counter(
        (int(length), int(width))
        for length, width in _PAIR.findall(leaflet_text)
        if _is_vehicle_pair(int(length), int(width))
    )


@dataclass(frozen=True)
class CatalogueFacts:
    """The two fields the catalogue adds, per range."""

    mtplm_kilograms: int | None = None
    base_vehicle_manufacturer: str | None = None


def parse_catalogue(catalogue_text: str, ranges: tuple[tuple[str, str], ...]) -> dict[str, CatalogueFacts]:
    """MTPLM and base chassis per range, keyed by range label.

    **Only page-constant values may be read here.** pypdf returns a whole spec row as a
    single run — `'Outside length (mm) 5413 5998'` covers three models with two values,
    because the layout prints a value once where it spans several columns — and every
    run starts at the same x, so there is nothing to recover the spans from. Anything
    varying per model is therefore unreadable and comes from the HTML instead.

    Maximum overall weight and engine are identical down every column of a page, so they
    need no alignment at all. Where a range's pages disagree the field is dropped for
    that range: disagreement means the assumption above has stopped holding.
    """
    pages = [page for page in catalogue_text.split("\n\n") if _SPEC_PAGE_MARKER in page]

    facts: dict[str, CatalogueFacts] = {}
    for slug, label in ranges:
        heading = slug.replace("-", " ").upper()
        weights: set[int] = set()
        engines: set[str] = set()
        for page in pages:
            if heading not in page.upper():
                continue
            mtplm = _CATALOGUE_MTPLM.search(page)
            engine = _CATALOGUE_ENGINE.search(page)
            if mtplm:
                weights.add(int(mtplm.group(1)))
            if engine:
                engines.add(engine.group(1).strip())
        if not weights and not engines:
            continue
        facts[label] = CatalogueFacts(
            mtplm_kilograms=weights.pop() if len(weights) == 1 else None,
            # "Fiat Ducato" / "Ford Transit" — the make is the first word, as in
            # `sunlight.py`.
            base_vehicle_manufacturer=engines.pop().split()[0] if len(engines) == 1 else None,
        )
    return facts


def catalogue_urls(year: int) -> list[str]:
    """Candidate catalogue URLs, newest season and version first.

    Two seasons are tried because the survey ran in August against a `2025-26`
    catalogue: the changeover is near, and which side of it a run falls on is not
    knowable from the site.
    """
    seasons = [f"{year}-{(year + 1) % 100:02d}", f"{year - 1}-{year % 100:02d}"]
    return [
        BASE_URL + CATALOGUE_PATH.format(season=season, version=version).replace(" ", "%20")
        for season in seasons
        for version in range(MAX_CATALOGUE_VERSION, 0, -1)
    ]


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def _reconciles(model: RimorModel, leaflet: Counter[tuple[int, int]]) -> tuple[bool, str]:
    """Whether a layout agrees with what Rimor publishes about it elsewhere.

    Two independent redundancies stand in for the payload arithmetic Morelo and Swift
    provide and Rimor does not:

    1. **Listing against detail.** Seats and berths appear on the body-style card *and*
       on the model's own page. A mismatch means a card was attributed to the wrong
       model — the realistic failure, given the listing renders twice per page.
    2. **HTML against the leaflet.** The range leaflet republishes every layout's
       `length x width`. A pair that is not in that multiset means the dimensions were
       misread, or the layout is not in the range the page put it in.

    Returns the reason as well as the verdict so a drop can say what it found. A check
    with nothing to compare against passes: absence is not contradiction.
    """
    if (
        model.card_seats is not None
        and model.mh_passenger_seats_inc_driver is not None
        and model.card_seats != model.mh_passenger_seats_inc_driver
    ):
        return False, (
            f"listing card says {model.card_seats} seats but its page says "
            f"{model.mh_passenger_seats_inc_driver}"
        )
    if model.card_berths is not None and model.berths is not None and model.card_berths != model.berths:
        return False, (
            f"listing card says {model.card_berths} berths but its page says {model.berths}"
        )

    dimensions = model.dimensions
    if dimensions is not None and leaflet and leaflet[dimensions] == 0:
        return False, (
            f"{dimensions[0]}x{dimensions[1]} mm is not among the sizes the range "
            f"leaflet publishes ({', '.join(f'{l}x{w}' for l, w in sorted(leaflet))})"
        )
    return True, ""


# --------------------------------------------------------------------------- #
# Orchestration: fetch + parse -> ExtractedMotorhome
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(model: RimorModel, facts: CatalogueFacts) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=model.range_label,
        model=model.model,
        base_vehicle_manufacturer=facts.base_vehicle_manufacturer,
        body_type=model.body_type,
        bed_types=model.bed_types,
        mh_passenger_seats_inc_driver=model.mh_passenger_seats_inc_driver,
        berths=model.berths,
        mtplm_kilograms=facts.mtplm_kilograms,
        mh_length_mm=model.mh_length_mm,
        mh_width_mm=model.mh_width_mm,
        mh_height_mm=model.mh_height_mm,
    )

    source = BASE_URL + model.url
    label = f"{model.range_label} {model.model}"
    provenance: dict[str, Provenance] = {}

    def record(field_name: str, snippet: str, *, url: str = source) -> None:
        provenance[field_name] = Provenance(source_url=url, snippet=f"{label} — {snippet}")

    if model.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            f"numero posti omologati (certified seats): {model.seats_text}",
        )
    if model.berths is not None:
        # The cell text is kept verbatim: "4 (+1 opt)" says something the integer
        # cannot, namely that the fifth berth needs optional equipment.
        record("berths", f"numero posti letto (berths): {model.berths_text}")
    for field_name, axis, value in (
        ("mh_length_mm", "Outside length", model.mh_length_mm),
        ("mh_width_mm", "Outside width", model.mh_width_mm),
        ("mh_height_mm", "Maximum outside height", model.mh_height_mm),
    ):
        if value is not None:
            record(field_name, f"{axis}: {value} mm")
    if model.body_type is not None:
        record("body_type", f"listed under /{model.body_style}")
    if model.bed_types:
        record("bed_types", f"Bedding solution: {model.bedding_solution}")
    if facts.mtplm_kilograms is not None:
        record(
            "mtplm_kilograms",
            f"Maximum overall weight: {facts.mtplm_kilograms} kg (2025-26 catalogue)",
        )
    if facts.base_vehicle_manufacturer is not None:
        record(
            "base_vehicle_manufacturer",
            f"Engine: {facts.base_vehicle_manufacturer} (2025-26 catalogue)",
        )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def _fetch_catalogue_facts(
    http: Fetcher,
    ranges: tuple[tuple[str, str], ...],
    on_progress: Callable[[str], None],
    year: int,
) -> dict[str, CatalogueFacts]:
    """MTPLM and chassis per range, or `{}` if the catalogue can't be found.

    Deliberately non-fatal. The catalogue is linked from no page on the site, so its URL
    is probed rather than discovered, and both the season and the version move. Failing
    a whole run because a guessed URL 404s would be absurd — the 41 products come from
    the HTML and only these two fields are lost.
    """
    for url in catalogue_urls(year):
        try:
            result = http.fetch(url)
        except Exception as exc:  # noqa: BLE001 — a probe failing is not a run failing
            on_progress(f"catalogue probe failed for {url}: {exc}")
            continue
        if result.status_code != 200 or "pdf" not in (result.content_type or ""):
            continue

        document = extract_text(result.file_path)
        if document.is_empty():
            on_progress(f"catalogue at {url} has no extractable text — skipping enrichment")
            return {}

        facts = parse_catalogue(document.text, ranges)
        on_progress(
            f"catalogue found ({url.rsplit('/', 1)[-1]}): "
            f"MTPLM and chassis for {len(facts)} range(s)"
        )
        return facts

    on_progress(
        "SKIPPED enrichment: no catalogue PDF found at any probed season/version — "
        "products will have no MTPLM or base chassis"
    )
    return {}


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Rimor is fully server-rendered; see the docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every Rimor layout from the website, checked against the range leaflets.

    `ranges` selects which of the five to walk, so `--range Kilig` runs one of them.

    A failure on one page or one product is narrated and skipped; only a range page that
    cannot be fetched at all takes its whole range out, and even then the other ranges
    continue. The catalogue is optional enrichment throughout.
    """
    results: list[ExtractedMotorhome] = []
    facts_by_range = _fetch_catalogue_facts(http, ranges, on_progress, datetime.now(UTC).year)

    for range_slug, range_label in ranges:
        range_url = f"{BASE_URL}/int/en/gamma/{range_slug}"
        on_progress(f"[{range_label}] {range_url}")
        range_result = http.fetch(range_url)
        if range_result.status_code != 200:
            on_progress(f"[{range_label}] SKIPPED: range page returned {range_result.status_code}")
            continue
        range_html = range_result.file_path.read_text(encoding="utf-8", errors="replace")

        # The leaflet is the self-check's second source. Without it the dimension check
        # cannot run, so say so rather than letting products through silently unchecked.
        leaflet: Counter[tuple[int, int]] = Counter()
        leaflet_path = parse_leaflet_url(range_html)
        if leaflet_path is None:
            on_progress(f"[{range_label}] no leaflet linked — dimension check disabled")
        else:
            leaflet_url = BASE_URL + leaflet_path.replace(" ", "%20")
            leaflet_result = http.fetch(leaflet_url)
            if leaflet_result.status_code != 200:
                on_progress(
                    f"[{range_label}] leaflet returned {leaflet_result.status_code} — "
                    f"dimension check disabled"
                )
            else:
                leaflet = parse_leaflet_dimensions(extract_text(leaflet_result.file_path).text)
                on_progress(
                    f"[{range_label}] leaflet lists {sum(leaflet.values())} layout size(s)"
                )

        body_styles = parse_body_style_links(range_html, range_slug)
        if not body_styles:
            on_progress(f"[{range_label}] SKIPPED: no body-style pages linked")
            continue

        facts = facts_by_range.get(range_label, CatalogueFacts())
        collected = 0

        for body_style in body_styles:
            listing_url = f"{BASE_URL}/int/en/gamma/{range_slug}/{body_style}"
            listing_result = http.fetch(listing_url)
            if listing_result.status_code != 200:
                on_progress(
                    f"  /{body_style} — SKIPPED: returned {listing_result.status_code}"
                )
                continue

            cards = parse_model_cards(
                listing_result.file_path.read_text(encoding="utf-8", errors="replace")
            )
            if not cards:
                on_progress(f"  /{body_style} — SKIPPED: no model cards found")
                continue
            on_progress(f"  /{body_style} — {len(cards)} layout(s)")

            for card in cards:
                model_result = http.fetch(BASE_URL + card.url)
                if model_result.status_code != 200:
                    on_progress(
                        f"    {card.name} — SKIPPED: returned {model_result.status_code}"
                    )
                    continue

                model = parse_model_page(
                    model_result.file_path.read_text(encoding="utf-8", errors="replace"),
                    card.url,
                    card,
                )
                if model is None:
                    on_progress(f"    {card.name} — SKIPPED: no overview block on the page")
                    continue

                ok, reason = _reconciles(model, leaflet)
                if not ok:
                    on_progress(f"    {card.name} — SKIPPED: {reason}")
                    continue
                if not model.bed_types and model.bedding_solution:
                    on_progress(
                        f"    {card.name} — unmapped bedding solution "
                        f"{model.bedding_solution!r}, bed types left empty"
                    )

                results.append(_build_extracted_motorhome(model, facts))
                collected += 1

        on_progress(f"[{range_label}] {collected} product(s)")

    on_progress(f"{len(results)} product(s) collected")
    return results
