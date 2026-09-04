"""Weinsberg (weinsberg.com/en-uk) — motorhomes and campervans, WEINSBERG brand only.

See `docs/adapters/weinsberg.md` for the full write-up.

**Scope.** Knaus Tabbert AG owns KNAUS, TABBERT, WEINSBERG, T@B, MORELO and RENT AND
TRAVEL. This adapter covers **WEINSBERG-branded motorhomes and campervans only** —
`knaus.py` is the sibling row. Caravans (CaraOne, CaraCito, CaraTwo) are sold on this very
site and are out of scope, so unlike `knaus.com` the scoping here has to be *done* rather
than assumed: nothing under `/en-uk/caravans/` is ever fetched.

**`MANUFACTURER` is `Knaus Tabbert AG`, not `Knaus Tabbert AG Weinsberg`.** Both strings
are live in FMLV — the 88-row Weinsberg export carries 34 rows under the former (all
current model year, none archived) and 54 under the latter (2022–2025, and dropped by
`cli._is_current_model_year` anyway). Registry id 252, per the requester.

## The source: six per-range UK price lists, and no per-layout page at all

**The UK site publishes no layout page.** `/en-uk/motorhomes/caracore/layouts/650-meg/`
and the German tree's `/grundrisse/650-meg/` both return the 404 page, and the range
page's `CaraCore layouts` carousel renders no model names into the served HTML. So where
Knaus's website beat its PDFs, here the price list is the *only* source of weights, berths
and seats — the requester said as much before the survey started, and it is the single
biggest structural difference between the two brands.

Each range page carries a **Download price list** button pointing at
`konfigurator.knaustabbert.de/rest/1/downloadPriceList/<token>`, the same host Knaus uses.
Those six documents are the source, and the token is **rediscovered from the range page
every run**. It is a zlib-compressed CBOR map
(`{b: "WEINSBERG", c: "UK", l: "EN", m: 2027, k: "R50-CARACORE-MJ27"}`) with a trailing
signature, so a constructed token is rejected by the server — there is no route to a
document the site does not link, and no reason to try.

## The near-miss: the downloads page's "Price list, UK" is priced in euros

`/en-uk/support/catalogues-price-lists/` labels its cards **"Price list, UK"** and links
the `global`, `DE-EN` documents, which quote `List price in EUR including 19% VAT`
throughout — the word `GBP` appears **zero times** in either. Reading the card would have
put euro prices into `rrp_pounds` on all 28 layouts while sterling sat two clicks away.

So `parse_price_list_pages` reads a price **only** from a page stating
`List price in GBP including 20% VAT`, and narrates a page that offers EUR instead. That
one assertion is what stops the near-miss recurring silently, and it is why the same
function can safely be pointed at the European document for X-PEDITION below.

Those European lists are still fetched, for the one product that needs them and as the
brand's second source: they agree with the UK lists on length, width, height, MTPLM and
MRO on **28 of 28** layouts. They also list plain `CaraCompact`, `CaraSuite`, `CaraBus`
and `CaraBus GREY` ranges the UK does not get, which is why a shorter UK roster is by
design rather than evidence of a parse failure.

## X-PEDITION: specs from the European list, price from the index card

One layout (`600 MQ`), a Mercedes Sprinter, on its own site (`weinsberg-xpedition.com`,
which has no `en-uk` locale). It is priced in sterling on the UK campervan index, appears
in **no UK price list**, and its only configurator link points at the `/de` market. FMLV
already holds it (`product_id` 8610), so leaving it out would report a live product as
disappeared.

Its specs therefore come from the European campervan price list — the only document that
carries them — and its price from the index card, in sterling. Its own microsite disagrees
with both on length (600 cm vs 594) and height (290 cm vs 283); the price list and the
index card agree with each other, so the microsite is the odd one out and is not read.

## OUTLAW is not a range

`/en-uk/camper-vans/carabus-carabus-grey-outlaw/` is the **630 MEG layout of the two
EDITION [FIRE] ranges**, in its own words — both already collected. It links no price list
and its key facts read `0 layouts`, `0 kg`, `Total length 0 cm`. It is deliberately absent
from `RANGES`: a zero-product range page is exactly the shape that looks like a parse
failure a year from now.

## The traps

**Row labels wrap, and how they wrap depends on the column count.** With CaraSuite's five
columns `Technically maximum authorised laden mass (kg) 3.500 …` becomes
`Technically maximum authorised laden` / `mass (kg) 3.500 …`, and the MRO cells wrap
mid-value (`2.930 (2.783` / `- 3.076)`). Both are handled by collapsing each page's
whitespace before matching anything — the reason every parser here works on
`" ".join(page_text.split())` and never on lines.

**Short rows exist and must be dropped, not padded.** CaraHome's
`Lap seat belts against driving direction` genuinely prints two values for three models.
Every row is pinned to the page's own stated roster and rejected outright if it yields a
different count, which is `docs/adapters/README.md`'s rule — and coordinates cannot help
here, since pypdf places 79 of 124 runs on that page at `(0, 0)`.

**German thousands separators, everywhere.** `3.500` is 3500 and `88.995,-` is £88,995.
`_thousands` is the only number parser in this module for that reason.

**Centimetres.** Every dimension is cm; FMLV wants mm.

**`Mass in running order` is printed twice, on all 29 products.** Identical on CaraHome and
most of CaraSuite; row two differs by −12 kg (CaraCore), +22 (PEPPER), −3 (both CaraBus
ranges) and −5 (CaraSuite 700 DX). Hint `H140` is only the ±5% tolerance footnote, so it
does not discriminate them, and both figures always sit inside each other's band.
`parse_price_list_pages` takes the **first**, which pairs with the `Chassis` /
`Engine power` / `Gearbox` rows immediately above it, and carries both into the provenance
snippet. Confirmed as the pragmatic choice by the requester, 3 September 2026; unresolved
in the same way it is unresolved for Knaus.

**`Maximum payload` is not payload.** It reconciles with nothing (CaraCore 700 MEG prints
18 kg where `3500 − 2960 = 540`) and it is the one field where the UK and European
documents disagree — CaraHome prints `63 22 170` in sterling and `85 50 200` in euros for
the same three layouts. A figure that changes with the market it is priced in is not a
property of the vehicle, so it is never read; the website's `Payload ex works` is the same
number and is no escape either. `mh_payload_kilograms` is derived as `MTPLM − MRO`.

**And the 404 page returns HTTP 200.** Every fetch of a `/en-uk/` page checks the `<title>`
for `404 - Page not Found`; the status code says nothing.

## Berths and seats: four ceilings and one fitment figure

`Beds` is the standard count and `Max. number of beds` the optioned one — the documents
label both ends rather than printing a range, and they differ on 12 of 29 products, so the
lower-figure rule picks `Beds`. The pop-up roof corroborates it: `Beds 2` on the CaraBus
540 MQ is exactly the vehicle without the £5,516 roof whose bed is `135 x 200`.

`Three-point belts in driving direction` is the belted travel seats fitted as standard, and
the same article number Knaus's survey found corroborates the rule here — in the CaraSuite
list, `552686-01 Two folding seats with 3-point seat belts, facing the direction of travel`
is `–` (not possible) on four layouts and `o` (optional, £2,534) on the fifth, never `s`.

`Number of persons allowed in driving operation` is **not** this field: Knaus's price list
defines it as the figure "determined by the manufacturer during the type-approval process",
which is the row `docs/adapters/burstner.md` established is not `mh_passenger_seats_inc_driver`.
Weinsberg's own documents show it wrong in both directions — 6 on two CaraHome layouts and
2 on X-PEDITION, where `Max. belt-secured seats` is 4.

Two caveats, both weaker than the Knaus case and both narrated to the reviewer:

* **The row reads 2 on all 29 products**, so it has no variance of its own and is
  indistinguishable on the numbers from `Automatic three-point belts, height-adjustable`.
* **CaraHome alone publishes `Lap seat belts against driving direction`**, and it is
  deliberately not counted. **A lap belt is not a safe adult travel seat, so FMLV counts
  three-point belts only** — requester, 3 September 2026, and now a standing rule in
  `docs/adapters/README.md`. So CaraHome's figure is 2, not 4, and the row's short-column
  problem never has to be solved.

Expect this to propose `4 → 2` on every matched product. That is the shape
`docs/adapters/burstner.md` says to distrust, so it rests on the documented definition
rather than on the count.

## Body type

Derived, and validated against all 34 current FMLV rows before adoption — **34 of 34
agree**, no exceptions either way. Weinsberg's own category pages name the range they
contain, so this is the manufacturer's classification rather than a heuristic:

* `/camper-vans/` -> `campervan_high_top`. Every layout is 258, 282 or 312 cm tall, well
  over `HIGH_TOP_ABOVE_MM`.
* CaraCore -> `a_class`, from *"the CaraCore, the fully integrated motorhome from
  WEINSBERG"*.
* CaraHome -> `coach_built_over_cab_bed`, from *"the CaraHome, our bestseller among alcove
  motorhomes"*. First use of this value in any adapter.
* CaraCompact and CaraSuite -> `coach_built_low_profile`, from *"The semi-integrated models
  from WEINSBERG"*.

**The elevating roof is checked, not assumed.** Weinsberg price it in the same document —
`WEINSBERG pop-up roof KOMFORT` is `o` on four layouts and `–` on three, **standard on
none** — so by the base-vehicle rule no campervan is an `…_elevating_roof` variant, and
the recorded height is the closed height (hint `H145`: *"If this option is selected, the
vehicle height increases by approx. 11 cm"*). `pop_up_roof_is_standard` reads those
markings every run rather than trusting the survey: if the roof ever becomes standard on
any layout, the campervans' `body_type` is left **unset with provenance** for a reviewer to
settle rather than silently asserted. That is a deliberate improvement on `knaus.py`, which
can only observe that no roof is mentioned.

## Identity: FMLV puts the edition in the model, and is inconsistent about it

The price lists' range titles are not what FMLV calls these vehicles, and the difference is
not guessable from the site — `fmlv fetch-export` is what answered it:

| Price-list range | FMLV range | FMLV model |
|---|---|---|
| `CaraCore` | `CaraCore` | `650 MF` |
| `CaraHome` | `CaraHome` | `600 DKG` |
| `CaraSuite EDITION [SPICY]` | `CaraSuite` | `650 MF` |
| `CaraCompact EDITION [PEPPER]` | `CaraCompact` | `600 MF Edition PEPPER` |
| `CaraBus EDITION [FIRE]` | `CaraBus` | `540 MQ Edition FIRE` |
| `CaraBus GREY EDITION [FIRE]` | `CaraBus` | `540 MQ GREY Edition FIRE` |
| `X-PEDITION` | `X-Pedition` | `600 MQ` |

The edition name moves from the range to the model and loses its bracket-and-caps styling,
`GREY` sits *before* `Edition` — and **SPICY is not suffixed at all**, where PEPPER and
FIRE are. That inconsistency is FMLV's, and the adapter reproduces it deliberately:
emitting `650 MF Edition SPICY` for tidiness would propose a rename on all five CaraSuite
rows for no gain.

Emitting FMLV's own strings gives **28 matches at exactly 1.000** with no fuzzy match
anywhere in the run, so no `MATCH_THRESHOLD` is declared — there is no bad pair to separate
and nothing in the score distribution to tune.
"""

from __future__ import annotations

import html as html_module
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://weinsberg.com"
MANUFACTURER = "Knaus Tabbert AG"
MANUFACTURER_DISPLAY_NAME = "Weinsberg"

#: The two category index pages. Fetched for the campervan index's price cards (the only
#: place X-PEDITION's sterling price appears) and to narrate the roster.
CATEGORY_INDEXES: tuple[tuple[str, str], ...] = (
    ("motorhomes", f"{BASE_URL}/en-uk/motorhomes/"),
    ("camper-vans", f"{BASE_URL}/en-uk/camper-vans/"),
)

#: Where the European category-wide price lists are listed. Their filenames carry a date
#: (`…__05-08_13-30-59_.pdf`) so they are matched on the `/preislisten/<category>/` path
#: segment instead, which also excludes the glossy `/katalog/` documents and the
#: out-of-scope `/wohnwagen/` caravan list.
DOWNLOADS_URL = f"{BASE_URL}/en-uk/support/catalogues-price-lists/"

#: A campervan taller than this is a high top. Same shared threshold as `bailey.py`,
#: `auto_trail.py`, `chausson.py` and `knaus.py`, set by the NCC side from FMLV's own data.
HIGH_TOP_ABOVE_MM = 2300

#: How far the printed band may sit from an exact ±5% before the row is treated as
#: misparsed. One kilogram absorbs Weinsberg's own rounding, which is all that was ever
#: seen: the band matched to within 1 kg on all 28 layouts surveyed.
_BAND_TOLERANCE_KG = 1

#: Row labels, kept as constants because the parser and the provenance snippets both key
#: off the same strings and a silent rename on one side only is exactly the failure
#: `docs/adapters/README.md` warns about.
_MRO = "Mass in running order"
_MTPLM = "Technically maximum authorised laden mass (kg)"
_BELTS_IN_DRIVING_DIRECTION = "Three-point belts in driving direction"
_BEDS = "Beds (Hints: H141)"
_MAX_BEDS = "Max. number of beds (Hints: H142)"
_MAX_BELTED_SEATS = "Max. belt-secured seats"
_GBP_PRICE = "List price in GBP including 20% VAT"
_EUR_PRICE = "List price in EUR"


@dataclass(frozen=True)
class RangeSpec:
    """One range: where its document is, and what FMLV calls its products.

    `model_suffix` is what FMLV appends to the layout code the price list prints, so the
    price list's `540 MQ` in `CaraBus EDITION [FIRE]` is emitted as FMLV's
    `CaraBus` + `540 MQ Edition FIRE`. Empty for the four ranges FMLV names bare.
    """

    category: str
    #: Page slug under `/en-uk/<category>/`, or `None` for X-PEDITION, which has no UK
    #: range page — its data comes from the European list and the index card.
    slug: str | None
    #: The range title as the price list prints it, and the `--range` label.
    pdf_title: str
    fmlv_range: str
    model_suffix: str
    #: `None` for campervans, which derive it from the published height.
    body_type: BodyType | None
    body_type_basis: str

    @property
    def url(self) -> str | None:
        if self.slug is None:
            return None
        return f"{BASE_URL}/en-uk/{self.category}/{self.slug}/"

    def fmlv_model(self, layout_code: str) -> str:
        return f"{layout_code}{self.model_suffix}"


_SEMI_INTEGRATED = (
    "listed under /en-uk/motorhomes/, and WEINSBERG's own category page heads this "
    "range's section 'The semi-integrated models from WEINSBERG'"
)

RANGES: tuple[RangeSpec, ...] = (
    RangeSpec(
        category="motorhomes",
        slug="caracore",
        pdf_title="CaraCore",
        fmlv_range="CaraCore",
        model_suffix="",
        body_type=BodyType.A_CLASS,
        body_type_basis=(
            "listed under /en-uk/motorhomes/, and WEINSBERG's own category page calls it "
            "'the CaraCore, the fully integrated motorhome from WEINSBERG'"
        ),
    ),
    RangeSpec(
        category="motorhomes",
        slug="carahome",
        pdf_title="CaraHome",
        fmlv_range="CaraHome",
        model_suffix="",
        body_type=BodyType.COACH_BUILT_OVER_CAB_BED,
        body_type_basis=(
            "listed under /en-uk/motorhomes/, and WEINSBERG's own category page calls it "
            "'the CaraHome, our bestseller among alcove motorhomes' — the alcove is the "
            "over-cab bed"
        ),
    ),
    RangeSpec(
        category="motorhomes",
        slug="carasuite-edition-spicy",
        pdf_title="CaraSuite EDITION [SPICY]",
        fmlv_range="CaraSuite",
        # Deliberately bare: FMLV holds all five CaraSuite rows without an edition suffix,
        # where it suffixes PEPPER and FIRE. See the module docstring.
        model_suffix="",
        body_type=BodyType.COACH_BUILT_LOW_PROFILE,
        body_type_basis=_SEMI_INTEGRATED,
    ),
    RangeSpec(
        category="motorhomes",
        slug="edition-pepper",
        pdf_title="CaraCompact EDITION [PEPPER]",
        fmlv_range="CaraCompact",
        model_suffix=" Edition PEPPER",
        body_type=BodyType.COACH_BUILT_LOW_PROFILE,
        body_type_basis=_SEMI_INTEGRATED,
    ),
    RangeSpec(
        category="camper-vans",
        slug="edition-fire",
        pdf_title="CaraBus EDITION [FIRE]",
        fmlv_range="CaraBus",
        model_suffix=" Edition FIRE",
        body_type=None,
        body_type_basis="",
    ),
    RangeSpec(
        category="camper-vans",
        slug="grey-edition-fire",
        pdf_title="CaraBus GREY EDITION [FIRE]",
        fmlv_range="CaraBus",
        model_suffix=" GREY Edition FIRE",
        body_type=None,
        body_type_basis="",
    ),
    RangeSpec(
        category="camper-vans",
        slug=None,
        pdf_title="X-PEDITION",
        fmlv_range="X-Pedition",
        model_suffix="",
        body_type=None,
        body_type_basis="",
    ),
)

#: `(slug-or-empty, label)`. `cli.resolve_ranges` keys on the label, so the labels are the
#: price lists' own range titles — unique, and what the manufacturer calls them. They are
#: *not* FMLV's range names, which is why `baseline_in_scope` exists below.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = tuple(
    (spec.slug or "x-pedition", spec.pdf_title) for spec in RANGES
)

#: The price-list link on a range page. Anchored on the host and REST path so nothing else
#: on the page can be mistaken for it.
_PRICE_LIST_URL = re.compile(
    r'href="(https://konfigurator\.knaustabbert\.de/rest/1/downloadPriceList/[A-Za-z0-9_-]+)"'
)

#: A European category-wide price list, on the downloads page. Matched on the
#: `/preislisten/<segment>/` path rather than the dated filename.
def _european_price_list_pattern(segment: str) -> re.Pattern[str]:
    return re.compile(
        r'href="(/fileadmin/[^"]*/preislisten/' + re.escape(segment) + r'/[^"]*\.pdf)"'
    )


#: The range a price-list page belongs to, stated at the top of every page:
#: `CaraBus GREY EDITION [FIRE] (2027)`. Anchored at the start of the page's collapsed
#: text, which is where every one of these documents puts it — the page number is at the
#: end. The year is matched loosely so next season's documents keep working.
_PL_RANGE = re.compile(r"^\s*(.{1,60}?)\s*\((?:19|20)\d{2}\)")

#: A price-list page's own model roster: `Technical Data 650 MF 650 MEG 700 MEG`. This is
#: the stated roster the README asks for, and it is what makes the columnar table safe to
#: read — a row is only used when it yields exactly this many values. The `s = standard`
#: legend that shares the `Technical Data` prefix cannot match, having no digits.
_PL_HEADER = re.compile(r"Technical Data((?:\s+\d{3}\s+[A-Z]{1,4})+)")
_PL_MODEL = re.compile(r"\d{3} [A-Z]{1,4}")

#: `2.930 (2.783 - 3.076)` — a mass with its ±5% production tolerance band. Matched after
#: the page's whitespace is collapsed, which is what rejoins the cells the PDF wraps
#: mid-value.
_MASS_WITH_BAND = re.compile(r"([\d.]+)\s*\(\s*([\d.]+)\s*-\s*([\d.]+)\s*\)")

#: The pop-up roof's `s`/`o`/`–` markings, following its weight and price. Both the ASCII
#: hyphen and the en dash appear in these documents.
#:
#: Anchored on the leading **article number** so only a genuine orderable line matches.
#: The same phrase appears twice more in these documents where it carries no markings at
#: all — as `Bed dimensions pop-up roof (cm)` in the technical data, and in hint H135
#: about awning sizes — and matching either could invent a marking run out of unrelated
#: text.
_POP_UP_ROOF = re.compile(
    r"\d{6}(?:-\d+)?[^,;]{0,40}?pop-up roof.{0,180}?\d[\d.]*,-((?:\s+[so–—-])+)",
    re.I,
)

#: `3 layouts` on a range page — the manufacturer's own count, used as a free completeness
#: check against the roster the price list states.
_LAYOUT_COUNT = re.compile(r"(\d+)\s+layouts")

#: One model card's title and price on a category index. The cards are `<div>`s rather than
#: anchors, so there is no link to follow — but the title and the sterling price are both
#: in the served HTML, and the price is the only published GBP figure for X-PEDITION.
_INDEX_CARD_TITLE = re.compile(r'class="heading delta"[^>]*>(.*?)</span>', re.S)
_INDEX_CARD_PRICE = re.compile(r"([\d.]+),00\s*£")

#: WEINSBERG's 404 page is served with HTTP 200, so the title is the only reliable test.
_NOT_FOUND = "404 - Page not Found"


def _strip_tags(fragment: str) -> str:
    """Readable text from one HTML fragment, entities resolved and whitespace collapsed."""
    return " ".join(html_module.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _thousands(raw: str | None) -> int | None:
    """`'3.500'` -> `3500`; `'88.995,-'` -> `88995`; `'699'` -> `699`.

    Weinsberg use the German convention throughout, so the dot is a **thousands separator
    and never a decimal point**. Reading `3.500` as 3.5 would give a three-and-a-half
    kilogram motorhome, which nothing downstream would flag — `validation.py` has no bound
    on a mass.
    """
    if raw is None:
        return None
    match = re.search(r"\d[\d.]*", raw)
    if match is None:
        return None
    return int(match.group(0).replace(".", ""))


def _centimetres_to_mm(raw: str | int | None) -> int | None:
    if raw is None:
        return None
    value = raw if isinstance(raw, int) else _thousands(raw)
    return None if value is None else value * 10


def is_not_found(page_html: str) -> bool:
    """Whether a fetched page is WEINSBERG's 404, which is served with HTTP 200."""
    return _NOT_FOUND in page_html


def find_price_list_url(page_html: str) -> str | None:
    """The UK price list linked from one range page — its own range's, in sterling."""
    match = _PRICE_LIST_URL.search(page_html)
    return match.group(1) if match else None


def find_european_price_list_url(downloads_html: str, segment: str) -> str | None:
    """The European category-wide price list for one segment, off the downloads page.

    Only used for X-PEDITION, which appears in no UK document. Matched on the
    `/preislisten/<segment>/` path so the dated filename does not have to be hardcoded and
    so neither the glossy `/katalog/` PDFs nor the out-of-scope caravan list can be picked
    up by mistake.
    """
    match = _european_price_list_pattern(segment).search(downloads_html)
    return f"{BASE_URL}{match.group(1)}" if match else None


def parse_layout_count(page_html: str) -> int | None:
    """The `N layouts` a range page claims, for the completeness check."""
    match = _LAYOUT_COUNT.search(_strip_tags(page_html))
    return int(match.group(1)) if match else None


def parse_index_prices(index_html: str) -> dict[str, int]:
    """Each model card's title on a category index, mapped to its sterling `from` price.

    The cards are `<div class="link__button">`, not anchors, so the index cannot be used
    to *discover* ranges — three of the four campervan cards link nothing at all, which is
    why `RANGES` is an explicit list and both `EDITION [FIRE]` slugs had to come from the
    German sitemap. What the index does carry is the price, and for X-PEDITION it is the
    only published GBP figure anywhere.
    """
    prices: dict[str, int] = {}
    matches = list(_INDEX_CARD_TITLE.finditer(index_html))
    for index, match in enumerate(matches):
        title = _strip_tags(match.group(1))
        if not title:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(index_html)
        price = _INDEX_CARD_PRICE.search(_strip_tags(index_html[match.end() : end]))
        if price is not None:
            prices[title] = _thousands(price.group(1)) or 0
    return prices


def _row_values(page_text: str, label: str, count: int) -> list[str] | None:
    """`count` bare numbers following `label` on one collapsed page, or `None`.

    pypdf places 79 of 124 runs on these pages at `(0, 0)`, so coordinates cannot separate
    the columns and reading order is all there is. That is safe **only** because the count
    is pinned to the page's own stated roster: a row that does not yield exactly `count`
    values is rejected outright rather than sliced to fit, which is the trap
    `docs/adapters/README.md` describes — CaraHome's
    `Lap seat belts against driving direction 2 2` really does print two values for three
    models, and slicing would let it swallow the next row's label and pad itself back to
    the expected length, defeating the very check meant to catch it.

    Only ever used for rows whose cells are bare integers. The prose rows (`Rim size`,
    `Bed size, rear`, `Body door`) are not read at all: their cells contain spaces and
    would make the count meaningless.

    The capture is **greedy and then counted**, not sliced to `count`. Matching exactly
    `count` numbers and stopping would happily take the first three of four and silently
    attribute a fourth layout's value to the third.
    """
    match = re.search(re.escape(label) + r"((?:\s+[\d.]+)+)", page_text)
    if match is None:
        return None
    values = match.group(1).split()
    return values if len(values) == count else None


def _price_values(page_text: str, count: int) -> list[str] | None:
    """The GBP price row's `count` values, which carry a German `,-` suffix.

    Separate from `_row_values` because `88.995,-` is not a bare number: a numeric capture
    stops at the comma and would read one value where there are five.
    """
    match = re.search(re.escape(_GBP_PRICE) + r"((?:\s+[\d.]+,-)+)", page_text)
    if match is None:
        return None
    values = match.group(1).split()
    return values if len(values) == count else None


def _chassis_values(page_text: str, count: int) -> list[str] | None:
    """The `Chassis` row's `count` values — `FIAT FIAT FIAT`, or `MERCEDES`.

    Anchored on runs of **two or more** capitals so the following `Engine power` label
    cannot contribute its leading `E` as a spurious extra value, which would push the
    count over and silently reject the row.
    """
    match = re.search(r"Chassis((?:\s+[A-Z]{2,})+)", page_text)
    if match is None:
        return None
    values = match.group(1).split()
    return values if len(values) == count else None


def _mass_rows(page_text: str, count: int) -> list[list[tuple[int, int, int]]]:
    """Every `Mass in running order` row on one collapsed page, as `count` band triples.

    Returned in document order, so `[0]` is the first printed row — the one that pairs
    with the `Chassis` / `Engine power` / `Gearbox` rows immediately above it, and the one
    recorded. All 29 products print this row twice; see the module docstring.

    Triples are accepted only while they run **contiguously**, separated by nothing but
    whitespace. That is what stops the run continuing into an unrelated later figure, and
    it is why the row needs its own parser rather than `_row_values`: each cell is three
    numbers, not one, and the PDF wraps them mid-value.
    """
    rows: list[list[tuple[int, int, int]]] = []
    for chunk in page_text.split(_MRO)[1:]:
        matches = list(_MASS_WITH_BAND.finditer(chunk))
        if not matches:
            continue
        run = [matches[0]]
        for previous, following in zip(matches, matches[1:]):
            if chunk[previous.end() : following.start()].strip():
                break
            run.append(following)
        if len(run) != count:
            continue
        rows.append(
            [
                (
                    _thousands(match.group(1)) or 0,
                    _thousands(match.group(2)) or 0,
                    _thousands(match.group(3)) or 0,
                )
                for match in run
            ]
        )
    return rows


def pop_up_roof_is_standard(pages: Iterable[str]) -> bool | None:
    """Whether Weinsberg fit the pop-up roof as standard on any layout in a document.

    `True` on any `s` marking, `False` when every marking is `o` (optional) or `–` (not
    possible), and `None` when the row could not be read at all.

    Read every run rather than trusted from the survey, because it is the whole basis for
    the campervans' body type. As of 3 September 2026 it is `o` on four layouts of each
    CaraBus range at £5,516 and `–` on three, so **standard on none** — and by the
    base-vehicle rule that makes every campervan a plain `campervan_high_top` rather than
    an elevating-roof variant, with the published height being the closed height (hint
    `H145`: "If this option is selected, the vehicle height increases by approx. 11 cm").

    Deliberately a whole-document answer rather than a per-layout one. The per-layout
    markings sit on the options pages, whose roster is laid out differently from the
    technical-data pages' and cannot be pinned the same way; and the only decision that
    turns on it is whether *any* layout has the roof as standard, at which point the
    campervans' body type is left to a reviewer instead of being asserted.
    """
    seen = False
    for page_text in pages:
        for match in _POP_UP_ROOF.finditer(" ".join(page_text.split())):
            seen = True
            if "s" in match.group(1).split():
                return True
    return False if seen else None


@dataclass(frozen=True)
class PriceListRow:
    """One layout's technical data, as its range's price list prints it."""

    layout_code: str
    rrp_pounds: int | None = None
    base_vehicle_manufacturer: str | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mro_kilograms: int | None = None
    mro_band: tuple[int, int] | None = None
    #: Every `Mass in running order` figure the document printed for this layout, in
    #: document order. Always length two; the snippet shows both so a reviewer sees the
    #: discard.
    mro_published: tuple[int, ...] = ()
    mtplm_kilograms: int | None = None
    berths: int | None = None
    max_berths: int | None = None
    mh_passenger_seats_inc_driver: int | None = None
    max_belted_seats: int | None = None

    @property
    def mh_payload_kilograms(self) -> int | None:
        """`MTPLM - MRO`. Weinsberg publish no payload figure that means this."""
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms


@dataclass
class PriceList:
    """A price list's contents, indexed by `(range title, layout code)`.

    Keyed on the pair, not on the layout code alone: `600 MQ` exists in five Weinsberg
    ranges, and the European document used for X-PEDITION covers five in one file. Keying
    on the code would let one range's figures stand for all of them — the mistake
    `knaus.py` records having had to guard against for the same reason.
    """

    url: str
    rows: dict[tuple[str, str], PriceListRow] = field(default_factory=dict)
    #: Range titles whose price row was found in euros rather than sterling. Narrated by
    #: `collect`, and the guard against the downloads page's mislabelled "Price list, UK".
    priced_in_euros: set[str] = field(default_factory=set)


def parse_price_list(pdf_path: Path, url: str) -> PriceList:
    """`parse_price_list_pages` over a real PDF. The PDF read is all this adds."""
    return parse_price_list_pages(
        [page.text or "" for page in extract_text(pdf_path).pages], url
    )


def parse_price_list_pages(pages: Iterable[str], url: str) -> PriceList:
    """Read every technical-data row this project needs, per layout.

    Walks the document page by page, tracking whichever range title and model roster were
    stated most recently, so a single-range UK list and the five-range European one work
    the same way. Every page's whitespace is collapsed first, which is what rejoins the
    labels and cells the PDF wraps — with five columns
    `Technically maximum authorised laden mass (kg)` is split across two lines, and the
    MRO cells are split mid-value on every range.

    A page's rows accumulate onto whatever the roster's layouts already have, because the
    campervan ranges split their seven layouts across two technical-data pages and restate
    the roster on each: the masses arrive on one page and the belted seats on the next.
    """
    price_list = PriceList(url=url)
    models: list[str] = []
    range_title: str | None = None

    for page_text in pages:
        text = " ".join(page_text.split())
        heading = _PL_RANGE.match(text)
        if heading is not None:
            range_title = " ".join(heading.group(1).split())
        header = _PL_HEADER.search(text)
        if header is not None:
            models = _PL_MODEL.findall(header.group(1))
        if not (models and range_title):
            continue
        count = len(models)

        if _EUR_PRICE in text and _GBP_PRICE not in text:
            price_list.priced_in_euros.add(range_title)

        prices = _price_values(text, count)
        chassis = _chassis_values(text, count)
        lengths = _row_values(text, "Total length (cm)", count)
        widths = _row_values(text, "Width (outside) (cm)", count)
        heights = _row_values(text, "Height (outside) (cm)", count)
        mtplms = _row_values(text, _MTPLM, count)
        berths = _row_values(text, _BEDS, count)
        max_berths = _row_values(text, _MAX_BEDS, count)
        belts = _row_values(text, _BELTS_IN_DRIVING_DIRECTION, count)
        max_belts = _row_values(text, _MAX_BELTED_SEATS, count)
        masses = _mass_rows(text, count)

        for index, layout_code in enumerate(models):
            key = (range_title, layout_code)
            row = price_list.rows.get(key, PriceListRow(layout_code=layout_code))
            updates: dict[str, object] = {}
            if prices:
                updates["rrp_pounds"] = _thousands(prices[index])
            if chassis:
                updates["base_vehicle_manufacturer"] = fmlv_base_vehicle(chassis[index])
            if lengths:
                updates["mh_length_mm"] = _centimetres_to_mm(lengths[index])
            if widths:
                updates["mh_width_mm"] = _centimetres_to_mm(widths[index])
            if heights:
                updates["mh_height_mm"] = _centimetres_to_mm(heights[index])
            if mtplms:
                updates["mtplm_kilograms"] = _thousands(mtplms[index])
            if berths:
                updates["berths"] = _thousands(berths[index])
            if max_berths:
                updates["max_berths"] = _thousands(max_berths[index])
            if belts:
                updates["mh_passenger_seats_inc_driver"] = _thousands(belts[index])
            if max_belts:
                updates["max_belted_seats"] = _thousands(max_belts[index])
            if masses:
                # The FIRST row, which pairs with the Chassis/Engine/Gearbox rows above it.
                value, low, high = masses[0][index]
                updates["mro_kilograms"] = value
                updates["mro_band"] = (low, high)
                updates["mro_published"] = tuple(row[index][0] for row in masses)
            if updates:
                price_list.rows[key] = replace(row, **updates)  # type: ignore[arg-type]
    return price_list


def reconciles(row: PriceListRow) -> bool:
    """Whether the printed ±5% tolerance band brackets the mass it was printed with.

    Weinsberg's self-check, and the same shape as Knaus's, Sunlight's, Etrusco's and
    Bürstner's. It held on all 28 layouts surveyed, to within a kilogram of rounding, and
    the document says why: the price list's own Important Notes call the mass "a calculated
    nominal value subject to production-related variations of up to ± 5%", "separately
    indicated in the technical data following the calculated value".

    This is doing real work here, unlike on Knaus. These are columnar pages read in
    reading order with no usable coordinates, so a misaligned column is the realistic
    failure rather than a theoretical one — and a swapped column breaks the band arithmetic
    immediately, because each cell carries its own three numbers.

    A row with no band is **not** dropped: the band is Weinsberg's annotation, not a
    guarantee it is always printed, and dropping a whole vehicle over a missing footnote
    would be worse than proposing its mass unchecked. `collect` narrates that case.
    """
    if row.mro_kilograms is None or row.mro_band is None:
        return True
    low, high = row.mro_band
    return (
        abs(low - round(row.mro_kilograms * 0.95)) <= _BAND_TOLERANCE_KG
        and abs(high - round(row.mro_kilograms * 1.05)) <= _BAND_TOLERANCE_KG
    )


def _body_type(spec: RangeSpec, row: PriceListRow, roof_standard: bool | None) -> BodyType | None:
    if spec.body_type is not None:
        return spec.body_type
    if row.mh_height_mm is None or roof_standard is not False:
        # An unknown height, or a document whose pop-up roof markings could not be read
        # or show the roof as standard somewhere: leave it for a reviewer rather than
        # choose between four campervan types on a guess.
        return None
    return (
        BodyType.CAMPERVAN_HIGH_TOP
        if row.mh_height_mm > HIGH_TOP_ABOVE_MM
        else BodyType.CAMPERVAN
    )


def _body_type_basis(spec: RangeSpec, row: PriceListRow) -> str:
    if spec.body_type is not None:
        return spec.body_type_basis
    return (
        f"listed under /en-uk/camper-vans/ and {(row.mh_height_mm or 0) // 10} cm tall, "
        f"above the {HIGH_TOP_ABOVE_MM}mm high-top threshold. WEINSBERG's own price list "
        f"marks the 'WEINSBERG pop-up roof KOMFORT' as optional or not possible and "
        f"standard on no layout, so per the base-vehicle rule this is a plain high top "
        f"and the height recorded is the closed height — hint H145 notes the roof adds "
        f"about 11 cm when selected"
    )


def _build_extracted_motorhome(
    spec: RangeSpec,
    row: PriceListRow,
    *,
    price_list_url: str,
    identity_url: str,
    price_url: str,
    price_note: str,
    roof_standard: bool | None,
) -> ExtractedMotorhome:
    model = spec.fmlv_model(row.layout_code)
    label = f"{spec.pdf_title} {row.layout_code}"
    body_type = _body_type(spec, row, roof_standard)

    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=spec.fmlv_range,
        model=model,
        base_vehicle_manufacturer=row.base_vehicle_manufacturer,
        rrp_pounds=row.rrp_pounds,
        mro_kilograms=row.mro_kilograms,
        mtplm_kilograms=row.mtplm_kilograms,
        mh_payload_kilograms=row.mh_payload_kilograms,
        mh_length_mm=row.mh_length_mm,
        mh_width_mm=row.mh_width_mm,
        mh_height_mm=row.mh_height_mm,
        mh_passenger_seats_inc_driver=row.mh_passenger_seats_inc_driver,
        berths=row.berths,
        body_type=body_type,
    )

    provenance: dict[str, Provenance] = {}

    def record(field_name: str, snippet: str, *, url: str = price_list_url) -> None:
        provenance[field_name] = Provenance(source_url=url, snippet=f"{label} — {snippet}")

    if row.rrp_pounds is not None:
        record("rrp_pounds", price_note, url=price_url)
    if row.mh_length_mm is not None:
        record("mh_length_mm", f"Total length (cm): {row.mh_length_mm // 10} cm")
    if row.mh_width_mm is not None:
        record(
            "mh_width_mm",
            f"Width (outside) (cm): {row.mh_width_mm // 10} cm. WEINSBERG publish a "
            f"separate 'Width (inside)' figure, which is not this field",
        )
    if row.mh_height_mm is not None:
        record("mh_height_mm", f"Height (outside) (cm): {row.mh_height_mm // 10} cm")
    if row.mro_kilograms is not None:
        published = " / ".join(f"{value} kg" for value in row.mro_published)
        note = ""
        if len(set(row.mro_published)) > 1:
            note = (
                f"WEINSBERG print this row twice with two different figures and "
                f"identical labels ({published}); the first is recorded, being the one "
                f"that pairs with the Chassis, Engine power and Gearbox rows above it. "
                f"Both sit inside each other's ±5% band. "
            )
        elif len(row.mro_published) > 1:
            note = (
                f"WEINSBERG print this row twice with the same figure both times; the "
                f"first is recorded. "
            )
        band = f" ({row.mro_band[0]} – {row.mro_band[1]} kg)" if row.mro_band else ""
        record(
            "mro_kilograms",
            f"Mass in running order: {row.mro_kilograms} kg{band}. {note}"
            f"The bracketed range is WEINSBERG's own ±5% production tolerance",
        )
    if row.mtplm_kilograms is not None:
        record("mtplm_kilograms", f"{_MTPLM}: {row.mtplm_kilograms} kg")
    if row.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"derived: {row.mtplm_kilograms} kg MTPLM − {row.mro_kilograms} kg MRO = "
            f"{row.mh_payload_kilograms} kg. WEINSBERG's own 'Maximum payload' row is an "
            f"EU homologation figure that reconciles with nothing — CaraCore 700 MEG "
            f"prints 18 kg — and it is the one field where their UK and European price "
            f"lists disagree, so it is deliberately not read",
        )
    if row.berths is not None:
        max_berths = (
            f" WEINSBERG publish 'Max. number of beds' separately as {row.max_berths}"
            if row.max_berths is not None
            else ""
        )
        record(
            "berths",
            f"Beds: {row.berths}.{max_berths} — the lower, standard figure is recorded "
            f"per the berths rule. On the campervans the difference is the optional "
            f"pop-up roof bed",
        )
    if row.mh_passenger_seats_inc_driver is not None:
        ceilings = (
            f" Their 'Max. belt-secured seats' is {row.max_belted_seats}, a fitment "
            f"ceiling, and the range page's 'up to N belted seats' quotes that figure."
            if row.max_belted_seats is not None
            else ""
        )
        lap_belts = (
            " NOTE WEINSBERG also print 'Lap seat belts against driving direction' on "
            "this range, 2 on some layouts. That row is deliberately NOT counted: a lap "
            "belt is not a safe adult travel seat, so FMLV counts three-point belts only "
            "(requester, 3 September 2026). CaraHome's figure is 2, not 4."
            if spec.fmlv_range == "CaraHome"
            else ""
        )
        record(
            "mh_passenger_seats_inc_driver",
            f"'{_BELTS_IN_DRIVING_DIRECTION}': {row.mh_passenger_seats_inc_driver} — the "
            f"belted travel seats fitted as standard.{ceilings} Their 'Number of persons "
            f"allowed in driving operation' is NOT this field: it is the type-approval "
            f"ceiling used for the 75kg-per-passenger mass calculation. The same document "
            f"prices '552686-01 Two folding seats with 3-point seat belts, facing the "
            f"direction of travel' as optional or not possible and standard on no layout, "
            f"which is what makes this the standard-fitment figure.{lap_belts}",
        )
    if row.base_vehicle_manufacturer is not None:
        record("base_vehicle_manufacturer", f"Chassis: {row.base_vehicle_manufacturer}")

    # Registered with or without a value: where the height or the roof markings could not
    # be established the family is still certain, so a reviewer gets a grouped dropdown to
    # settle it rather than a silently blank column on a new product.
    provenance["body_type"] = Provenance(
        source_url=identity_url,
        snippet=(
            f"{label} — {_body_type_basis(spec, row)}"
            if body_type is not None
            else (
                f"{label} — WEINSBERG list this under /en-uk/camper-vans/, so it is "
                f"certainly a campervan, but which of the four campervan types could not "
                f"be settled this run: either no 'Height (outside)' figure was read, or "
                f"the price list's pop-up roof markings could not be read or show the "
                f"roof as standard on some layout. Open the source link and choose"
            )
        ),
    )

    # Both halves of the identity move together — FMLV splits the edition name across the
    # two columns (`CaraBus` + `540 MQ Edition FIRE`), so accepting one alone would corrupt
    # the vehicle's name. See `bailey.py` for the failure this prevents.
    record(
        "manufacturer_range",
        f"WEINSBERG's price list heads this range '{spec.pdf_title}'; FMLV files it under "
        f"'{spec.fmlv_range}', with the edition name carried in the model instead. Paired "
        f"with the model below — accept or reject both together, since the vehicle's full "
        f"name is the two joined",
        url=identity_url,
    )
    record(
        "model",
        f"Layout '{row.layout_code}', as WEINSBERG's price list roster names it, emitted "
        f"as FMLV's '{model}'. Paired with the range above: together they are "
        f"'{spec.fmlv_range} {model}'",
        url=identity_url,
    )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def baseline_in_scope(motorhome: Motorhome, labels: set[str]) -> bool:
    """Which baseline rows a `--range`-narrowed run should diff against.

    The default scope matches the selector against `manufacturer_range`, which is wrong
    here in both directions: the selectors are the price lists' own range titles
    (`CaraBus GREY EDITION [FIRE]`), while FMLV's range column says `CaraBus` — and *two*
    selectors share that one FMLV range. Left alone, a narrowed run would find no baseline
    row at all and propose every layout as new, which is Wingamm's documented failure.

    So a baseline row is placed by the **longest matching model suffix** in its FMLV
    range. That is what keeps `540 MQ GREY Edition FIRE` with the GREY range rather than
    letting the plain `CaraBus EDITION [FIRE]` selector claim it on the shorter
    ` Edition FIRE` suffix they both end with.

    A row in a configured FMLV range whose model matches **no** suffix falls to that
    range's shortest-suffix selector — FMLV's 2026 plain `CaraBus 540 MQ` and `600 DQ` land
    on `CaraBus EDITION [FIRE]`. Without that fallback a narrowed run would leave them
    unreachable and so never report them as withdrawn, which is the silent half of getting
    the scope wrong: too narrow and a live product is proposed as new, too narrow in the
    other direction and a dead one is never noticed. They are reported by a full sweep
    either way.
    """
    if motorhome.manufacturer_range is None:
        return False
    held_range = motorhome.manufacturer_range.strip().casefold()
    held_model = (motorhome.model or "").strip().casefold()

    in_range = [spec for spec in RANGES if held_range == spec.fmlv_range.casefold()]
    if not in_range:
        return False

    matching = [
        spec
        for spec in in_range
        if not spec.model_suffix or held_model.endswith(spec.model_suffix.casefold())
    ]
    best = (
        max(matching, key=lambda spec: len(spec.model_suffix))
        if matching
        else min(in_range, key=lambda spec: len(spec.model_suffix))
    )
    return best.pdf_title in labels


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Weinsberg's pages are server-rendered; no JS needed
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every current WEINSBERG motorhome and campervan layout.

    One fetch per requested range page for its price-list token and its own `N layouts`
    claim, one per price list, plus the campervan index (for X-PEDITION's sterling price)
    and the downloads page and European campervan list where X-PEDITION is requested.

    A range page or price list that cannot be read is narrated and skipped; a product
    failing the ±5% band check is dropped rather than proposed. Only a wholly unreadable
    document costs its range.
    """
    wanted = [spec for spec in RANGES if spec.pdf_title in {label for _slug, label in ranges}]
    for spec in RANGES:
        if spec not in wanted:
            on_progress(f"[{spec.pdf_title}] not requested, skipping")

    index_prices: dict[str, int] = {}
    if any(spec.slug is None for spec in wanted):
        # Only X-PEDITION needs the index, and only for its price.
        index_url = f"{BASE_URL}/en-uk/camper-vans/"
        on_progress(f"[camper-vans] fetching {index_url} for the index card prices ...")
        index = http.fetch(index_url)
        if index.status_code != 200:
            on_progress(
                f"[camper-vans] WARNING: {index_url} returned {index.status_code}, so no "
                f"index card prices are available"
            )
        else:
            index_prices = parse_index_prices(
                index.file_path.read_text(encoding="utf-8", errors="replace")
            )
            on_progress(f"[camper-vans] {len(index_prices)} index card price(s) read")

    results: list[ExtractedMotorhome] = []

    for spec in wanted:
        price_list_url: str | None = None
        identity_url = spec.url or f"{BASE_URL}/en-uk/camper-vans/"
        claimed_layouts: int | None = None

        range_url = spec.url
        if range_url is not None:
            range_page = http.fetch(range_url)
            if range_page.status_code != 200:
                on_progress(
                    f"[{spec.pdf_title}] SKIPPED: {range_url} returned "
                    f"{range_page.status_code}"
                )
                continue
            page_html = range_page.file_path.read_text(encoding="utf-8", errors="replace")
            if is_not_found(page_html):
                on_progress(
                    f"[{spec.pdf_title}] SKIPPED: {range_url} is WEINSBERG's 404 page "
                    f"(served with HTTP 200) — the range may have been withdrawn or "
                    f"renamed"
                )
                continue
            claimed_layouts = parse_layout_count(page_html)
            price_list_url = find_price_list_url(page_html)
            if price_list_url is None:
                on_progress(
                    f"[{spec.pdf_title}] SKIPPED: no 'Download price list' link on "
                    f"{range_url}. The UK site publishes no per-layout page, so there is "
                    f"no other source for this range's weights, berths or seats"
                )
                continue
        else:
            # X-PEDITION: no UK range page and no UK price list. Its technical data is in
            # the European campervan list, rediscovered off the downloads page.
            on_progress(
                f"[{spec.pdf_title}] no UK range page or price list exists; using the "
                f"European campervan list for the specification and the UK index card "
                f"for the price"
            )
            downloads = http.fetch(DOWNLOADS_URL)
            if downloads.status_code != 200:
                on_progress(
                    f"[{spec.pdf_title}] SKIPPED: {DOWNLOADS_URL} returned "
                    f"{downloads.status_code}"
                )
                continue
            price_list_url = find_european_price_list_url(
                downloads.file_path.read_text(encoding="utf-8", errors="replace"),
                "camper-van",
            )
            if price_list_url is None:
                on_progress(
                    f"[{spec.pdf_title}] SKIPPED: no European campervan price list found "
                    f"on {DOWNLOADS_URL}"
                )
                continue

        document = http.fetch(price_list_url)
        if document.status_code != 200:
            on_progress(
                f"[{spec.pdf_title}] SKIPPED: price list {price_list_url} returned "
                f"{document.status_code}"
            )
            continue
        try:
            page_texts = [pdf_page.text or "" for pdf_page in extract_text(document.file_path).pages]
            price_list = parse_price_list_pages(page_texts, price_list_url)
            roof_standard = pop_up_roof_is_standard(page_texts)
        except Exception as error:  # noqa: BLE001 — one bad PDF must not fail the run
            on_progress(
                f"[{spec.pdf_title}] SKIPPED: price list could not be read "
                f"({type(error).__name__}: {error})"
            )
            continue

        rows = [
            row
            for (title, _code), row in price_list.rows.items()
            if title == spec.pdf_title
        ]
        if not rows:
            titles = sorted({title for title, _code in price_list.rows})
            on_progress(
                f"[{spec.pdf_title}] SKIPPED: no technical-data rows for this range in "
                f"{price_list_url}. Range titles found: {titles or 'none'} — the "
                f"document's own heading may have been reworded"
            )
            continue

        if spec.pdf_title in price_list.priced_in_euros:
            on_progress(
                f"[{spec.pdf_title}] WARNING: this document prices the range in EUR, not "
                f"'{_GBP_PRICE}'. Prices are left blank rather than recorded in the wrong "
                f"currency — WEINSBERG's downloads page labels the euro documents "
                f"'Price list, UK', so check the range page's own link"
            )

        if claimed_layouts is not None and claimed_layouts != len(rows):
            on_progress(
                f"[{spec.pdf_title}] WARNING: the range page claims {claimed_layouts} "
                f"layouts but the price list's roster states {len(rows)}"
            )
        if spec.body_type is None and roof_standard is None:
            on_progress(
                f"[{spec.pdf_title}] WARNING: the pop-up roof's standard/optional "
                f"markings could not be read, so body type is left for a reviewer rather "
                f"than assumed to be a plain high top"
            )
        elif roof_standard:
            on_progress(
                f"[{spec.pdf_title}] WARNING: the pop-up roof is marked STANDARD on at "
                f"least one layout in this document. Body type is left for a reviewer — "
                f"an elevating roof fitted as standard changes what the vehicle is"
            )

        for row in rows:
            label = f"{spec.pdf_title} {row.layout_code}"

            if row.mro_kilograms is None:
                on_progress(
                    f"[{label}] SKIPPED: no '{_MRO}' row read for this layout — the "
                    f"roster and the row's value count may have stopped agreeing"
                )
                continue
            if not reconciles(row):
                low, high = row.mro_band or (0, 0)
                on_progress(
                    f"[{label}] SKIPPED: the printed tolerance band ({low}–{high} kg) is "
                    f"not ±5% of the mass in running order ({row.mro_kilograms} kg), so a "
                    f"column was misread from {price_list_url}"
                )
                continue
            if row.mro_band is None:
                on_progress(
                    f"[{label}] WARNING: mass in running order carries no ±5% tolerance "
                    f"band, so it could not be checked against itself"
                )

            price_url = price_list_url
            price_note = (
                f"'{_GBP_PRICE}': £{row.rrp_pounds:,}. WEINSBERG state this is the "
                f"manufacturer's recommended retail price including VAT and excluding "
                f"registration papers, delivery and transport — not an on-the-road price"
                if row.rrp_pounds is not None
                else ""
            )
            row_for_build = row

            if spec.slug is None:
                # X-PEDITION: the European document's price is in euros, so take the
                # sterling figure off the UK campervan index card instead.
                card_price = index_prices.get(spec.pdf_title)
                if card_price is None:
                    on_progress(
                        f"[{label}] WARNING: no sterling price on the UK campervan index "
                        f"card, and the European price list quotes euros — price left "
                        f"blank rather than converted"
                    )
                    row_for_build = replace(row, rrp_pounds=None)
                else:
                    row_for_build = replace(row, rrp_pounds=card_price)
                    price_url = f"{BASE_URL}/en-uk/camper-vans/"
                    price_note = (
                        f"£{card_price:,}, from WEINSBERG's own UK campervan index card. "
                        f"This range appears in no UK price list — the European one quotes "
                        f"euros — so the index card is the only published sterling figure. "
                        f"The page footnote states prices include 20% VAT and are the "
                        f"manufacturer's recommended retail prices, excluding "
                        f"registration papers, delivery and transport"
                    )
            elif row.rrp_pounds is None:
                on_progress(f"[{label}] WARNING: no price read, left blank")

            if row.mh_passenger_seats_inc_driver is None:
                on_progress(
                    f"[{label}] WARNING: no '{_BELTS_IN_DRIVING_DIRECTION}' row read, so "
                    f"the belted seat count is left blank rather than guessed"
                )
            if row.berths is None:
                on_progress(f"[{label}] WARNING: no '{_BEDS}' row read, berths left blank")

            results.append(
                _build_extracted_motorhome(
                    spec,
                    row_for_build,
                    price_list_url=price_list_url,
                    identity_url=identity_url,
                    price_url=price_url,
                    price_note=price_note,
                    roof_standard=roof_standard,
                )
            )

        on_progress(f"[{spec.pdf_title}] {len(rows)} layout(s) read from {price_list_url}")

    on_progress(f"{len(results)} product(s) collected")
    return results
