"""Dethleffs (dethleffs.co.uk) — the twelfth adapter, an Erwin Hymer Group brand.

See `docs/adapters/dethleffs.md` for the full write-up. Dethleffs sell caravans on their
group sites, but **the GB edition lists none** — its navigation offers only "Motorhomes"
and "Camper Vans" and the sitemap has no caravan pages — so there is nothing to exclude.

**One source: the 48 per-model pages.** Each carries everything FMLV needs — price,
chassis, all three dimensions, both masses, berths, seats and body type — in plain
server-rendered HTML. No JavaScript, no PDF, no login. The two MY2027 GB technical-data
PDFs publish the same figures but **no prices at all**, so the website wins outright,
which is also the standing rule in `docs/adapters/README.md`.

**Take the roster from the sitemap.** `sitemap.xml` points at `sitemap.site_38.xml`,
which lists exactly the 48 model pages. Unusually, every source agrees: the union of
layout links across the 11 range pages is the same set, nothing missing either way. The
`/motorhomes` and `/camper-van` index pages link only to range pages, so they are not a
layout source. Note the campervan path is **`/camper-van`, singular** — `/campervans` 404s.

**Three things about this site actively mislead, and all three are handled by reading the
page's own body-type tag rather than any name:**

* **The Just Van is not a van.** It is tagged `Low Profile` — a 2.20 m-wide GRP
  coach-built on a Fiat Ducato. Flagged by the requester before the survey started.
* **Globebus is always a motorhome and Globetrail is always the campervan name**
  (requester, 2 September 2026; verified with zero violations across all 48). This is not
  a tautology, because **VW Crafter vehicles sit in both families** — `Globebus
  Performance` and `Globebus Performance 4x4` are low-profile motorhomes on a VW Crafter,
  while `Globetrail VW Performance` is a campervan on the same base vehicle.
* **Two range pages carry two ranges each.** `/motorhomes/trend-active` serves both
  `Trend Active Low profile` and `Trend Active A class`; `/motorhomes/alpa` serves both
  `Alpa Coachbuilt` and `Alpa A Class`. The range comes from each layout page's own table
  header, never from the URL — the path would collapse two ranges into one on 17 layouts.

**FMLV splits the identity inconsistently, and the adapter follows FMLV per range.** The
body letter lives in the *range* for Alpa, Trend Active and XL Family I, but in the
*model* for Just Camp Active, Globebus Active and XL. See `RANGE_MAP`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from html import unescape
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.dethleffs.co.uk"
MANUFACTURER = "Dethleffs"
MANUFACTURER_DISPLAY_NAME = "Dethleffs"

SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

#: (range path, label) for every range on the GB site, taken from the sitemap and
#: reconciled against all 11 range pages on 2 September 2026.
#:
#: These are *paths*, and a path is not a range: `motorhomes/trend-active` and
#: `motorhomes/alpa` each serve two ranges, distinguished only by the model letter. The
#: labels here name the path for `--range` and progress output; the range that reaches FMLV
#: always comes from the layout page's own table header via `RANGE_MAP`.
#:
#: Kept as a stated roster rather than derived from the sitemap alone so that a range
#: vanishing from the site is narrated instead of silently reducing the product count —
#: the `docs/adapters/README.md` rule that a stated roster beats any heuristic.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes/just-van", "Just Van"),
    ("motorhomes/globebus-active", "Globebus Active"),
    ("motorhomes/globebus-performance", "Globebus Performance"),
    ("motorhomes/globebus-performance-4x4", "Globebus Performance 4x4"),
    ("motorhomes/just-camp-active", "Just Camp Active"),
    ("motorhomes/trend-active", "Trend Active"),
    ("motorhomes/xl-a", "XL A"),
    ("motorhomes/xl-i", "XL I"),
    ("motorhomes/alpa", "Alpa"),
    ("camper-van/globetrail", "Globetrail"),
    ("camper-van/globetrail-active-plus", "Globetrail Active Plus"),
    ("camper-van/globetrail-performance", "Globetrail Performance"),
)

#: Site range heading -> (FMLV `manufacturer_range`, strip the leading model letter?).
#:
#: Checked against the real FMLV export for id 85 (186 products, 50 of them model year
#: 2026, fetched 2 September 2026). Per `docs/adapters/README.md` the export decides these
#: strings, and it is **inconsistent about where the body letter sits**: FMLV holds
#: `Alpa A` / `6820-2` and `Trend Active T` / `7057 EB` with the letter in the range, but
#: `Just Camp Active` / `T 7052 EB` and `Globebus Active` / `I 1` with it in the model. So
#: the flag is per range, not a rule.
#:
#: The site's own headings are never what FMLV holds. They survive in the provenance.
#:
#: Two ranges have no FMLV counterpart and keep their site name: **Just Van**, genuinely new
#: for MY2027 and tagged "New" in the site navigation, and **Globebus Performance**.
#:
#: `Globebus Performance 4x4` is deliberately *not* mapped onto FMLV's
#: `Globetrail VW Performance 4X4`. That baseline row is misfiled — a low-profile motorhome
#: under a Globetrail range name, which the Globebus/Globetrail rule forbids — and its
#: figures (6850 mm, 3880 kg, 3 berths) match this vehicle exactly. Emitting the correct
#: name proposes the fix; the matcher still pairs them, and both halves of the identity are
#: proposed together as `docs/adapters/README.md` requires.
RANGE_MAP: dict[str, tuple[str, bool]] = {
    "Alpa A Class": ("Alpa I", True),
    "Alpa Coachbuilt": ("Alpa A", True),
    "Trend Active A class": ("Trend Active I", True),
    "Trend Active Low profile": ("Trend Active T", True),
    "XL Family I": ("XL Family I", True),
    "XL Family A": ("XL", False),
    "Just Camp Active Low Profile": ("Just Camp Active", False),
    "Globebus Active A Class": ("Globebus Active", False),
    "Globebus Performance": ("Globebus Performance", False),
    "Globebus Performance 4x4": ("Globebus Performance 4x4", False),
    "Just Van": ("Just Van", False),
    "Globetrail Fiat": ("Globetrail Classic", False),
    "Globetrail Active Plus Fiat": ("Globetrail Active", False),
    "Globetrail VW Performance": ("Globetrail VW Performance", False),
}

#: `--range` selector -> the FMLV ranges it covers, for narrowing the baseline.
#:
#: Needed because a selector here is a **URL path**, and a path is not an FMLV range in
#: either direction: `motorhomes/alpa` serves two of them, and every path's site heading is
#: renamed by `RANGE_MAP` on the way to FMLV. The default scope in `cli.baseline_scope`
#: matches `manufacturer_range` against the selector label, which would find nothing for
#: `--range Alpa` and propose both Alpa layouts as new — a duplicate on upload.
#:
#: `Globebus Performance 4x4` also claims FMLV's `Globetrail VW Performance 4X4`. That row
#: is the misfiled one — a low-profile motorhome under a Globetrail name — and its figures
#: match this range's `T 46` exactly, so a run narrowed to this path must diff against it
#: rather than leave it unmatched and propose the vehicle twice.
RANGE_PATH_TO_FMLV_RANGES: dict[str, frozenset[str]] = {
    "Just Van": frozenset({"Just Van"}),
    "Globebus Active": frozenset({"Globebus Active"}),
    "Globebus Performance": frozenset({"Globebus Performance"}),
    "Globebus Performance 4x4": frozenset(
        {"Globebus Performance 4x4", "Globetrail VW Performance 4X4"}
    ),
    "Just Camp Active": frozenset({"Just Camp Active"}),
    "Trend Active": frozenset({"Trend Active T", "Trend Active I"}),
    "XL A": frozenset({"XL"}),
    "XL I": frozenset({"XL Family I"}),
    "Alpa": frozenset({"Alpa A", "Alpa I"}),
    "Globetrail": frozenset({"Globetrail Classic"}),
    "Globetrail Active Plus": frozenset({"Globetrail Active"}),
    "Globetrail Performance": frozenset({"Globetrail VW Performance"}),
}

#: Spec labels exactly as the page writes them, asterisks and all.
LABEL_PRICE = "Price (incl. VAT)"
LABEL_CHASSIS = "Standard chassis"
LABEL_LENGTH = "Overall length, approx."
LABEL_WIDTH = "Overall width, approx."
LABEL_HEIGHT = "Overall height, approx."
LABEL_MRO = "Mass in running order (+/-5%)*"
LABEL_MTPLM = "Technically permissible maximum laden mass*"
LABEL_SEATS = "Permitted number of seats (including driver)*"
LABEL_BERTHS = "Sleeping berths standard / max."

#: `Overall width with mirrors` is 60cm wider than the body and appears on the 10 Fiat
#: Globetrails only. `docs/adapters/README.md` requires the body width, so labels are
#: matched **exactly** rather than by prefix — `LABEL_WIDTH` would otherwise match both.
LABEL_WIDTH_WITH_MIRRORS = "Overall width with mirrors, approx."

#: The raised height of an open pop-top (358cm on the Globetrails), which is neither the
#: vehicle's height nor a variant of it. Named so it is documented rather than merely unused.
LABEL_HEIGHT_POPTOP_OPEN = "Overall height (open pop-top roof)"

#: A pop-top bed row exists only on layouts offering an elevating roof. Whether that roof is
#: standard or a cost option decides the body type — see `DethleffsLayout.body_type`.
LABEL_BED_POPTOP = "Bed dimension: pop-up roof, L x W, approx."

#: `Manufacturer-specified mass for optional equipment` sits **between** the two masses,
#: exactly where payload would go, and is not payload — it caps factory-fitted extras
#: (555 kg on the Just Van T 1 against a real payload of 888 kg). Named here so the mistake
#: is documented rather than merely avoided; Sunlight, Etrusco and Bürstner share the trap.
LABEL_NOT_PAYLOAD = "Manufacturer-specified mass for optional equipment*"

#: The site's own body tag, which is the only safe source: the model names lie (a "Just Van"
#: that is a coach-built) and so does the chassis (VW Crafters in both families).
_BODY_TYPES: dict[str, BodyType] = {
    "A Class": BodyType.A_CLASS,
    "Coachbuilt": BodyType.COACH_BUILT_OVER_CAB_BED,
    "Low Profile": BodyType.COACH_BUILT_LOW_PROFILE,
}

#: The tag Dethleffs give every campervan. It does not distinguish the four campervan body
#: types FMLV needs, so those are resolved from the roof — see `DethleffsLayout.body_type`.
CAMPERVAN_TAG = "Camper Van"

#: Marks a value as available only as a cost option, e.g. `265 / 278 (○)`, `4 - 5 (○)`.
OPTIONAL_MARK = "○"

#: Family name -> whether it is a motorhome, per the requester's rule of 2 September 2026.
#: Verified against all 48 layouts with zero violations. Used as a self-check, not to
#: classify: the body type still comes from the page tag.
FAMILY_IS_MOTORHOME: dict[str, bool] = {"Globebus": True, "Globetrail": False}

#: A campervan taller than this is a high top. Same threshold as `etrusco`, `auto_trail`
#: and `chausson`, set by the NCC side from FMLV's own data: the tallest standard-height
#: campervan is 2050mm. Dethleffs' campervans are 2650–2670mm.
HIGH_TOP_ABOVE_MM = 2300

#: Bounds on a plausible payload, in kg. The real spread here is 439–1588 kg, the top end
#: being the 5400 kg XL Family chassis.
MIN_PAYLOAD_KG = 100
MAX_PAYLOAD_KG = 2500

#: How much the printed tolerance band may differ from the recomputed one. The band is the
#: mass ±5% rounded to whole kilograms, so a kilogram or two of slack is rounding, not error.
BAND_TOLERANCE_KG = 3

_SITEMAP_LOC = re.compile(r"<loc>\s*(?P<url>.*?)\s*</loc>", re.S)

#: A layout page: exactly three path segments, the first being a vehicle section.
_MODEL_URL = re.compile(
    r"^https://www\.dethleffs\.co\.uk/(?P<section>motorhomes|camper-van)/(?P<range>[^/]+)/(?P<layout>[^/]+)$"
)

#: The technical-data modal. Five tables on a page share this class — the spec table is the
#: one whose `<thead>` holds **two** `<th>` cells (range and model); the other four are
#: equipment lists with one. See `parse_spec_table`.
_TABLE = re.compile(r"<table[^>]*has-columns--1\+[^>]*>(?P<body>.*?)</table>", re.S)
_TH = re.compile(r"<th[^>]*>(?P<cell>.*?)</th>", re.S)
_ROW = re.compile(r"<tr\s*>(?P<row>.*?)</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(?P<cell>.*?)</td>", re.S)

#: The body-type tag, e.g. `<span class="a-tags__label fs-body-7">Low Profile</span>`.
_BODY_TAG = re.compile(r"<span class=\"a-tags__label[^\"]*\">(?P<tag>.*?)</span>", re.S)

#: The "main facts" card, which re-renders six of the spec table's values in a different
#: structure. Parsed so the two can be compared — see `_card_reconciles`.
_MAIN_FACT = re.compile(
    r"<dd class=\"m-mainfacts__label[^\"]*\">(?P<label>.*?)</dd>\s*"
    r"<dt class=\"m-mainfacts__text[^\"]*\">(?P<value>.*?)</dt>",
    re.S,
)

CARD_LENGTH = "Length"
CARD_WIDTH = "Width"
CARD_HEIGHT = "Height"
CARD_BERTHS_MAX = "Sleeping berths max."
CARD_MTPLM = "Technically permissible maximum laden mass"
CARD_MRO = "Mass in running order"
CARD_PRICE = "Price"


def _clean(markup: str) -> str:
    """Cell text with footnote superscripts and modal buttons removed.

    Both matter. Footnote markers sit **inside** the value cell as `<sup>1</sup>`, so
    `<td>273 <sup>1</sup></td>` reads as 2731mm tall without this. The main-facts card
    wraps an info `<button>` whose `data-content` is a URL-encoded paragraph full of digits.
    """
    markup = re.sub(r"<sup[^>]*>.*?</sup>", " ", markup, flags=re.S)
    markup = re.sub(r"<button.*?</button>", " ", markup, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(markup))).strip()


def _pounds(value: str) -> int | None:
    """`'£61,990.00'` -> `61990`, dropping the pence the site always prints as `.00`."""
    match = re.search(r"[\d,]+", value)
    if not match:
        return None
    digits = match.group(0).replace(",", "")
    return int(digits) if digits else None


def _centimetres_to_mm(value: str) -> int | None:
    """`'265 / 278 (○)'` -> `2650`. Dethleffs quote every dimension in whole centimetres.

    The **first** figure, per the base-vehicle rule in `docs/adapters/README.md`: all ten
    Fiat Globetrails print `265 / 278 (○)`, the second being the optional pop-top roof.
    """
    match = re.search(r"\d+", value)
    return int(match.group(0)) * 10 if match else None


def _kilograms(value: str) -> int | None:
    """`'2611 (2480 to 2742)*'` -> `2611`, the nominal mass before its tolerance band."""
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def _band(value: str) -> tuple[int, int] | None:
    """`'2611 (2480 to 2742)*'` -> `(2480, 2742)`, the legally permissible ±5% range."""
    match = re.search(r"\(\s*(\d+)\s*(?:to|-|–)\s*(\d+)\s*\)", value)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _standard_count(value: str) -> int | None:
    """The standard figure of a published count, which prints in three different shapes.

    `'2 / 3 (○)'` -> 2 and `'4 - 5 (○)'` -> 4, the lower figure per the data rules in
    `docs/adapters/README.md`. But 18 of the 48 layouts print berths as a **single** number
    (`'4'`), meaning standard and maximum are the same — a parser expecting `n / n` drops
    those silently, so the first integer is taken whatever the shape.
    """
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


@dataclass(frozen=True)
class DethleffsLayout:
    """One layout, as read from its own model page.

    `range_heading` is the range as the site markets it — `Alpa Coachbuilt`, `Globetrail
    Fiat` — and `model` is the name as published, `A 6820-2`. **Neither is necessarily what
    goes into FMLV**: see `fmlv_range` and `fmlv_model`.
    """

    url: str
    section: str
    range_heading: str
    model: str
    body_tag: str | None = None
    rrp_pounds: int | None = None
    berths_published: str | None = None
    seats_published: str | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    mro_band: tuple[int, int] | None = None
    base_vehicle_manufacturer: str | None = None
    poptop_published: str | None = None
    card: dict[str, str] | None = None

    @property
    def label(self) -> str:
        return f"{self.range_heading} {self.model}".strip()

    @property
    def family(self) -> str:
        """`Globetrail` from `Globetrail Active Plus Fiat` — the first word of the range."""
        return self.range_heading.split(" ", 1)[0].strip()

    @property
    def fmlv_range(self) -> str:
        """The range as FMLV records it, from `RANGE_MAP`.

        An unmapped heading falls back to the site's own, which is visible but wrong rather
        than silently mis-filed under a neighbouring range.
        """
        mapped = RANGE_MAP.get(self.range_heading)
        return mapped[0] if mapped else self.range_heading

    @property
    def fmlv_model(self) -> str:
        """The model as FMLV records it, with the body letter stripped only where FMLV
        keeps it in the range instead.

        `A 6820-2` -> `6820-2` for Alpa, but `T 7052 EB` stays whole for Just Camp Active,
        because that is how the export holds each of them.
        """
        mapped = RANGE_MAP.get(self.range_heading)
        if mapped is None or not mapped[1]:
            return self.model
        parts = self.model.split(" ", 1)
        return parts[1].strip() if len(parts) > 1 else self.model

    @property
    def berths(self) -> int | None:
        return _standard_count(self.berths_published) if self.berths_published else None

    @property
    def mh_passenger_seats_inc_driver(self) -> int | None:
        return _standard_count(self.seats_published) if self.seats_published else None

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload, which Dethleffs do not publish, as `MTPLM - MRO`.

        The presentation FMLV wants, as for Etrusco and Bürstner. Note the table's
        `LABEL_NOT_PAYLOAD` row sits between the two masses and is emphatically not this.
        """
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms

    @property
    def has_standard_elevating_roof(self) -> bool:
        """Whether a pop-top is fitted as standard rather than offered as a cost option.

        Per `docs/adapters/README.md`, an elevating roof offered as an *option* does not
        change what the vehicle is — so only an unmarked pop-top row counts. Every Dethleffs
        pop-top is currently marked `(○)`, so this is `False` throughout; it is written as a
        rule rather than a constant so a future standard-fit roof classifies itself.
        """
        return bool(self.poptop_published) and OPTIONAL_MARK not in self.poptop_published

    @property
    def body_type(self) -> BodyType | None:
        """From the site's own tag, and never from the model name or the base vehicle.

        Both would be wrong here: the Just Van is a coach-built despite its name, and VW
        Crafters underpin four motorhomes and two campervans. The tag is unambiguous, is one
        of exactly four values across all 48, and is corroborated — precisely the five
        `Coachbuilt` layouts carry an alcove bed row.

        A campervan's type turns on its roof, so the tag alone is not enough for those: the
        2×2 in `docs/adapters/README.md` crosses body height with whether an elevating roof
        is standard. An unrecognised tag is a blank, not the nearest known type.
        """
        if self.body_tag == CAMPERVAN_TAG:
            if self.mh_height_mm is None:
                return None
            high_top = self.mh_height_mm > HIGH_TOP_ABOVE_MM
            if self.has_standard_elevating_roof:
                return (
                    BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF
                    if high_top
                    else BodyType.CAMPERVAN_ELEVATING_ROOF
                )
            return BodyType.CAMPERVAN_HIGH_TOP if high_top else BodyType.CAMPERVAN
        return _BODY_TYPES.get(self.body_tag or "")


def baseline_in_scope(motorhome: Motorhome, labels: set[str]) -> bool:
    """Which baseline rows a `--range`-narrowed run should diff against.

    Picked up by `cli.baseline_scope` with `getattr`, the same opt-in as `DEFAULT_RANGES`,
    so no other adapter is affected. The default there matches the FMLV `manufacturer_range`
    against the selector label, which is wrong here for two reasons: a selector is a URL
    path, and `motorhomes/alpa` alone serves both `Alpa A` and `Alpa I`; and every site
    heading is renamed by `RANGE_MAP` before it reaches FMLV, so no selector label is an
    FMLV range name at all.

    Getting this wrong is not cosmetic in either direction, per `cli.baseline_scope`: too
    narrow and a product FMLV already holds is proposed as new, which uploads a duplicate;
    too wide and live products the run never swept are reported as disappeared.
    """
    wanted: set[str] = set()
    for label in labels:
        wanted |= RANGE_PATH_TO_FMLV_RANGES.get(label, {label})
    return motorhome.manufacturer_range in wanted


def _band_reconciles(layout: DethleffsLayout) -> bool:
    """Whether the printed tolerance band matches the mass it belongs to.

    Dethleffs print the mass in running order with its legally permissible ±5% range in
    brackets: `2611 (2480 to 2742)`. The band is a **function of the mass**, so the pair must
    be self-consistent, which makes it a free test that both were read from the same row. The
    same device Sunlight, Etrusco and Bürstner use. A few kilograms of slack is allowed
    because the band is printed rounded to whole kilograms.
    """
    if layout.mro_kilograms is None or layout.mro_band is None:
        return True  # nothing to contradict
    low, high = layout.mro_band
    expected_low = Decimal(layout.mro_kilograms) * Decimal("0.95")
    expected_high = Decimal(layout.mro_kilograms) * Decimal("1.05")
    return (
        abs(Decimal(low) - expected_low) <= BAND_TOLERANCE_KG
        and abs(Decimal(high) - expected_high) <= BAND_TOLERANCE_KG
    )


def _card_disagreements(layout: DethleffsLayout) -> list[str]:
    """Fields where the main-facts card contradicts the specification table.

    The strongest check available here, and one no other adapter has: the page renders six
    values **twice**, in two unrelated DOM structures, so comparing them catches a mis-read
    row that the ±5% band cannot — the band only proves a mass is paired with its own
    tolerance, not that the right row was read in the first place.

    A field missing from the card is not a disagreement; only a value that is present and
    different is. All 48 × 6 comparisons agreed on 2 September 2026.
    """
    if not layout.card:
        return []
    checks: tuple[tuple[str, str, int | None], ...] = (
        (CARD_LENGTH, "length", layout.mh_length_mm),
        (CARD_WIDTH, "width", layout.mh_width_mm),
        (CARD_HEIGHT, "height", layout.mh_height_mm),
        (CARD_MTPLM, "maximum laden mass", layout.mtplm_kilograms),
        (CARD_MRO, "running order mass", layout.mro_kilograms),
        (CARD_PRICE, "price", layout.rrp_pounds),
    )
    disagreements: list[str] = []
    for card_label, name, table_value in checks:
        raw = layout.card.get(card_label)
        if raw is None or table_value is None:
            continue
        card_value = _pounds(raw) if card_label == CARD_PRICE else _kilograms(raw)
        if card_value is None:
            continue
        if card_label in (CARD_LENGTH, CARD_WIDTH, CARD_HEIGHT):
            card_value *= 10  # the card prints centimetres too, as `599 cm`
        if card_value != table_value:
            disagreements.append(f"{name} (table {table_value}, card {card_value})")
    return disagreements


def _family_disagreement(layout: DethleffsLayout) -> str | None:
    """Whether family name, URL section and body tag disagree about motorhome vs campervan.

    Globebus is always a motorhome and Globetrail always a campervan (requester rule), the
    URL section says the same thing independently, and so does the body tag. Three
    statements of one fact, from three parts of the site, so a page that has been rebuilt
    around a different layout shows up here rather than as a plausible wrong body type.
    """
    if layout.body_tag is None:
        return None
    tagged_motorhome = layout.body_tag in _BODY_TYPES
    if (layout.section == "motorhomes") != tagged_motorhome:
        return (
            f"the URL section '{layout.section}' and the body tag "
            f"'{layout.body_tag}' disagree about motorhome vs campervan"
        )
    expected = FAMILY_IS_MOTORHOME.get(layout.family)
    if expected is not None and expected != tagged_motorhome:
        kind = "a motorhome" if expected else "a campervan"
        return (
            f"'{layout.family}' is always {kind}, but the body tag is "
            f"'{layout.body_tag}'"
        )
    return None


def _reconciles(layout: DethleffsLayout) -> bool:
    """Whether a layout's masses are consistent enough to propose."""
    mtplm, mro = layout.mtplm_kilograms, layout.mro_kilograms
    if mtplm is None or mro is None:
        return True
    if mtplm <= mro:
        return False
    return MIN_PAYLOAD_KG <= mtplm - mro <= MAX_PAYLOAD_KG


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_sitemap_model_urls(index_xml: str, sitemap_xml: str) -> list[str]:
    """Every model page URL, in sitemap order.

    Two documents because `sitemap.xml` is an index holding a single `<loc>` that points at
    `sitemap.site_38.xml`; the model URLs are all in the second. Filtered to exactly three
    path segments under a vehicle section, which excludes the range pages, the configurator
    (`/configurator/motorhomes/...`) and marketing pages that share a prefix.
    """
    urls = _SITEMAP_LOC.findall(sitemap_xml) or _SITEMAP_LOC.findall(index_xml)
    seen: dict[str, None] = {}
    for url in urls:
        if _MODEL_URL.match(url):
            seen.setdefault(url, None)
    return list(seen)


def parse_spec_table(page_html: str) -> tuple[str | None, str | None, dict[str, str]]:
    """The technical-data modal as `(range, model, {label: value})`.

    Five tables on a page carry the modal's class; the specification is the one whose
    `<thead>` holds **two** `<th>` cells, the range and then the model. The other four are
    equipment lists (`Electrical installation`, `Heating`, `Water supply`, `Gas supply`)
    with a single header cell, and taking the first table blindly would read one of those on
    any page where the order changed.

    Rows are a flat run of `<tr><td>label</td><td>value</td></tr>`, so there is no column
    alignment to get wrong — the risk that dominates the Morelo, Swift and Rimor adapters
    does not arise here.
    """
    for match in _TABLE.finditer(page_html):
        table = match.group("body")
        headers = [_clean(cell) for cell in _TH.findall(table)]
        if len(headers) != 2:
            continue
        specs: dict[str, str] = {}
        for row in _ROW.findall(table):
            cells = [_clean(cell) for cell in _CELL.findall(row)]
            if len(cells) == 2 and cells[0]:
                specs.setdefault(cells[0], cells[1])
        return headers[0] or None, headers[1] or None, specs
    return None, None, {}


def parse_main_facts(page_html: str) -> dict[str, str]:
    """The main-facts card as `{label: value}` — the page's second rendering of six specs."""
    return {
        _clean(match.group("label")): _clean(match.group("value"))
        for match in _MAIN_FACT.finditer(page_html)
    }


def parse_body_tag(page_html: str) -> str | None:
    """The site's own body-type tag: `A Class`, `Coachbuilt`, `Low Profile` or `Camper Van`."""
    match = _BODY_TAG.search(page_html)
    return _clean(match.group("tag")) or None if match else None


def parse_layout(url: str, page_html: str) -> DethleffsLayout | None:
    """One layout from its model page, or `None` if the page carries no specification."""
    match = _MODEL_URL.match(url)
    if match is None:
        return None
    range_heading, model, specs = parse_spec_table(page_html)
    if not range_heading or not model or not specs:
        return None
    mro_raw = specs.get(LABEL_MRO, "")
    chassis = specs.get(LABEL_CHASSIS, "")
    return DethleffsLayout(
        url=url,
        section=match.group("section"),
        range_heading=range_heading,
        model=model,
        body_tag=parse_body_tag(page_html),
        rrp_pounds=_pounds(specs.get(LABEL_PRICE, "")),
        berths_published=specs.get(LABEL_BERTHS) or None,
        seats_published=specs.get(LABEL_SEATS) or None,
        mh_length_mm=_centimetres_to_mm(specs.get(LABEL_LENGTH, "")),
        # Exact label, so the 60cm-wider `with mirrors` row on the Globetrails cannot win.
        mh_width_mm=_centimetres_to_mm(specs.get(LABEL_WIDTH, "")),
        mh_height_mm=_centimetres_to_mm(specs.get(LABEL_HEIGHT, "")),
        mtplm_kilograms=_kilograms(specs.get(LABEL_MTPLM, "")),
        mro_kilograms=_kilograms(mro_raw),
        mro_band=_band(mro_raw),
        base_vehicle_manufacturer=chassis.split()[0] if chassis else None,
        poptop_published=specs.get(LABEL_BED_POPTOP) or None,
        card=parse_main_facts(page_html),
    )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(layout: DethleffsLayout) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=layout.fmlv_range,
        model=layout.fmlv_model,
        base_vehicle_manufacturer=layout.base_vehicle_manufacturer,
        berths=layout.berths,
        mh_passenger_seats_inc_driver=layout.mh_passenger_seats_inc_driver,
        rrp_pounds=layout.rrp_pounds,
        mtplm_kilograms=layout.mtplm_kilograms,
        mro_kilograms=layout.mro_kilograms,
        mh_payload_kilograms=layout.mh_payload_kilograms,
        mh_length_mm=layout.mh_length_mm,
        mh_width_mm=layout.mh_width_mm,
        mh_height_mm=layout.mh_height_mm,
        body_type=layout.body_type,
    )

    provenance: dict[str, Provenance] = {}

    def record(field: str, snippet: str) -> None:
        provenance[field] = Provenance(source_url=layout.url, snippet=f"{layout.label} — {snippet}")

    # Both halves of the identity, always together: they are one name split across two
    # columns, and accepting a range rename without the matching model rename corrupts it.
    identity = (
        f"site publishes range '{layout.range_heading}' and model '{layout.model}'; FMLV "
        f"holds range '{layout.fmlv_range}' and model '{layout.fmlv_model}'. The two halves "
        f"belong together — accept both or neither"
    )
    record("manufacturer_range", identity)
    record("model", identity)

    if layout.rrp_pounds is not None:
        record(
            "rrp_pounds",
            f"Price (incl. VAT) £{layout.rrp_pounds:,} — a recommended retail price in GBP "
            f"including VAT and On The Road Charges (delivery from Germany, registration and "
            f"PDI), import duties excluded",
        )
    if layout.berths is not None:
        record(
            "berths",
            f"Sleeping berths standard / max. '{layout.berths_published}', "
            f"standard figure {layout.berths}",
        )
    if layout.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            f"Permitted number of seats (including driver): '{layout.seats_published}', "
            f"standard figure {layout.mh_passenger_seats_inc_driver}",
        )
    if layout.mh_length_mm is not None:
        record("mh_length_mm", f"Overall length, approx. {layout.mh_length_mm / 10:.0f}cm")
    if layout.mh_width_mm is not None:
        record(
            "mh_width_mm",
            f"Overall width, approx. {layout.mh_width_mm / 10:.0f}cm — the body width, "
            f"excluding mirrors",
        )
    if layout.mh_height_mm is not None:
        record(
            "mh_height_mm",
            f"Overall height, approx. {layout.mh_height_mm / 10:.0f}cm (the standard roof "
            f"where a taller one is optional)",
        )
    if layout.mtplm_kilograms is not None:
        record(
            "mtplm_kilograms",
            f"Technically permissible maximum laden mass: {layout.mtplm_kilograms}kg",
        )
    if layout.mro_kilograms is not None:
        band = (
            f" (permissible range {layout.mro_band[0]} to {layout.mro_band[1]}kg, ±5%)"
            if layout.mro_band
            else ""
        )
        record("mro_kilograms", f"Mass in running order: {layout.mro_kilograms}kg{band}")
    if layout.base_vehicle_manufacturer is not None:
        record("base_vehicle_manufacturer", f"Standard chassis: {layout.base_vehicle_manufacturer}")
    if layout.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"derived: {layout.mtplm_kilograms}kg maximum laden - {layout.mro_kilograms}kg "
            f"running order = {layout.mh_payload_kilograms}kg. Dethleffs publish no payload, "
            f"and their 'manufacturer-specified mass for optional equipment' is not one",
        )
    if layout.body_type is not None:
        detail = f"the site's own '{layout.body_tag}' tag"
        if layout.body_tag == CAMPERVAN_TAG:
            roof = "standard" if layout.has_standard_elevating_roof else "a cost option"
            detail += (
                f", with the {layout.mh_height_mm}mm body deciding high top (threshold "
                f"{HIGH_TOP_ABOVE_MM}mm) and the elevating roof being {roof}"
            )
        record("body_type", f"from {detail}, not from the model name or the base vehicle")
    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Dethleffs needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect the GB range: the sitemap for the roster, then one fetch per model page.

    A model page that cannot be read is narrated and skipped rather than raised, so one
    rebuilt page does not cost the other 47. An unreachable sitemap does raise — without it
    there is no roster at all, and silently collecting nothing would look like a
    manufacturer that had discontinued its entire range.
    """
    on_progress(f"fetching the sitemap index {SITEMAP_URL} ...")
    index = http.fetch(SITEMAP_URL)
    if index.status_code != 200:
        msg = f"sitemap index {SITEMAP_URL} returned {index.status_code}"
        raise RuntimeError(msg)
    index_xml = index.file_path.read_text(encoding="utf-8", errors="replace")

    sitemap_xml = ""
    nested = [url for url in _SITEMAP_LOC.findall(index_xml) if url.endswith(".xml")]
    for url in nested:
        on_progress(f"fetching the sitemap {url} ...")
        page = http.fetch(url)
        if page.status_code == 200:
            sitemap_xml += page.file_path.read_text(encoding="utf-8", errors="replace")

    model_urls = parse_sitemap_model_urls(index_xml, sitemap_xml)
    if not model_urls:
        msg = "no model pages found in the sitemap"
        raise RuntimeError(msg)

    wanted_paths = [path for path, _label in ranges]
    on_progress(f"{len(model_urls)} model page(s) in the sitemap, across {len(wanted_paths)} range path(s)")

    results: list[ExtractedMotorhome] = []
    for path, range_label in ranges:
        prefix = f"{BASE_URL}/{path}/"
        in_range = [url for url in model_urls if url.startswith(prefix)]
        # A stated roster beats a heuristic: a range that vanishes from the sitemap is
        # narrated rather than quietly reducing the product count.
        if not in_range:
            on_progress(f"[{range_label}] WARNING: no layouts found under {prefix}")
            continue
        on_progress(f"[{range_label}] {len(in_range)} layout(s)")

        for url in in_range:
            page = http.fetch(url)
            if page.status_code != 200:
                on_progress(f"[{range_label}] SKIPPED {url}: returned {page.status_code}")
                continue
            layout = parse_layout(url, page.file_path.read_text(encoding="utf-8", errors="replace"))
            if layout is None:
                on_progress(f"[{range_label}] SKIPPED {url}: no specification table found")
                continue

            if layout.range_heading not in RANGE_MAP:
                on_progress(
                    f"[{layout.label}] WARNING: range heading '{layout.range_heading}' is not "
                    f"in RANGE_MAP, so the site's own name is used and may not match FMLV"
                )
            disagreement = _family_disagreement(layout)
            if disagreement is not None:
                on_progress(f"[{layout.label}] SKIPPED: {disagreement}")
                continue
            if not _band_reconciles(layout):
                on_progress(
                    f"[{layout.label}] SKIPPED: the printed tolerance band {layout.mro_band} "
                    f"is not ±5% of the {layout.mro_kilograms}kg running order, so the two "
                    f"may have come from different rows"
                )
                continue
            card_issues = _card_disagreements(layout)
            if card_issues:
                on_progress(
                    f"[{layout.label}] SKIPPED: the specification table and the main-facts "
                    f"card disagree on {', '.join(card_issues)}"
                )
                continue
            if not _reconciles(layout):
                on_progress(
                    f"[{layout.label}] SKIPPED: masses don't reconcile (maximum laden "
                    f"{layout.mtplm_kilograms}kg, running order {layout.mro_kilograms}kg)"
                )
                continue

            for field, value in (
                ("price", layout.rrp_pounds),
                ("berths", layout.berths),
                ("length", layout.mh_length_mm),
                ("maximum laden mass", layout.mtplm_kilograms),
                ("body type", layout.body_type),
            ):
                if value is None:
                    on_progress(f"[{layout.label}] WARNING: no {field} published, left blank")
            results.append(_build_extracted_motorhome(layout))

    on_progress(f"{len(results)} product(s) collected")
    return results
