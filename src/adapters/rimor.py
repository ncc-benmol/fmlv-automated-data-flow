"""Rimor — UK range and prices from the importer, specifications from the factory.

See `docs/adapters/rimor.md` for the full write-up. Rimor is the first adapter to read
two *different* sites and let each decide different fields, because neither one can
answer the whole question:

* **Motorhomes & Caravans Ltd (`motorhomesandcaravansltd.co.uk`) decides which products
  exist and what they cost.** Rimor is sold in the UK exclusively through MNC, so the UK
  range *is* whatever MNC lists — the factory's own catalogue carries layouts that are
  never imported. And Rimor publishes no price anywhere in the world, so MNC's is the
  only price there is.
* **`rimor.it` decides every number.** MNC's specifications are a sales description, not
  a data sheet: it truncates dimensions to whole centimetres, it repeats the travel-seat
  count in place of the berth count on the coachbuilts, and at least two of its layouts
  carry another layout's figures. The factory publishes exact millimetres, the
  homologated seat count, the standard berth count, MTPLM, MRO and the bedding solution.

So MNC is walked for the range, the price and the body type, and each listing is then
joined to its factory layout page, which supplies the specification. A layout MNC does
not list is not a UK product and is not emitted, however complete its factory page.

    MNC   /product-category/new-motorhomes-for-sale/new-rimor-motorhomes/<range>
            -> /product/rimor-<range>-<layout>-<year>[-variant]    price, body type
    Rimor /int/en/gamma/<range>/<body-style>
            -> /int/en/gamma/<range>/modello/<layout>              every specification

Three things shape this adapter:

* **The join survives Rimor's renaming.** Rimor moved its whole Kilig low-profile line
  to `<n> Plus` for the new season while MNC still lists the old names, so a layout is
  looked up with a `-plus` fallback — MNC's `kilig-66` finds `kilig/66-plus`.
  `_factory_slug` is where that lives, and the dimension check below is what *proves*
  the match rather than assuming it.
* **The self-check is cross-site.** MNC and Rimor publish each layout's dimensions
  independently, so the two are compared. MNC truncates metres, which caps an honest
  disagreement at 9 mm; anything larger is a real conflict, narrated loudly, with the
  factory figure kept. It is what caught Kilig 79 (MNC prints the 78's length) and
  Kilig 99 (out by 132 mm).
* **Stock units are not products.** MNC sells actual vehicles alongside its layout
  listings — demo vans with a struck-through price, and WordPress `-copy` slugs. Each
  layout is emitted once, preferring its plain listing; where a demo unit is the only
  listing a layout has, the *pre-discount* price is taken, because the discount belongs
  to that one vehicle and not to the layout. See `select_listings` and `price_from`.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.enums import BedType, BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://www.rimor.it"
MNC_BASE_URL = "https://motorhomesandcaravansltd.co.uk"
MNC_CATEGORY = "/product-category/new-motorhomes-for-sale/new-rimor-motorhomes"
MANUFACTURER = "Rimor"
MANUFACTURER_DISPLAY_NAME = "Rimor"

#: `(MNC category slug, factory range slug, label)`. Neither site has a machine-readable
#: index of its ranges — the factory's `/int/en/gamma` is a 404 and MNC's category page
#: mixes range tiles with marketing links — so the five are listed here. Note that MNC
#: spells Sailer's category without the `rimor-` prefix the other four carry.
DEFAULT_RANGES: tuple[tuple[str, str, str], ...] = (
    ("rimor-horus", "horus", "Horus"),
    ("rimor-kilig", "kilig", "Kilig"),
    ("rimor-sarus", "sarus", "Sarus"),
    ("sailer", "sailer", "Sailer"),
    ("rimor-super-brig", "super-brig", "Super Brig"),
)

#: Product slugs read `rimor-<range>-<layout>-...`, and the range has to be matched
#: longest-first so `super-brig` is not truncated to a single token. `van` is the Rimor
#: Van 238 — see `RANGE_LABELS`.
SLUG_RANGES: tuple[str, ...] = ("super-brig", "horus", "kilig", "sarus", "sailer", "van")

#: The range each slug prefix names. `van` is deliberately mapped to Horus: MNC files the
#: Van 238 under `All Camper Vans, Horus`, and MNC is what decides the UK range. The
#: factory instead gives it a standalone `/special/rimor-van` page with no spec table,
#: which is why it has no factory join at all.
RANGE_LABELS: dict[str, str] = {
    "horus": "Horus",
    "kilig": "Kilig",
    "sarus": "Sarus",
    "sailer": "Sailer",
    "super-brig": "Super Brig",
    "van": "Horus",
}

#: Trailing slug tokens that are not part of a layout name: a model year, a transmission
#: or trim variant, or a stock/duplicate marker. Stripped from the right until a real
#: layout token remains, so `rimor-kilig-55-plus-2027` yields `55-plus` and
#: `rimor-horus-40-2026-automatic` yields `40`.
SLUG_NOISE: frozenset[str] = frozenset(
    {"automatic", "demo", "van", "copy", "2", "off", "road", "spec"}
)

#: Slug tokens marking a listing as a specific vehicle or a duplicate rather than a
#: layout. `demo` is a stock unit; `copy` is a WordPress duplicate whose slug is the only
#: thing wrong with it. Both lose to a plain listing of the same layout, but either can
#: stand in when it is the only listing that layout has.
STOCK_MARKERS: frozenset[str] = frozenset({"demo", "copy", "spec"})

#: The factory body-style URL segment *is* the body type, and stays the best source for
#: it. Any other segment is not a body-style page and is skipped, so a new one appearing
#: does not silently become the wrong type.
BODY_TYPES: dict[str, BodyType] = {
    "low-profile": BodyType.COACH_BUILT_LOW_PROFILE,
    "overcab": BodyType.COACH_BUILT_OVER_CAB_BED,
    "vans": BodyType.CAMPERVAN,
}

#: MNC's product categories carry the same distinction, and are the only source of it for
#: a layout with no factory page. Matched against the `Categories` line, longest-first.
MNC_BODY_TYPES: tuple[tuple[str, BodyType], ...] = (
    ("all low profile", BodyType.COACH_BUILT_LOW_PROFILE),
    ("all camper vans", BodyType.CAMPERVAN),
    ("all overcab", BodyType.COACH_BUILT_OVER_CAB_BED),
)

#: "Bedding solution : Twin beds" -> the FMLV bed type. Ordered longest-first, because
#: several of these are prefixes of each other: matching `Double bed` before `Double bunk
#: beds` or `Double superimposed bunk beds` turns a bunk layout into a fixed one. A
#: solution matching nothing here leaves `bed_types` empty and is narrated, rather than
#: being guessed at.
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

#: How far MNC and the factory may disagree on a dimension before it counts as a real
#: conflict. MNC prints whole centimetres and *truncates* rather than rounds (7338 mm
#: reads as 7.33 m), so an honest disagreement never exceeds 9 mm.
DIMENSION_TOLERANCE_MM = 10

# --- MNC: the range, the price and the body type -----------------------------------

_MNC_PRODUCT_LINK = re.compile(rf'href="{re.escape(MNC_BASE_URL)}/product/([a-z0-9-]+)/"')

#: The WooCommerce price block. Scoping to it is not optional: the page also prices the
#: options ("Alloy wheel option: £1,350") and the finance calculator repeats the total.
_MNC_PRICE_BLOCK = re.compile(r'<p class="price">(.*?)</p>', re.S)

#: Prices are read from WooCommerce's own screen-reader labels rather than from the
#: `<del>`/`<ins>` markup around them. The visible markup puts the currency symbol in its
#: own `<span>`, so the symbol and its digits are never adjacent; these labels spell out
#: both figures in plain text and say which is which.
_MNC_PRICE_WAS = re.compile(r"Original price was:\s*(?:&pound;|£)\s*([\d,]+)", re.I)
_MNC_PRICE_NOW = re.compile(r"Current price is:\s*(?:&pound;|£)\s*([\d,]+)", re.I)

#: An undiscounted listing carries one amount and no labels, so it is read from the
#: block's text with the tags taken out.
_MNC_PRICE_ONLY = re.compile(r"£\s*([\d,]+)")

#: The listing title, which is a heading with the `product_title` class — an `<h2>` today,
#: so the tag itself is not pinned. It is the only element carrying the full title
#: including a "Demo Van" suffix; the `<h1>` inside the description drops it.
_MNC_TITLE = re.compile(r'<(h[1-6])[^>]*class="[^"]*product_title[^"]*"[^>]*>(.*?)</\1>', re.S)
_MNC_CATEGORIES = re.compile(r'<span class="posted_in[^"]*">(.*?)</span>\s*</span>', re.S)
_MNC_VEHICLE = re.compile(r"Vehicle:\s*(?:</?[^>]+>\s*)*([A-Za-z][A-Za-z\-]*)", re.I)
_MNC_LENGTH = re.compile(r"Length:\s*([\d.]+)\s*m\b", re.I)
_MNC_WIDTH = re.compile(r"Width:\s*([\d.]+)\s*m\b", re.I)
_MNC_HEIGHT = re.compile(r"Height:\s*([\d.]+)\s*m\b", re.I)
_MNC_BERTHS = re.compile(r"(\d+)\s*berth with\s*(\d+)\s*travel seat", re.I)

#: A page whose title says "Demo" is one specific vehicle. Detected from the *fetched*
#: page rather than the requested slug, because several plain layout URLs 301 onto a demo
#: listing — `rimor-sailer-55-plus-2026` lands on the demo van — and only the page that
#: comes back can say what was actually read.
_MNC_DEMO = re.compile(r"\bdemo\b", re.I)

# --- rimor.it: every specification --------------------------------------------------

#: The overview block on a model page. Scoping to it is not optional: every model page
#: also carries an "other range models" list whose cards repeat the same markup for every
#: *other* layout in the range, and an unscoped read takes whichever comes first.
_OVERVIEW = re.compile(r'id="panoramica-modello"(.*?)END PANORAMICA MODELLO', re.S)

_MODEL_CARD = re.compile(
    r'href="(/int/en/gamma/[a-z-]+/modello/[^"]+)"[^>]*class="stretched-link[^"]*"[^>]*>\s*([^<]+?)\s*</a>'
)
_BODY_STYLE_LINK = re.compile(r'href="/int/en/gamma/([a-z-]+)/([a-z-]+)"')
_RANGE_NAME = re.compile(r'class="gamma[^"]*"[^>]*>\s*([^<]+?)\s*</a>')
_MODEL_NAME = re.compile(r'<div class="modello">\s*([^<]+?)\s*</div>')
_BODY_STYLE_OF_MODEL = re.compile(r'href="/int/en/gamma/[a-z-]+/([a-z-]+)"[^>]*class="tipologia')

def _spec_row(label: str, value: str) -> re.Pattern[str]:
    """Matches one row of the overview table: `<td>label</td><td>value</td>`.

    Two pieces of slack matter, and both were learned from the 2026 redesign silently
    emptying every field that did not allow for them. The label is padded onto its own
    line, so whitespace before the closing `</td>` is not optional; and a footnote
    anchor may follow the label inside the same cell — the rows for the uprated-chassis
    and reduced-seat notes both carry one.
    """
    return re.compile(
        rf"{label}\s*(?:<a[^>]*>.*?</a>\s*)?</td>\s*<td[^>]*>\s*{value}",
        re.S | re.I,
    )


#: The dimension rows. Only the first figure of each pair is the outside measurement;
#: the second is the internal one, which FMLV does not store.
_LENGTH = _spec_row("outside length", r"(\d+)\s*mm")
_WIDTH = _spec_row("outside width - inside width", r"(\d+)\s*-\s*(\d+)\s*mm")
_HEIGHT = _spec_row(r"maximum outside height\s*-?\s*inside height", r"(\d+)\s*-\s*(\d+)\s*mm")

#: Masses, both published per model since the 2026 redesign — before it, neither appeared
#: anywhere but the catalogue PDF, and MRO not even there, so payload could not be
#: computed at all. MTPLM is a list of chassis options (`3500 / 3550 / 4100`) of which the
#: **first is the standard vehicle**; the heavier ones are uprated chassis and are not the
#: FMLV figure.
_MTPLM = _spec_row("maximum overall weight", r"(\d+(?:\s*/\s*\d+)*)\s*kg")
_MRO = _spec_row(r"\bMRO", r"(\d+)\s*kg")

_BEDDING = re.compile(r"Bedding solution\s*</span>\s*:\s*<span>\s*([^<]+?)\s*</span>", re.S)

#: Seats and berths are distinguishable **only** by these Italian icon class names. Until
#: the 2026 redesign they were `title` attributes; the Italian words are the same and so
#: is the rule — anchor on the name, never on position, because the two widgets are
#: otherwise identical and the site's English does not reach either of them.
_SEATS_ICON = "lc-icons-posti-omologati"
_BERTHS_ICON = "lc-icons-posti-letto"

#: `4`, `6 / 5`, `4 (+1 opt)`. The standard figure is the leading integer: a `/ 5` is the
#: reduced-seat homologation Rimor offers to free up payload, and a `(+n opt)` needs
#: optional equipment. Both are dropped, the convention `sunlight.py` also applies.
_COUNT = re.compile(r"^\s*(\d+)")


def _icon_value(icon_class: str) -> re.Pattern[str]:
    """Matches the value span belonging to the `caratteristica-modello` with `icon_class`."""
    return re.compile(
        rf'class="{re.escape(icon_class)}[^"]*"'
        r'(?:(?!caratteristica-modello">).)*?'
        r'valore-caratteristica-modello">\s*([^<]*?)\s*</span>',
        re.S,
    )


_SEATS = _icon_value(_SEATS_ICON)
_BERTHS = _icon_value(_BERTHS_ICON)


def _leading_int(text: str | None) -> int | None:
    if not text:
        return None
    match = _COUNT.match(text)
    return int(match.group(1)) if match else None


def _pounds(text: str | None) -> int | None:
    return None if not text else int(text.replace(",", ""))


def _metres_to_mm(text: str | None) -> int | None:
    """Whole millimetres from MNC's `7.33` metres. Used for the cross-check only."""
    return None if not text else round(float(text) * 1000)


def _plain_text(fragment: str) -> str:
    """Tags stripped and entities resolved, for reading MNC's prose spec list."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


@dataclass(frozen=True)
class MncListing:
    """One product listing on MNC — a UK availability record, a price and a body type.

    `layout` is the join key onto the factory site. The dimensions are carried only so
    `_dimension_conflicts` can check the join; nothing here reaches a product except the
    price, the body type, the base vehicle, and — for a layout with no factory page —
    the seats and berths.
    """

    slug: str
    url: str
    title: str
    range_slug: str
    layout: str
    model_year: int | None
    markers: frozenset[str]
    rrp_pounds: int | None = None
    pre_discount_pounds: int | None = None
    is_demo: bool = False
    body_type: BodyType | None = None
    base_vehicle_manufacturer: str | None = None
    mnc_length_mm: int | None = None
    mnc_width_mm: int | None = None
    mnc_height_mm: int | None = None
    mnc_berths: int | None = None
    mnc_seats: int | None = None

    @property
    def range_label(self) -> str:
        return RANGE_LABELS.get(self.range_slug, self.range_slug.title())

    @property
    def is_stock(self) -> bool:
        """True when the slug marks this a specific vehicle or a duplicate listing."""
        return bool(self.markers & STOCK_MARKERS)

    @property
    def key(self) -> tuple[str, str]:
        return (self.range_slug, self.layout)


@dataclass(frozen=True)
class RimorModel:
    """One layout's specification, from its own page on the factory site."""

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
    mtplm_kilograms: int | None = None
    mtplm_text: str | None = None
    mro_kilograms: int | None = None
    bedding_solution: str | None = None
    bed_types: list[BedType] | None = None

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload from the two published masses, the arithmetic FMLV stores directly."""
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms


def parse_layout_key(slug: str) -> tuple[str, str, int | None, frozenset[str]] | None:
    """`(range slug, layout, model year, markers)` from an MNC product slug.

    Trailing noise is stripped from the right — a model year, `automatic`, a stock or
    duplicate marker — until a layout token remains, so every listing of one layout
    reduces to the same key however MNC has suffixed it:

        rimor-kilig-55-plus-2027                     -> kilig, 55-plus, 2027, {}
        rimor-horus-40-2026-automatic                 -> horus, 40, 2026, {automatic}
        rimor-sailer-55-plus-2026-automatic-demo-van  -> sailer, 55-plus, 2026, {...demo}

    Returns `None` for a slug naming no known range, rather than guessing at one.
    """
    body = slug[len("rimor-") :] if slug.startswith("rimor-") else slug
    range_slug = next((r for r in SLUG_RANGES if body.startswith(f"{r}-")), None)
    if range_slug is None:
        return None

    tokens = body[len(range_slug) + 1 :].split("-")
    markers: set[str] = set()
    model_year: int | None = None
    while tokens and (re.fullmatch(r"20\d\d", tokens[-1]) or tokens[-1] in SLUG_NOISE):
        token = tokens.pop()
        if re.fullmatch(r"20\d\d", token):
            # Keep the *latest* year a slug carries; `-copy-2` style suffixes never
            # carry one, so there is only ever the one.
            model_year = int(token)
        else:
            markers.add(token)
    if not tokens:
        return None
    return range_slug, "-".join(tokens), model_year, frozenset(markers)


def parse_mnc_product_slugs(category_html: str) -> list[str]:
    """Every product slug linked from one MNC category page, deduplicated, in page order.

    The listing renders each product more than once (card, title and "More Info" all
    link to it), and the site footer repeats the range menu, so duplicates are the norm.
    """
    seen: dict[str, None] = {}
    for slug in _MNC_PRODUCT_LINK.findall(category_html):
        seen.setdefault(slug, None)
    return list(seen)


def price_from(price_block: str, *, is_demo: bool) -> tuple[int | None, int | None]:
    """`(price to record, pre-discount price)` from the WooCommerce price block.

    A struck-through `<del>` price means this listing is discounted. Which of the two
    figures is the guide price depends on *what* is discounted:

    * A **layout** listing on promotion — the whole Horus range shows £61,990 struck
      through at £59,995 — is discounted as a range, and £59,995 is the price MNC's site
      leads with. That is the figure FMLV should match, so the current price is taken.
    * A **demo unit** standing in for its layout is discounted as one vehicle. Sailer 55
      Plus reads £69,995 struck through at £64,995, and £69,995 is exactly what the other
      three Sailers cost. Taking the current price there would publish one used van's
      price as the layout's, so the pre-discount figure is taken instead.
    """
    was = _pounds(match.group(1)) if (match := _MNC_PRICE_WAS.search(price_block)) else None
    now = _pounds(match.group(1)) if (match := _MNC_PRICE_NOW.search(price_block)) else None
    if now is None and was is None:
        text = _plain_text(price_block)
        now = _pounds(match.group(1)) if (match := _MNC_PRICE_ONLY.search(text)) else None
    if is_demo and was is not None:
        return was, was
    return now, was


def parse_mnc_listing(html_text: str, slug: str, url: str) -> MncListing | None:
    """One MNC product page, or `None` if its slug names no range.

    The page that comes back is not always the page that was asked for — several plain
    layout URLs 301 onto a demo listing — so `is_demo` is read from the title here and
    not inferred from the requested slug.
    """
    parsed = parse_layout_key(slug)
    if parsed is None:
        return None
    range_slug, layout, model_year, markers = parsed

    title_match = _MNC_TITLE.search(html_text)
    title = _plain_text(title_match.group(2)) if title_match else slug
    is_demo = bool(_MNC_DEMO.search(title)) or "demo" in markers

    price_match = _MNC_PRICE_BLOCK.search(html_text)
    rrp, pre_discount = (
        price_from(price_match.group(1), is_demo=is_demo) if price_match else (None, None)
    )

    categories_match = _MNC_CATEGORIES.search(html_text)
    categories = _plain_text(categories_match.group(1)).lower() if categories_match else ""
    body_type = next(
        (bt for phrase, bt in MNC_BODY_TYPES if phrase in categories),
        None,
    )

    text = _plain_text(html_text)
    vehicle = _MNC_VEHICLE.search(text)
    berths = _MNC_BERTHS.search(text)

    return MncListing(
        slug=slug,
        url=url,
        title=title,
        range_slug=range_slug,
        layout=layout,
        model_year=model_year,
        markers=markers,
        rrp_pounds=rrp,
        pre_discount_pounds=pre_discount,
        is_demo=is_demo,
        body_type=body_type,
        base_vehicle_manufacturer=fmlv_base_vehicle(vehicle.group(1)) if vehicle else None,
        mnc_length_mm=_metres_to_mm(m.group(1)) if (m := _MNC_LENGTH.search(text)) else None,
        mnc_width_mm=_metres_to_mm(m.group(1)) if (m := _MNC_WIDTH.search(text)) else None,
        mnc_height_mm=_metres_to_mm(m.group(1)) if (m := _MNC_HEIGHT.search(text)) else None,
        mnc_berths=int(berths.group(1)) if berths else None,
        mnc_seats=int(berths.group(2)) if berths else None,
    )


def select_listings(slugs: list[str]) -> tuple[list[str], dict[str, str]]:
    """One slug per layout, plus why each of the others was set aside.

    MNC lists a layout more than once — a plain page, an `-automatic` variant, a demo
    van, a WordPress `-copy` — and all of them describe the same layout. Preference runs
    plain listing, then duplicate, then demo unit; within that, the latest model year and
    then the shortest slug, which favours the base vehicle over an optioned variant.

    A demo or copy listing is still chosen when it is all a layout has, so that a layout
    MNC genuinely sells is not lost for want of a tidy URL — four of them are in that
    position today, Sailer 55 Plus and 56 Plus among them.
    """
    grouped: dict[tuple[str, str], list[tuple[str, int | None, frozenset[str]]]] = {}
    unparsed: dict[str, str] = {}
    for slug in slugs:
        parsed = parse_layout_key(slug)
        if parsed is None:
            unparsed[slug] = "slug names no known range"
            continue
        range_slug, layout, model_year, markers = parsed
        grouped.setdefault((range_slug, layout), []).append((slug, model_year, markers))

    def rank(entry: tuple[str, int | None, frozenset[str]]) -> tuple[int, int, int]:
        slug, model_year, markers = entry
        stock = 2 if markers & {"demo"} else (1 if markers & STOCK_MARKERS else 0)
        return (stock, -(model_year or 0), len(slug))

    selected: list[str] = []
    set_aside = dict(unparsed)
    for _key, entries in grouped.items():
        chosen, *rest = sorted(entries, key=rank)
        selected.append(chosen[0])
        for slug, _year, _markers in rest:
            set_aside[slug] = f"another listing of the same layout was preferred ({chosen[0]})"
    return selected, set_aside


def parse_body_style_links(range_html: str, range_slug: str) -> list[str]:
    """The body-style segments linked from one factory range page, in page order."""
    seen: dict[str, None] = {}
    for slug, body_style in _BODY_STYLE_LINK.findall(range_html):
        if slug == range_slug and body_style in BODY_TYPES:
            seen.setdefault(body_style, None)
    return list(seen)


def parse_model_slugs(body_style_html: str) -> list[str]:
    """The layout slugs linked from one factory body-style listing page.

    The list appears twice on every such page, once in the main content and once in a
    footer block, so it is deduplicated on the slug.
    """
    seen: dict[str, None] = {}
    for url, _name in _MODEL_CARD.findall(body_style_html):
        seen.setdefault(url.rsplit("/", 1)[-1], None)
    return list(seen)


def _factory_slug(layout: str, available: set[str]) -> str | None:
    """The factory's slug for an MNC layout, allowing for Rimor's `Plus` renaming.

    Rimor renamed its whole Kilig low-profile line from `<n>` to `<n> Plus` for the new
    season while MNC kept the old names, so `66` has to find `66-plus`. The reverse also
    has to work, since MNC will eventually catch up and Sarus already lists `66 Plus`
    against a factory `66-plus`. Nothing is invented: only a slug the factory actually
    publishes is returned, and the dimension check afterwards is what confirms it.
    """
    for candidate in (layout, f"{layout}-plus", layout.removesuffix("-plus")):
        if candidate in available:
            return candidate
    return None


def parse_model_page(html_text: str, url: str) -> RimorModel | None:
    """One layout's specification from its factory page, or `None` without an overview.

    Everything numeric is read from inside the overview block only. The rest of the page
    repeats the same markup for every *other* layout in the range, so an unscoped read
    silently attributes a sibling's seats and berths to this product.
    """
    overview_match = _OVERVIEW.search(html_text)
    range_match = _RANGE_NAME.search(html_text)
    if overview_match is None or range_match is None:
        return None
    overview = overview_match.group(1)

    model_match = _MODEL_NAME.search(html_text)
    # The `modello` heading is the designation on its own ("38", "55 Plus", "Suite"). Its
    # absence means the page shape has moved again, so fall back to the URL's own slug
    # rather than dropping a product MNC says is on sale.
    model = model_match.group(1) if model_match else url.rsplit("/", 1)[-1]

    body_style_match = _BODY_STYLE_OF_MODEL.search(html_text)
    body_style = body_style_match.group(1) if body_style_match else None

    length = _LENGTH.search(overview)
    width = _WIDTH.search(overview)
    height = _HEIGHT.search(overview)
    seats = _SEATS.search(overview)
    berths = _BERTHS.search(overview)
    mtplm = _MTPLM.search(overview)
    mro = _MRO.search(overview)
    bedding = _BEDDING.search(overview)

    solution = bedding.group(1) if bedding else None
    mtplm_text = " ".join(mtplm.group(1).split()) if mtplm else None
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
        # Only the first of each pair is the outside figure; the second is internal.
        mh_length_mm=int(length.group(1)) if length else None,
        mh_width_mm=int(width.group(1)) if width else None,
        mh_height_mm=int(height.group(1)) if height else None,
        # The standard chassis is the first of `3500 / 3550 / 4100`; the rest are the
        # uprated options and are not what FMLV stores.
        mtplm_kilograms=_leading_int(mtplm_text),
        mtplm_text=mtplm_text,
        mro_kilograms=int(mro.group(1)) if mro else None,
        bedding_solution=solution,
        bed_types=bed_types_for(solution),
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


def dimension_conflicts(listing: MncListing, model: RimorModel) -> list[str]:
    """Where MNC and the factory disagree on a dimension by more than truncation allows.

    This is the adapter's self-check, and it is a genuine second source rather than the
    same number read twice: the two sites publish these independently. MNC truncates
    metres, so it reads up to 9 mm short of the factory's millimetres and no more —
    anything past `DIMENSION_TOLERANCE_MM` is a real conflict in the data, or a layout
    matched to the wrong factory page.
    """
    conflicts: list[str] = []
    for axis, mnc_mm, factory_mm in (
        ("length", listing.mnc_length_mm, model.mh_length_mm),
        ("width", listing.mnc_width_mm, model.mh_width_mm),
        ("height", listing.mnc_height_mm, model.mh_height_mm),
    ):
        if mnc_mm is None or factory_mm is None:
            continue
        if abs(mnc_mm - factory_mm) > DIMENSION_TOLERANCE_MM:
            conflicts.append(
                f"{axis} MNC {mnc_mm} mm vs rimor.it {factory_mm} mm "
                f"({mnc_mm - factory_mm:+d} mm)"
            )
    return conflicts


#: Trailing words in an MNC title that describe the vehicle rather than name the layout:
#: a model year, a transmission, a demo unit. Trimmed from the right one at a time, so
#: "Rimor Van 238 2026-Automatic" keeps `Van 238` — a leading pass over the whole string
#: would take the `Van` too, and Rimor's own name for it is "Rimor Van 238".
_TITLE_SUFFIX = re.compile(r"[\s,\-]*(?:automatic|demo\s+van|demo|van|20\d\d)\s*$", re.I)


def _model_name_from_title(listing: MncListing) -> str:
    """The layout's designation from an MNC title, for a layout with no factory page.

    "Rimor Horus 12- Automatic" becomes `12`, and "Rimor Van 238 2026-Automatic" becomes
    `Van 238`: FMLV renders manufacturer and range as their own fields, so both are
    dropped from the front, and the transmission and year are dropped from the back.
    """
    name = re.sub(rf"^\s*{re.escape(MANUFACTURER)}\s*", "", listing.title, flags=re.I)
    name = re.sub(rf"^\s*{re.escape(listing.range_label)}\s*", "", name, flags=re.I)
    while True:
        trimmed = _TITLE_SUFFIX.sub("", name)
        if trimmed == name:
            break
        name = trimmed
    return name.strip(" ,-") or listing.layout


def _build_extracted_motorhome(
    listing: MncListing, model: RimorModel | None
) -> ExtractedMotorhome:
    """One product: MNC's range membership and price, the factory's specification.

    `model` is `None` for a layout MNC sells that the factory has no page for — the
    Rimor Van 238, and a Horus 12 the factory has withdrawn. Those keep MNC's price,
    body type and base vehicle, and take seats and berths from MNC *only* when the two
    differ: MNC repeats its travel-seat count in the berth position on the coachbuilts,
    so two equal figures cannot be told apart from that bug and are left empty.
    """
    range_label = model.range_label if model else listing.range_label
    body_type = (model.body_type if model else None) or listing.body_type

    seats = model.mh_passenger_seats_inc_driver if model else None
    berths = model.berths if model else None
    mnc_counts_usable = (
        model is None
        and listing.mnc_berths is not None
        and listing.mnc_seats is not None
        and listing.mnc_berths != listing.mnc_seats
    )
    if mnc_counts_usable:
        seats, berths = listing.mnc_seats, listing.mnc_berths

    model_name = model.model if model is not None else _model_name_from_title(listing)

    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=range_label,
        model=model_name,
        base_vehicle_manufacturer=listing.base_vehicle_manufacturer,
        body_type=body_type,
        bed_types=model.bed_types if model and model.bed_types else [],
        mh_passenger_seats_inc_driver=seats,
        berths=berths,
        rrp_pounds=listing.rrp_pounds,
        mtplm_kilograms=model.mtplm_kilograms if model else None,
        mro_kilograms=model.mro_kilograms if model else None,
        mh_payload_kilograms=model.mh_payload_kilograms if model else None,
        mh_length_mm=model.mh_length_mm if model else None,
        mh_width_mm=model.mh_width_mm if model else None,
        mh_height_mm=model.mh_height_mm if model else None,
    )

    mnc_source = listing.url
    factory_source = BASE_URL + model.url if model else None
    label = f"{range_label} {model_name}"
    provenance: dict[str, Provenance] = {}

    def record(field_name: str, snippet: str, *, url: str) -> None:
        provenance[field_name] = Provenance(source_url=url, snippet=f"{label} — {snippet}")

    if listing.rrp_pounds is not None:
        # Say which of the two figures on a discounted page this is, so a reviewer can
        # see the choice rather than having to reconstruct it from the page.
        if listing.is_demo and listing.pre_discount_pounds is not None:
            note = (
                f"£{listing.rrp_pounds:,} before the demo-unit discount "
                f"({listing.title}) — the layout's own price"
            )
        elif listing.pre_discount_pounds is not None:
            note = f"£{listing.rrp_pounds:,}, reduced from £{listing.pre_discount_pounds:,}"
        else:
            note = f"£{listing.rrp_pounds:,}"
        record("rrp_pounds", f"{note}, the UK importer's listed price", url=mnc_source)
    if listing.base_vehicle_manufacturer is not None:
        record("base_vehicle_manufacturer", f"Vehicle: {listing.base_vehicle_manufacturer}", url=mnc_source)
    if body_type is not None:
        if model is not None and model.body_type is not None:
            record("body_type", f"listed under /{model.body_style}", url=factory_source or mnc_source)
        else:
            record("body_type", "from the MNC product categories", url=mnc_source)

    if model is None:
        if mnc_counts_usable:
            record(
                "mh_passenger_seats_inc_driver",
                f"{listing.mnc_seats} travel seats",
                url=mnc_source,
            )
            record("berths", f"{listing.mnc_berths} berth", url=mnc_source)
        return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)

    assert factory_source is not None
    if model.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            f"numero posti omologati (certified seats): {model.seats_text}",
            url=factory_source,
        )
    if model.berths is not None:
        # The cell text is kept verbatim: "4 (+1 opt)" says something the integer cannot,
        # namely that the fifth berth needs optional equipment.
        record("berths", f"numero posti letto (berths): {model.berths_text}", url=factory_source)
    for field_name, axis, value in (
        ("mh_length_mm", "Outside length", model.mh_length_mm),
        ("mh_width_mm", "Outside width", model.mh_width_mm),
        ("mh_height_mm", "Maximum outside height", model.mh_height_mm),
    ):
        if value is not None:
            record(field_name, f"{axis}: {value} mm", url=factory_source)
    if model.bed_types:
        record("bed_types", f"Bedding solution: {model.bedding_solution}", url=factory_source)
    if model.mtplm_kilograms is not None:
        note = f"Maximum overall weight: {model.mtplm_text} kg"
        if model.mtplm_text and "/" in model.mtplm_text:
            note += " — the standard chassis, the rest being uprated options"
        record("mtplm_kilograms", note, url=factory_source)
    if model.mro_kilograms is not None:
        record("mro_kilograms", f"MRO: {model.mro_kilograms} kg", url=factory_source)
    if model.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"{model.mtplm_kilograms} kg MTPLM - {model.mro_kilograms} kg MRO",
            url=factory_source,
        )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def _factory_index(
    http: Fetcher,
    range_slug: str,
    range_label: str,
    on_progress: Callable[[str], None],
) -> set[str]:
    """Every layout slug the factory publishes for one range.

    Read rather than probed: walking the range's body-style pages gives the exact slugs,
    so the `Plus` fallback in `_factory_slug` matches against what the site really has
    instead of guessing URLs and reading 302s. An empty set is not fatal — the range's
    MNC listings still become products, just without a specification.
    """
    range_url = f"{BASE_URL}/int/en/gamma/{range_slug}"
    result = http.fetch(range_url)
    if result.status_code != 200:
        on_progress(
            f"[{range_label}] rimor.it range page returned {result.status_code} — "
            f"specifications unavailable for this range"
        )
        return set()

    range_html = result.file_path.read_text(encoding="utf-8", errors="replace")
    slugs: set[str] = set()
    for body_style in parse_body_style_links(range_html, range_slug):
        listing = http.fetch(f"{BASE_URL}/int/en/gamma/{range_slug}/{body_style}")
        if listing.status_code != 200:
            on_progress(f"[{range_label}] /{body_style} returned {listing.status_code}")
            continue
        found = parse_model_slugs(
            listing.file_path.read_text(encoding="utf-8", errors="replace")
        )
        slugs.update(found)
        on_progress(f"[{range_label}] rimor.it /{body_style} publishes {len(found)} layout(s)")
    return slugs


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — both sites are server-rendered; see the docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect the UK Rimor range from MNC, specified from rimor.it.

    `ranges` selects which of the five to walk, so `--range Kilig` runs one of them.

    A failure on one page or one product is narrated and skipped. Only an MNC category
    page that cannot be fetched takes its whole range out, since that page is what says
    the range exists at all; a factory page that fails costs a product its specification
    but not its place in the range.
    """
    results: list[ExtractedMotorhome] = []

    for mnc_slug, factory_slug, range_label in ranges:
        category_url = f"{MNC_BASE_URL}{MNC_CATEGORY}/{mnc_slug}/"
        on_progress(f"[{range_label}] {category_url}")
        category = http.fetch(category_url)
        if category.status_code != 200:
            on_progress(
                f"[{range_label}] SKIPPED: MNC category page returned {category.status_code}"
            )
            continue

        slugs = parse_mnc_product_slugs(
            category.file_path.read_text(encoding="utf-8", errors="replace")
        )
        if not slugs:
            on_progress(f"[{range_label}] SKIPPED: no products linked from the category page")
            continue

        selected, set_aside = select_listings(slugs)
        on_progress(
            f"[{range_label}] MNC lists {len(slugs)} URL(s) -> {len(selected)} layout(s); "
            f"{len(set_aside)} set aside"
        )
        for slug, reason in sorted(set_aside.items()):
            on_progress(f"    {slug} — set aside: {reason}")

        available = _factory_index(http, factory_slug, range_label, on_progress)
        collected = 0
        matched: set[str] = set()

        for slug in sorted(selected):
            product_url = f"{MNC_BASE_URL}/product/{slug}/"
            product = http.fetch(product_url)
            if product.status_code != 200:
                on_progress(f"    {slug} — SKIPPED: returned {product.status_code}")
                continue

            listing = parse_mnc_listing(
                product.file_path.read_text(encoding="utf-8", errors="replace"),
                slug,
                product_url,
            )
            if listing is None:
                on_progress(f"    {slug} — SKIPPED: slug names no known range")
                continue
            if listing.rrp_pounds is None:
                on_progress(f"    {slug} — no price on the listing, rrp_pounds left empty")

            model: RimorModel | None = None
            factory_layout = _factory_slug(listing.layout, available)
            if factory_layout is None:
                on_progress(
                    f"    {listing.title} — no rimor.it page for layout "
                    f"{listing.layout!r}; MNC price and body type only"
                )
            else:
                matched.add(factory_layout)
                model_path = f"/int/en/gamma/{factory_slug}/modello/{factory_layout}"
                model_result = http.fetch(BASE_URL + model_path)
                if model_result.status_code != 200:
                    on_progress(
                        f"    {listing.title} — rimor.it returned "
                        f"{model_result.status_code}; MNC price and body type only"
                    )
                else:
                    model = parse_model_page(
                        model_result.file_path.read_text(encoding="utf-8", errors="replace"),
                        model_path,
                    )
                    if model is None:
                        on_progress(
                            f"    {listing.title} — no overview block on "
                            f"{model_path}; MNC price and body type only"
                        )

            if model is not None:
                if factory_layout != listing.layout:
                    on_progress(
                        f"    {listing.title} — matched rimor.it "
                        f"{factory_slug}/{factory_layout} (MNC still lists the "
                        f"pre-rename name {listing.layout!r})"
                    )
                for conflict in dimension_conflicts(listing, model):
                    on_progress(
                        f"    {listing.title} — CONFLICT: {conflict}; keeping the "
                        f"rimor.it figure"
                    )
                if not model.bed_types and model.bedding_solution:
                    on_progress(
                        f"    {listing.title} — unmapped bedding solution "
                        f"{model.bedding_solution!r}, bed types left empty"
                    )

            results.append(_build_extracted_motorhome(listing, model))
            collected += 1

        for unsold in sorted(available - matched):
            on_progress(
                f"    {factory_slug}/{unsold} — on rimor.it but not listed by MNC, "
                f"so not a UK product"
            )
        on_progress(f"[{range_label}] {collected} product(s)")

    on_progress(f"{len(results)} product(s) collected")
    return results
