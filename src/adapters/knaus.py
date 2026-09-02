"""Knaus (knaus.com/en-gb) — motorhomes and campervans, KNAUS brand only.

See `docs/adapters/knaus.md` for the full write-up.

**Scope.** Knaus Tabbert AG owns KNAUS, TABBERT, WEINSBERG, T@B, MORELO and RENT AND
TRAVEL. This adapter covers **KNAUS-branded vehicles only** — confirmed by the requester
1 September 2026, and matched by the NCC export dropdown, which lists `Knaus`, `Weinsberg`
and `Morelo` as three separate suppliers. `knaus.com` carries nothing but KNAUS, so the
scoping needs no filtering.

**The range called VAN is a motorhome range, not a campervan range.** VAN TI VANSATION,
VAN TI VW VANSATION and VAN TI PLUS are all coachbuilts and all live under
`/en-gb/motorhomes/`. The campervans are BOXTIME and BOXLIFE PLATINUM SELECTION only.

## Two sources, and why both

**The website is primary.** Each layout has its own page under
`/en-gb/{motorhomes,camper-vans}/<range-slug>/<model-slug>`, plain server-rendered HTML
carrying a 25-row `<dt>`/`<dd>` specification list. One URL is one vehicle, so attribution
is free and there is no column to misalign — the Auto-Trail end of the risk spectrum
rather than the Rimor end. The price and the model year come from the card on the Layouts
index that links the page, not from the page itself.

**The per-range UK price list supplies two things the website cannot.** Each layout page
links its own range's price list on `konfigurator.knaustabbert.de`, so the document is
rediscovered every run rather than hardcoded:

* **`Three-point belts in driving direction`** — the belted travel seats fitted as
  standard, which the website never publishes. See the seats section below.
* **The base `Technically maximum authorised laden mass`.** The website publishes the
  *uprated* figure on two layouts; the price list publishes the base one and prices the
  uprate as an option. See `_MTPLM` below.

It also republishes length, width, height, MRO and price, which agree with the website on
**28 of 28 layouts** — a cross-document check in the Rimor sense, used here to drop a
product whose two sources disagree rather than to guess which is right.

Discovering the price list from the *layout page* rather than from a downloads index is
deliberate: the same brand publishes a German `VAN TI DE | DE` price list and two combined
motorhome/campervan lists, and the layout page links only the English per-range one.

## The traps

**German thousands separators, everywhere.** `3.500 kg` is 3500 and `75.895 GBP` is
£75,895. `_thousands` is the only number parser in this module for that reason.

**Centimetres.** Every dimension is cm; FMLV wants mm.

**`Mass in running order` is printed twice.** 18 of the 28 layouts print the row twice
with two different figures, byte-identical labels and byte-identical tooltips — on the
German site and in the price list too, so it is real in Knaus's data rather than a
rendering bug. `parse_layout_page` takes the **first**, which is the one that pairs with
the `Chassis`/`Engine power`/`Gearbox` rows immediately above it, and carries both into
the provenance snippet so a reviewer can see what was discarded.

**`Maximum payload` is not payload.** The site's `Maximum payload (kg)` and
`Remaining payload (kg)` are EU 2021/535 homologation figures net of passenger mass and
the manufacturer's optional-equipment allowance; the SKY TI VW 650 MEG's is **8 kg** on the
website and **-161 kg** in the price list. Neither is FMLV's payload, and no arithmetic
relating them to the masses holds on any of the 28 layouts. They are never read.
`mh_payload_kilograms` is derived as `MTPLM - MRO`, which is what FMLV's own baseline
holds on 29 of its 33 current rows.

## Seats: the ceiling, the cab, and the real figure

The sources publish four person-counts and only one is `mh_passenger_seats_inc_driver`:

| Row | Where | Meaning |
|---|---|---|
| `Number of persons allowed in driving operation` | both | **type-approval ceiling** |
| `Max. belt-secured seats` | both | fitment ceiling |
| `Automatic three-point belts` | both | 2 on all 28 — the cab's inertia-reel belts |
| `Three-point belts in driving direction` | **price list only** | **belted seats fitted as standard** |

The first is disqualified by Knaus's own words. The price list's legal section defines it
as *"the permissible number of occupants in running order, as determined by the
manufacturer during the type-approval process"*, used to compute a 75 kg-per-passenger
mass — which is exactly the row `docs/adapters/burstner.md` established is not this field.

`Three-point belts in driving direction` reads 2 on 26 layouts and **4** on SKY TI VW
650 MEG and VAN TI PLUS 650 MEG, and the options table corroborates those two: the add-on
`Two folding seats with 3-point seat belts` is `-` (not possible) on the 650 MEG, whose
L-shaped seating group is standard, and only `o` on the 700s. So the 4s are standard
fitment and the 2s are the base vehicle, per the base-vehicle rule.

Decision from the requester, 1 September 2026: record the belted-seat figure even though
FMLV's baseline holds 4 on 32 of 33 rows. This will propose 2 on most products.

## Body type

Derived, and validated against all 33 current FMLV rows before adoption — **33 of 33
agree**, no exceptions either way:

* `/camper-vans/` -> `campervan_high_top`. Every campervan is 2580 mm or 2780 mm, well
  over `HIGH_TOP_ABOVE_MM`, and **no campervan page mentions a pop-top at any height** —
  the word and every synonym appear zero times on all ten — so the silence-means-option
  rule leaves them as plain high tops.
* L!VE I -> `a_class`. The catalogue heads its section *"Welcome to our fully-integrated
  motorhomes"*.
* every other motorhome -> `coach_built_low_profile`, from the catalogue's
  *"Welcome to our semi-integrated motorhomes"*.
"""

from __future__ import annotations

import html as html_module
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://www.knaus.com"
MANUFACTURER = "Knaus Tabbert AG Knaus"
MANUFACTURER_DISPLAY_NAME = "Knaus"

#: The two Layouts index pages. Each renders one card per layout of its whole category,
#: server-side — the `?fModels=` links on the page are a client-side filter, so one fetch
#: per category is the entire roster.
LAYOUT_INDEXES: tuple[tuple[str, str], ...] = (
    ("motorhomes", f"{BASE_URL}/en-gb/motorhomes/layouts"),
    ("camper-vans", f"{BASE_URL}/en-gb/camper-vans/layouts"),
)

#: `(category, range label)`. The label is the range name exactly as the site's own card
#: prints it, which is also what the adapter emits as `manufacturer_range` — FMLV's
#: current names are a model generation behind (`Sky TI` for `SKY TI VW`), so every one of
#: these proposes a rename. All eight renames score above `diff.matching`'s threshold, so
#: unlike Wingamm they can all actually be delivered; see `docs/adapters/knaus.md`.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes", "VAN TI VANSATION"),
    ("motorhomes", "VAN TI VW VANSATION"),
    ("motorhomes", "VAN TI PLUS"),
    ("motorhomes", "L!VE TI PLATINUM SELECTION"),
    ("motorhomes", "L!VE WAVE PLATINUM SELECTION"),
    ("motorhomes", "SKY TI VW"),
    ("motorhomes", "L!VE I"),
    ("camper-vans", "BOXTIME"),
    ("camper-vans", "BOXLIFE PLATINUM SELECTION"),
)

#: The range whose motorhomes are fully integrated. Everything else under `/motorhomes/`
#: is semi-integrated — see the module docstring's body-type section.
_A_CLASS_RANGES = frozenset({"L!VE I"})

#: A campervan taller than this is a high top. Same shared threshold as `bailey.py`,
#: `auto_trail.py` and `chausson.py`, set by the NCC side from FMLV's own data.
HIGH_TOP_ABOVE_MM = 2300

#: Raised from `diff.matching.DEFAULT_THRESHOLD` (0.5), read by `cli.match_threshold`.
#:
#: The 2027 SKY TI is a **replacement**, not a revision: KNAUS moved it from the Fiat
#: Ducato to the VW Crafter, renamed it `SKY TI VW`, and replaced the `700 MEG` layout
#: with a `700 DEG`. At the default threshold `SKY TI VW` + `700 DEG` scores exactly
#: **0.500** against FMLV's `Sky TI` + `700 MEG` — the three shared tokens `sky`, `ti`
#: and `700` out of six — and so is accepted as a revision of the vehicle it replaces.
#: Left alone the run offers a reviewer a single "change" that rewrites a Fiat coachbuilt
#: into a VW one, and hides the fact that the Fiat 700 MEG has been discontinued: a
#: claimed baseline row cannot also be reported as disappeared. This is Etrusco's failure
#: repeating, and `docs/adapters/README.md` calls a base-vehicle change the surest tell.
#:
#: 0.55 is safe here because KNAUS's own matches are separable, which Etrusco's were not.
#: The lowest *legitimate* score in the 1 September 2026 run is **0.600** — the five
#: `Boxlife` -> `BOXLIFE PLATINUM SELECTION` renames — and the only 0.500 in the whole run
#: is the bad pair above. Nothing sits between the two.
#:
#: Confirmed by the requester 1 September 2026. Re-check this if KNAUS ever renames a
#: range in a way that drops a legitimate match below 0.55; the symptom would be a
#: product proposed as new *and* its baseline row reported as disappeared, together.
MATCH_THRESHOLD = 0.55

#: Labels in the layout page's `<dl>`, and in the price list's spec table. Kept as
#: constants because both parsers key off the same strings and a silent rename on one
#: side only is exactly the failure `docs/adapters/README.md` warns about.
_MRO = "Mass in running order"
_MTPLM = "Technically maximum authorised laden mass (kg)"
_BELTS_IN_DRIVING_DIRECTION = "Three-point belts in driving direction"

#: A price-list URL. Opaque token, one document per range, linked from every layout page
#: of that range. Anchored on the host and path so the German `de-de` variant — which is
#: only ever linked from `de-de` pages this adapter never fetches — cannot be picked up
#: even if the site starts cross-linking.
_PRICE_LIST_URL = re.compile(
    r'href="(https://konfigurator\.knaustabbert\.de/rest/1/downloadPriceList/[A-Za-z0-9_-]+)"'
)

#: One layout's card on a Layouts index: the range in the `<h3>`, the model and model year
#: in the `c-tag` `<span>` inside it, then — before the next `<h3>` — the "from ..." price
#: and the "Technical data" link to the layout's own page.
_CARD = re.compile(
    r"<h3[^>]*>\s*(?P<range>.*?)\s*<span[^>]*c-tag[^>]*>\s*(?P<model>.*?)\s*</span>\s*</h3>"
    r"(?P<tail>.*?)(?=<h3|\Z)",
    re.S,
)
_CARD_PRICE = re.compile(r"<p[^>]*>\s*(from[^<]*)</p>")
_CARD_TECH_LINK = re.compile(
    r'href="(https://www\.knaus\.com/en-gb/[^"]*)"[^>]*>\s*Technical data', re.S
)
_MODEL_AND_YEAR = re.compile(r"^(?P<model>.+?)\s*\((?P<year>\d{4})\)$")

#: One `<dt>`/`<dd>` pair from a layout page's specification list.
_SPEC_ROW = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)

#: `2.690 kg (2.555 kg - 2.835 kg)` — the value with its ±5% production tolerance band.
_MASS_WITH_BAND = re.compile(
    r"^([\d.]+)\s*kg\s*\(\s*([\d.]+)\s*kg\s*-\s*([\d.]+)\s*kg\s*\)"
)

#: How far the printed band may sit from an exact ±5% before the row is treated as
#: misparsed. One kilogram absorbs Knaus's own rounding, which is all that was ever seen:
#: the band matched to within 1kg on all 28 layouts surveyed.
_BAND_TOLERANCE_KG = 1


def _strip_tags(fragment: str) -> str:
    """Readable text from one HTML fragment, entities resolved and whitespace collapsed."""
    return " ".join(html_module.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _thousands(raw: str | None) -> int | None:
    """`'3.500 kg'` -> `3500`; `'75.895 GBP'` -> `75895`; `'699 cm'` -> `699`.

    Knaus use the German convention on both the site and the price lists, so the dot is a
    **thousands separator and never a decimal point**. Reading `3.500` as 3.5 would give a
    three-and-a-half kilogram motorhome, which nothing downstream would flag as impossible
    — `validation.py` has no upper or lower bound on a mass.
    """
    if raw is None:
        return None
    match = re.search(r"\d[\d.]*", raw)
    if match is None:
        return None
    return int(match.group(0).replace(".", ""))


def _centimetres_to_mm(raw: str | None) -> int | None:
    value = _thousands(raw)
    return None if value is None else value * 10


@dataclass(frozen=True)
class LayoutCard:
    """One layout as its Layouts-index card names, prices and links it."""

    category: str
    range_label: str
    model: str
    year: int | None
    price_text: str | None
    url: str

    @property
    def label(self) -> str:
        return f"{self.range_label} {self.model}"

    @property
    def rrp_pounds(self) -> int | None:
        return _thousands(self.price_text) if self.price_text else None


def parse_layout_index(index_html: str, category: str) -> list[LayoutCard]:
    """Every layout card on one Layouts index page, in document order.

    A card missing its "Technical data" link is dropped here rather than carried as a
    half-product: the link is the only route to the specification, so there is nothing to
    collect without it. `collect` narrates the shortfall by comparing the card count.
    """
    cards: list[LayoutCard] = []
    for match in _CARD.finditer(index_html):
        tail = match.group("tail")
        link = _CARD_TECH_LINK.search(tail)
        if link is None:
            continue
        raw_model = _strip_tags(match.group("model"))
        year: int | None = None
        model_and_year = _MODEL_AND_YEAR.match(raw_model)
        if model_and_year is not None:
            raw_model = model_and_year.group("model")
            year = int(model_and_year.group("year"))
        price = _CARD_PRICE.search(tail)
        cards.append(
            LayoutCard(
                category=category,
                range_label=_strip_tags(match.group("range")),
                # `600 MQ ` ships with a trailing space on one BOXLIFE card; `_strip_tags`
                # collapses it, but the model is re-split out of the year group above and
                # so needs its own trim.
                model=" ".join(raw_model.split()),
                year=year,
                price_text=_strip_tags(price.group(1)) if price else None,
                url=link.group(1),
            )
        )
    return cards


def parse_spec_rows(page_html: str) -> list[tuple[str, str]]:
    """Every `<dt>`/`<dd>` pair on a layout page, in document order, as flat text.

    A list rather than a dict: `Mass in running order` legitimately appears twice with two
    different values (module docstring), and a dict would silently keep only one of them —
    whichever way round, on 18 of the 28 layouts, with no warning.
    """
    rows: list[tuple[str, str]] = []
    for label, value in _SPEC_ROW.findall(page_html):
        rows.append((_strip_tags(label), _strip_tags(value)))
    return rows


def _first_value(rows: Iterable[tuple[str, str]], prefix: str) -> str | None:
    for label, value in rows:
        if label.startswith(prefix):
            return value
    return None


def _all_values(rows: Iterable[tuple[str, str]], prefix: str) -> list[str]:
    return [value for label, value in rows if label.startswith(prefix)]


@dataclass(frozen=True)
class KnausProduct:
    """One layout, assembled from its own page plus its range's price list."""

    card: LayoutCard
    base_vehicle_manufacturer: str | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mro_kilograms: int | None = None
    #: Every `Mass in running order` figure the page printed, in document order. Length
    #: two on 18 of 28 layouts; the snippet shows both so a reviewer sees the discard.
    mro_published: tuple[str, ...] = ()
    mro_band: tuple[int, int] | None = None
    mtplm_website: int | None = None
    mtplm_price_list: int | None = None
    berths: int | None = None
    mh_passenger_seats_inc_driver: int | None = None

    @property
    def label(self) -> str:
        return self.card.label

    @property
    def mtplm_kilograms(self) -> int | None:
        """The base vehicle's MTPLM, preferring the price list over the website.

        These agree on 26 of 28 layouts. Where they differ — L!VE WAVE 700 MEG and L!VE I
        700 MEG, both 3650 on the website and 3500 in the price list — the price list is
        right and the website is showing an *optioned* vehicle: the same document prices
        `Load increase from 3.500 kg*** to 3.650 kg***` at £329 and marks it `o`
        (optional) on every layout of both ranges. The base-vehicle rule takes 3500.

        This is the documented exception the README's "website overrules the PDF" rule
        allows for, and it meets that rule's own test — the website figure can be *shown*
        to be the optioned one rather than merely suspected of being stale.
        """
        if self.mtplm_price_list is not None:
            return self.mtplm_price_list
        return self.mtplm_website

    @property
    def mh_payload_kilograms(self) -> int | None:
        """`MTPLM - MRO`. Knaus publish no payload figure that means this — see the docstring."""
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms

    @property
    def body_type(self) -> BodyType | None:
        if self.card.category == "camper-vans":
            if self.mh_height_mm is None:
                return None
            return (
                BodyType.CAMPERVAN_HIGH_TOP
                if self.mh_height_mm > HIGH_TOP_ABOVE_MM
                else BodyType.CAMPERVAN
            )
        if self.card.range_label in _A_CLASS_RANGES:
            return BodyType.A_CLASS
        return BodyType.COACH_BUILT_LOW_PROFILE

    @property
    def body_type_basis(self) -> str:
        if self.card.category == "camper-vans":
            return (
                f"listed under /en-gb/camper-vans/ and {self.mh_height_mm}mm tall, above "
                f"the {HIGH_TOP_ABOVE_MM}mm high-top threshold. No elevating roof is "
                f"mentioned anywhere on the page, so per the standing rule it is treated "
                f"as an option rather than standard equipment"
            )
        if self.card.range_label in _A_CLASS_RANGES:
            return (
                "listed under /en-gb/motorhomes/, and KNAUS's own catalogue heads this "
                "range's section 'Welcome to our fully-integrated motorhomes'"
            )
        return (
            "listed under /en-gb/motorhomes/, and KNAUS's own catalogue heads this "
            "range's section 'Welcome to our semi-integrated motorhomes'"
        )


def parse_layout_page(card: LayoutCard, page_html: str) -> KnausProduct:
    """One layout's specification, from its own page. Price-list fields are added later."""
    rows = parse_spec_rows(page_html)
    masses = _all_values(rows, _MRO)
    mro_value: int | None = None
    band: tuple[int, int] | None = None
    if masses:
        # The FIRST figure, which pairs with the Chassis/Engine/Gearbox rows above it.
        match = _MASS_WITH_BAND.match(masses[0])
        if match is not None:
            mro_value = _thousands(match.group(1))
            low, high = _thousands(match.group(2)), _thousands(match.group(3))
            if low is not None and high is not None:
                band = (low, high)
        else:
            mro_value = _thousands(masses[0])

    return KnausProduct(
        card=card,
        base_vehicle_manufacturer=fmlv_base_vehicle(_first_value(rows, "Chassis")),
        mh_length_mm=_centimetres_to_mm(_first_value(rows, "Total length")),
        mh_width_mm=_centimetres_to_mm(_first_value(rows, "Width (outside)")),
        mh_height_mm=_centimetres_to_mm(_first_value(rows, "Height (outside)")),
        mro_kilograms=mro_value,
        mro_published=tuple(masses),
        mro_band=band,
        mtplm_website=_thousands(_first_value(rows, _MTPLM)),
        # `Beds` is the standard count and `Max. number of beds` the optioned one, so the
        # lower-figure rule picks `Beds` — and here the document labels both ends rather
        # than printing a range, so there is nothing to interpret. The `startswith` prefix
        # must not be `"Beds"` alone or it would also match nothing else, but ordering
        # matters: `_first_value` walks in document order and `Beds` precedes `Max.`.
        berths=_thousands(_first_value(rows, "Beds")),
    )


def _reconciles(product: KnausProduct) -> bool:
    """Whether the printed ±5% tolerance band brackets the mass it was printed with.

    Knaus's self-check, and the same shape as Sunlight's, Etrusco's and Bürstner's. It
    held on all 28 layouts surveyed, to within a kilogram of rounding.

    With one URL per vehicle there is no column to misalign, so this is not defending
    against the classic cross-contamination failure. What it does catch is the realistic
    one here: a thousands separator mishandled, or a `<dd>` read from the wrong row after
    a template change. Either breaks the arithmetic immediately.

    A product with no band is **not** dropped — the band is Knaus's annotation, not a
    guarantee it is always printed, and dropping a whole vehicle over a missing footnote
    would be worse than proposing its mass unchecked. `collect` narrates that case.
    """
    if product.mro_kilograms is None or product.mro_band is None:
        return True
    low, high = product.mro_band
    expected_low = round(product.mro_kilograms * 0.95)
    expected_high = round(product.mro_kilograms * 1.05)
    return (
        abs(low - expected_low) <= _BAND_TOLERANCE_KG
        and abs(high - expected_high) <= _BAND_TOLERANCE_KG
    )


def find_price_list_url(page_html: str) -> str | None:
    """The price list linked from one layout page — its own range's, in English."""
    match = _PRICE_LIST_URL.search(page_html)
    return match.group(1) if match else None


@dataclass(frozen=True)
class PriceListRow:
    """The two fields read out of a price list, for one layout."""

    belts_in_driving_direction: int | None = None
    mtplm_kilograms: int | None = None


@dataclass
class PriceList:
    """A price list's contents, indexed by `(range, model)`.

    Keyed on the pair, not on the model alone: `650 MEG` exists in six different KNAUS
    ranges, and the category-wide lists used as a fallback below cover all seven
    motorhome ranges in one document. Keying on the model would silently overwrite five
    of those six with whichever range the document happened to print last.
    """

    url: str
    rows: dict[tuple[str, str], PriceListRow] = field(default_factory=dict)


#: A price-list page's own model roster: `Technical Data 650 MEG 700 DEG 700 DX`. This is
#: the stated roster the README asks for, and it is what makes the columnar table safe to
#: read — a row is only used when it yields exactly this many values.
_PL_HEADER = re.compile(r"Technical Data((?:\s+\d{3}\s+[A-Z]{1,3})+)\s")
_PL_MODEL = re.compile(r"\d{3} [A-Z]{1,3}")

#: The range a price-list page belongs to: `SKY TI VW (2027) Technical Data`. The year is
#: matched loosely so next season's documents keep working.
_PL_RANGE = re.compile(r"([A-Z][A-Z!@ \-]{2,40}?)\s*\((?:19|20)\d{2}\)")


def _pl_row_values(page_text: str, label_pattern: str, count: int) -> list[str] | None:
    """`count` values following `label_pattern` on one price-list page, or `None`.

    pypdf places almost every run in these documents at `(0, 0)`, so coordinates cannot
    separate the columns and reading order is all there is. That is safe **only** because
    the count is pinned to the page's own stated roster: a row that does not yield exactly
    `count` values is rejected outright rather than sliced to fit, which is the trap
    `docs/adapters/README.md` describes — a short row otherwise swallows the next row's
    label and pads itself back to the expected length, defeating the very check meant to
    catch it.

    Only ever used for rows whose cells are bare integers. The prose rows (`Rim size`,
    `Bed size, rear`) are not read at all: their cells contain spaces and would make the
    count meaningless.

    Note the capture is **greedy and then counted**, not sliced to `count`. Matching
    exactly `count` numbers and stopping would happily take the first three of four and
    silently attribute a fourth layout's value to the third — the padding failure the
    guard exists to prevent.
    """
    match = re.search(label_pattern + r"((?:\s+[\d.]+)+)", page_text)
    if match is None:
        return None
    values = match.group(1).split()
    return values if len(values) == count else None


def parse_price_list(pdf_path: Path, url: str) -> PriceList:
    """`parse_price_list_pages` over a real PDF. The PDF read is all this adds."""
    return parse_price_list_pages(
        (page.text or "" for page in extract_text(pdf_path).pages), url
    )


def parse_price_list_pages(pages: Iterable[str], url: str) -> PriceList:
    """Read `Three-point belts in driving direction` and the base MTPLM, per model.

    Walks the document page by page, tracking whichever range heading and model roster
    were stated most recently, so a category-wide list covering seven ranges works the
    same way a single-range one does.
    """
    price_list = PriceList(url=url)
    models: list[str] = []
    range_label: str | None = None
    for page_text in pages:
        text = " ".join(page_text.split())
        heading = _PL_RANGE.search(text)
        if heading is not None:
            range_label = " ".join(heading.group(1).split())
        header = _PL_HEADER.search(text)
        if header is not None:
            models = _PL_MODEL.findall(header.group(1))
        if not (models and range_label):
            continue
        count = len(models)

        belts = _pl_row_values(text, re.escape(_BELTS_IN_DRIVING_DIRECTION), count)
        mtplm = _pl_row_values(text, re.escape(_MTPLM), count)
        for index, model in enumerate(models):
            key = (range_label, model)
            existing = price_list.rows.get(key, PriceListRow())
            price_list.rows[key] = PriceListRow(
                belts_in_driving_direction=(
                    int(belts[index]) if belts else existing.belts_in_driving_direction
                ),
                mtplm_kilograms=(
                    _thousands(mtplm[index]) if mtplm else existing.mtplm_kilograms
                ),
            )
    return price_list


def _build_extracted_motorhome(product: KnausProduct, price_list_url: str | None) -> ExtractedMotorhome:
    card = product.card
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=card.range_label,
        model=card.model,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        rrp_pounds=card.rrp_pounds,
        mro_kilograms=product.mro_kilograms,
        mtplm_kilograms=product.mtplm_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=product.mh_length_mm,
        mh_width_mm=product.mh_width_mm,
        mh_height_mm=product.mh_height_mm,
        mh_passenger_seats_inc_driver=product.mh_passenger_seats_inc_driver,
        berths=product.berths,
        body_type=product.body_type,
        year=card.year,
    )

    provenance: dict[str, Provenance] = {}

    def record(field_name: str, snippet: str, *, url: str | None = None) -> None:
        provenance[field_name] = Provenance(
            source_url=url or card.url, snippet=f"{product.label} — {snippet}"
        )

    if card.rrp_pounds is not None:
        record(
            "rrp_pounds",
            f"KNAUS's own Layouts index states '{card.price_text}'. The page footnotes "
            f"this as 'the RRP for the corresponding base model, including individual "
            f"options'; the range's price list heads the same figure 'List price in GBP "
            f"including 20% VAT'",
            url=_layout_index_url(card.category),
        )
    if product.mh_length_mm is not None:
        record("mh_length_mm", f"Total length (cm): {product.mh_length_mm // 10} cm")
    if product.mh_width_mm is not None:
        record(
            "mh_width_mm",
            f"Width (outside) (cm): {product.mh_width_mm // 10} cm. KNAUS publish a "
            f"separate 'Width (inside)' figure, which is not this field",
        )
    if product.mh_height_mm is not None:
        record("mh_height_mm", f"Height (outside) (cm): {product.mh_height_mm // 10} cm")
    if product.mro_kilograms is not None:
        published = " / ".join(product.mro_published)
        note = (
            f"KNAUS print this row twice with two different figures and identical labels "
            f"({published}); the first is recorded, being the one that pairs with the "
            f"Chassis and Gearbox rows above it. "
            if len(product.mro_published) > 1
            else ""
        )
        record(
            "mro_kilograms",
            f"Mass in running order: {published}. {note}"
            f"The bracketed range is KNAUS's own ±5% production tolerance",
        )
    if product.mtplm_kilograms is not None:
        if (
            product.mtplm_price_list is not None
            and product.mtplm_website is not None
            and product.mtplm_price_list != product.mtplm_website
        ):
            snippet = (
                f"Technically maximum authorised laden mass: {product.mtplm_price_list} kg, "
                f"from the range's price list. The website states "
                f"{product.mtplm_website} kg, which is the *uprated* figure — the same "
                f"price list prices 'Load increase from 3.500 kg to 3.650 kg' at £329 and "
                f"marks it optional on this layout, so the base vehicle is "
                f"{product.mtplm_price_list} kg"
            )
        else:
            snippet = (
                f"Technically maximum authorised laden mass (kg): "
                f"{product.mtplm_kilograms} kg"
            )
        record("mtplm_kilograms", snippet)
    if product.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"derived: {product.mtplm_kilograms} kg MTPLM − {product.mro_kilograms} kg "
            f"MRO = {product.mh_payload_kilograms} kg. KNAUS's own 'Maximum payload' and "
            f"'Remaining payload' rows are EU 2021/535 homologation figures net of "
            f"passenger and optional-equipment mass — not this field, and negative on "
            f"one layout — so they are deliberately not read",
        )
    if product.berths is not None:
        record(
            "berths",
            f"Beds: {product.berths}. KNAUS publish 'Max. number of beds' separately; the "
            f"lower, standard figure is recorded per the berths rule",
        )
    if product.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            f"'{_BELTS_IN_DRIVING_DIRECTION}': "
            f"{product.mh_passenger_seats_inc_driver}, from the range's price list — the "
            f"belted travel seats fitted as standard. KNAUS's 'Number of persons allowed "
            f"in driving operation' is NOT this field: their own price list defines it as "
            f"the figure 'determined by the manufacturer during the type-approval "
            f"process' and uses it for the 75kg-per-passenger mass calculation",
            url=price_list_url,
        )
    if product.base_vehicle_manufacturer is not None:
        record(
            "base_vehicle_manufacturer",
            f"Chassis: {product.base_vehicle_manufacturer}",
        )
    if product.body_type is not None:
        record("body_type", product.body_type_basis)

    # Both halves of the identity move together — FMLV's range names are a model
    # generation behind the site's on every range, so accepting one half alone would
    # leave a mismatched pair. See `bailey.py` for the failure this prevents.
    record(
        "manufacturer_range",
        f"Range '{card.range_label}', as KNAUS's own Layouts index names it. FMLV's "
        f"current name for this range may differ. Paired with the model below — accept "
        f"or reject both together, since the vehicle's full name is the two joined",
        url=_layout_index_url(card.category),
    )
    record(
        "model",
        f"Model '{card.model}', as KNAUS's own Layouts index names it (tagged "
        f"'{card.year}' for the model year). Paired with the range above: together they "
        f"are '{product.label}'",
        url=_layout_index_url(card.category),
    )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def _layout_index_url(category: str) -> str:
    for name, url in LAYOUT_INDEXES:
        if name == category:
            return url
    return f"{BASE_URL}/en-gb/{category}/layouts"


def baseline_in_scope(motorhome: Motorhome, labels: set[str]) -> bool:
    """Which baseline rows a `--range`-narrowed run should diff against.

    Scoped on `model`, not on `manufacturer_range`, because the range column is the thing
    this adapter proposes to change: FMLV holds `Sky TI` where the site says `SKY TI VW`,
    `Boxlife` where it says `BOXLIFE PLATINUM SELECTION`, and six more. The default scope
    matches the selector against `manufacturer_range`, which would find **no** baseline
    row for any narrowed run and propose every layout as new — Wingamm's failure, where
    scoping mid-rename cost two products their identity.

    Scoping on the model code *alone* would be far too wide in the other direction —
    `650 MEG` exists in six KNAUS ranges, so a `--range "SKY TI VW"` run scoped that way
    pulled in twelve baseline rows for three products and reported eleven of them as
    disappeared. A check that fires on a correct run trains a reviewer to ignore it, which
    is worse than not having one. So the mapping is explicit: `_BASELINE_RANGE_NAMES`
    names the FMLV row(s) each site range corresponds to, pinning the model too in the one
    case where a single FMLV range covers two site ranges.
    """
    if motorhome.manufacturer_range is None:
        return False
    held_range = motorhome.manufacturer_range.strip().casefold()
    held_model = (motorhome.model or "").strip().casefold()
    for label in labels:
        # The site's own name, so this keeps working once the renames are accepted.
        if held_range == label.strip().casefold():
            return True
        for baseline_range, baseline_model in _BASELINE_RANGE_NAMES.get(label, ()):
            if held_range != baseline_range.casefold():
                continue
            if baseline_model is None or held_model == baseline_model.casefold():
                return True
    return False


#: What FMLV calls each site range, as of the 1 September 2026 export — used **only** to
#: scope a `--range`-narrowed run's baseline, never to drive collection. The roster comes
#: from the live Layouts index every run, so a new layout needs no edit here.
#:
#: A `None` model means "every row in that FMLV range". The two pinned models are the case
#: that forces the pair: FMLV's single `Van TI` range holds the 640 MEG that the site now
#: calls `VAN TI VW VANSATION` *and* duplicate 550 MF / 650 MEG rows of what the site calls
#: `VAN TI VANSATION` — the same two vehicles it also holds under `Van Ti Vansation`, at
#: byte-identical prices. Scoping the whole `Van TI` range to either site range alone would
#: be wrong in one direction or the other.
#:
#: This map goes stale as the renames are accepted, which is harmless: `baseline_in_scope`
#: matches the site's own range name first, so an accepted rename is matched by that and
#: the entry here simply stops being reached.
_BASELINE_RANGE_NAMES: dict[str, tuple[tuple[str, str | None], ...]] = {
    "VAN TI VANSATION": (
        ("Van Ti Vansation", None),
        ("Van TI", "550 MF"),
        ("Van TI", "650 MEG"),
    ),
    "VAN TI VW VANSATION": (("Van TI", "640 MEG"),),
    "VAN TI PLUS": (("Van TI Plus", None),),
    "L!VE TI PLATINUM SELECTION": (("L!ve TI", None),),
    "L!VE WAVE PLATINUM SELECTION": (("L!VE WAVE", None),),
    "SKY TI VW": (("Sky TI", None),),
    "L!VE I": (("L!ve I", None),),
    "BOXTIME": (("BOXTIME", None),),
    "BOXLIFE PLATINUM SELECTION": (("Boxlife", None),),
}


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Knaus is plain server-rendered HTML; no JS needed
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every current KNAUS motorhome and campervan layout.

    Two Layouts index fetches for the roster and the prices, then one fetch per layout
    page, then one fetch per range's price list. A layout page or a price list that
    cannot be fetched is narrated and skipped; only a Layouts index that cannot be read
    at all costs its whole category.
    """
    wanted_labels = {label for _category, label in ranges}
    wanted_categories = {category for category, _label in ranges}

    cards: list[LayoutCard] = []
    for category, index_url in LAYOUT_INDEXES:
        if category not in wanted_categories:
            continue
        on_progress(f"[{category}] fetching {index_url} ...")
        index = http.fetch(index_url)
        if index.status_code != 200:
            on_progress(
                f"[{category}] SKIPPED: {index_url} returned {index.status_code}, so no "
                f"{category} layouts were collected at all"
            )
            continue
        index_html = index.file_path.read_text(encoding="utf-8", errors="replace")
        found = parse_layout_index(index_html, category)
        if not found:
            on_progress(
                f"[{category}] SKIPPED: no layout cards parsed from {index_url} — the "
                f"index template may have changed"
            )
            continue
        selected = [card for card in found if card.range_label in wanted_labels]
        on_progress(
            f"[{category}] {len(found)} layout card(s) on the index, "
            f"{len(selected)} in the requested range(s)"
        )
        for card in found:
            if card.range_label not in wanted_labels:
                on_progress(f"[{category}] not requested, skipping: {card.label}")
        cards.extend(selected)

    # Price lists already loaded this run, by URL — a range's own list is linked from
    # every one of its layout pages, so this is what stops it being fetched five times.
    loaded: dict[str, PriceList | None] = {}
    # Whether the category-wide fallback has been pulled in yet, per category.
    fallback_done: set[str] = set()

    def load(url: str, what: str) -> PriceList | None:
        if url in loaded:
            return loaded[url]
        loaded[url] = None
        document = http.fetch(url)
        if document.status_code != 200:
            on_progress(f"[{what}] WARNING: price list {url} returned {document.status_code}")
            return None
        try:
            loaded[url] = parse_price_list(document.file_path, url)
        except Exception as error:  # noqa: BLE001 — one bad PDF must not fail the run
            on_progress(
                f"[{what}] WARNING: price list could not be read "
                f"({type(error).__name__}: {error})"
            )
        return loaded[url]

    def lookup(card: LayoutCard) -> tuple[PriceListRow | None, str | None]:
        key = (card.range_label, card.model)
        for url, price_list in loaded.items():
            if price_list is not None and key in price_list.rows:
                return price_list.rows[key], url
        return None, None

    results: list[ExtractedMotorhome] = []

    for card in cards:
        page = http.fetch(card.url)
        if page.status_code != 200:
            on_progress(
                f"[{card.label}] SKIPPED: {card.url} returned {page.status_code}"
            )
            continue
        page_html = page.file_path.read_text(encoding="utf-8", errors="replace")
        product = parse_layout_page(card, page_html)

        if product.mro_kilograms is None:
            on_progress(
                f"[{card.label}] SKIPPED: no '{_MRO}' row found on {card.url} — the "
                f"specification list may have changed shape"
            )
            continue

        if not _reconciles(product):
            low, high = product.mro_band or (0, 0)
            on_progress(
                f"[{card.label}] SKIPPED: the printed tolerance band "
                f"({low}–{high} kg) is not ±5% of the mass in running order "
                f"({product.mro_kilograms} kg), so a figure was misread from {card.url}"
            )
            continue

        if product.mro_band is None:
            on_progress(
                f"[{card.label}] WARNING: mass in running order carries no ±5% tolerance "
                f"band, so it could not be checked against itself"
            )

        # This range's own price list, linked from this very page.
        if (own_url := find_price_list_url(page_html)) is not None:
            load(own_url, card.range_label)

        row, price_list_url = lookup(card)

        # A brand-new range has no price list of its own yet — VAN TI PLUS, the 28 August
        # 2026 world premiere, links none from any of its pages. The category-wide list on
        # the downloads page does cover it, so fall back to that rather than lose the
        # seat count on precisely the newest vehicles.
        if row is None and card.category not in fallback_done:
            fallback_done.add(card.category)
            on_progress(
                f"[{card.label}] no per-range price list covers this layout; trying the "
                f"category-wide list(s) on {BASE_URL}/en-gb/catalogs-downloads"
            )
            downloads = http.fetch(f"{BASE_URL}/en-gb/catalogs-downloads")
            if downloads.status_code != 200:
                on_progress(
                    f"[{card.category}] WARNING: catalogs-downloads returned "
                    f"{downloads.status_code}; no fallback price list available"
                )
            else:
                downloads_html = downloads.file_path.read_text(
                    encoding="utf-8", errors="replace"
                )
                for url in dict.fromkeys(_PRICE_LIST_URL.findall(downloads_html)):
                    load(url, f"{card.category} category-wide")
            row, price_list_url = lookup(card)

        if row is None:
            on_progress(
                f"[{card.label}] WARNING: found in no price list, so the belted seat "
                f"count is left blank rather than guessed"
            )
        else:
            product = KnausProduct(
                card=product.card,
                base_vehicle_manufacturer=product.base_vehicle_manufacturer,
                mh_length_mm=product.mh_length_mm,
                mh_width_mm=product.mh_width_mm,
                mh_height_mm=product.mh_height_mm,
                mro_kilograms=product.mro_kilograms,
                mro_published=product.mro_published,
                mro_band=product.mro_band,
                mtplm_website=product.mtplm_website,
                mtplm_price_list=row.mtplm_kilograms,
                berths=product.berths,
                mh_passenger_seats_inc_driver=row.belts_in_driving_direction,
            )
            if (
                row.mtplm_kilograms is not None
                and product.mtplm_website is not None
                and row.mtplm_kilograms != product.mtplm_website
            ):
                on_progress(
                    f"[{card.label}] NOTE: website states MTPLM "
                    f"{product.mtplm_website} kg, price list states "
                    f"{row.mtplm_kilograms} kg; recording the price list's figure, which "
                    f"is the base vehicle's — the website's is the paid uprate"
                )
            if row.belts_in_driving_direction is None:
                on_progress(
                    f"[{card.label}] WARNING: its price list carries no "
                    f"'{_BELTS_IN_DRIVING_DIRECTION}' row, so the belted seat count is "
                    f"left blank"
                )

        if card.rrp_pounds is None:
            on_progress(f"[{card.label}] WARNING: no price on the index card, left blank")

        results.append(_build_extracted_motorhome(product, price_list_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
