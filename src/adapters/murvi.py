"""Murvi (murvi.co.uk) — the seventeenth adapter. A Devon van converter, one price list.

See `docs/adapters/murvi.md` for the full write-up. Ten products, and the whole brand fits
in one 20-page PDF discovered from the "PRICE LIST" page:

     Ford Murvi Pimento
    Dimensions
    Overall length  5.531M (18'1")
    Overall height  2.580M (8' 6")
    Overall width 2.059M (6' 9") Mir folded 2.094M (6'10")
    Payload  600 K gs
    PIMENTO  including 20% VAT £77,290.00
    as above  excluding VAT £64,475.00
    MURVI Pimento motorcaravan based on the NEW Ford Transit
    35 Leader (3,500kg GVW) MWB L2H2 High Roof van in White

Each product gets a **pair of whole pages** — a specification page and an options page —
with its name in a running header. There are no side-by-side columns anywhere in the
document, so none of the column-alignment defences that dominate `morelo.py`, `swift.py`
and `sunlight.py` are needed, and Rimor's unattributable-spans problem cannot arise. This
is Auto-Trail's best case: the risk is entirely *which label is this*.

**The website is not a source.** All seven model pages are marketing prose with a photo
gallery and publish no weight, dimension, price, berth or seat at all — bed sizes in inches
are the only measurement on any of them. Each one ends by pointing at this very document:
"please click on 'Price List' as this includes a fully detailed breakdown of the
specification, technical information and the options available for each Murvi model". So
`docs/adapters/README.md`'s "the website overrules the PDF" has nothing to overrule. The
pages are also stale — six unmodified since 2021, and the Morello page still advertises a
Mercedes Sprinter that neither current price list sells — so they are not even a tiebreak.

**Neither brochure is a source either**, and this is where the requester's warning earned
its place. The page titled "Murvi Brochure" links `JAN_22_MURVI_BROCHURE.pdf` (January
2022) and the page titled "NEW MURVI" links `Murvi-2018-Brochure-1.pdf` (2018) — so the
page calling itself NEW carries the eight-year-old document, and here the *filename* is the
honest half rather than the linking page. Both are glossy: zero occurrences of `Payload`,
`Overall length`, `GVW` or a price across the whole 2022 file. Nothing reads them.

Three Murvi-specific decisions, all from the requester and none of them general rules:

* **The chassis goes in the model name**, so a layout sold on both vans becomes two
  products — `Pimento` + `XL Ford` and `Pimento` + `XL Fiat`. FMLV holds these as two rows
  already (7128/7130 and 7129/7135) but leaves range and model *identical* between them,
  distinguishing them only by `base_vehicle_manufacturer`. Decision of 2 September 2026:
  "we're happy to accept separate models for fiat and ford bases … Again don't make this a
  general rule for going forward." A brand doing this again goes back to the requester.
* **Runs are per chassis.** See `DEFAULT_RANGES` and `baseline_in_scope` — this is not a
  convenience, it is what makes the identity above safe.
* **The Fiat Morello XL's contradictory price resolves to £79,956**, narrated every run.
  See `_price_from_pages`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://www.murvi.co.uk"

#: Byte-for-byte the registry's `fmlv_manufacturer`, and the export's own `manufacturer`.
MANUFACTURER = "Murvi"
MANUFACTURER_DISPLAY_NAME = "Murvi"

#: The page a customer clicks for the price list. **Always rediscover the PDF from here
#: rather than pinning a URL.** Murvi's media library holds eighteen superseded price lists
#: back to 2021, all still live and all named to the same pattern, so a pattern loose enough
#: to match `Murvi-price-list-.*\.pdf` matches all nineteen — Swift's lesson with the archive
#: already in place. Nor is the filename's month a reliable version: "June 2025" was uploaded
#: on 2025-07-06 and three separate "March 2025" lists exist. This page carries exactly one
#: link, which is the one a buyer is shown.
PRICE_LIST_PAGE_URL = f"{BASE_URL}/?page_id=1968"

#: Murvi's `--range` selectors are **base vehicles, not FMLV ranges**, and that is the whole
#: mechanism that makes this brand safe. FMLV files a layout sold on both vans as two rows
#: with identical `manufacturer_range` and `model`, so a combined baseline hits
#: `cli._dedupe_baseline`, which collapses same-range/model rows to the newest year — both
#: twins are 2026, the tie breaks on export order, and the two *Fiat* rows (7130, 7135) are
#: silently discarded before the diff begins. Ten products then meet six baseline rows and
#: four land on the wrong `product_id` or are proposed as duplicates of products the NCC
#: already holds.
#:
#: Scoping a run to one chassis removes the collapse entirely, because within a single
#: chassis no two baseline rows share a range and model. Measured against the real
#: 2026-09-02 export: `--range Fiat` matches 6 of 6 correctly, `--range Ford` 2 of 2 (its
#: other two rows are archived, so "new" is the honest answer), and a combined run 4 of 10
#: with two written onto the wrong row. `collect` warns when both are requested together.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("Ford", "Ford"),
    ("Fiat", "Fiat"),
)

#: Shared with `auto_trail.HIGH_TOP_ABOVE_MM`, set by the NCC side on 16 August 2026. Every
#: Murvi is a factory high-roof panel van at 2540–2846mm, so every one clears this.
HIGH_TOP_ABOVE_MM = 2300

#: The families Murvi sell, longest name first so `Pimento XL` is never read as `Pimento`.
#: Taken from the site navigation and reconciled against the price list, which is the
#: roster check `docs/adapters/README.md` asks for — there is no `sitemap.xml` and no
#: `robots.txt` on this site, so the usual orphan-page sweep is unavailable.
#:
#: `Piccolo` is deliberately absent: it is in the navigation and still has a live page, but
#: it is priced in **neither** the February 2026 nor the October 2025 list, its page has not
#: been modified since June 2021, and its FMLV row carries year 2024 — so
#: `cli._is_current_model_year` already drops it and it cannot be reported as disappeared.
_FAMILIES: tuple[str, ...] = (
    "Morello XL",
    "Morocco XL",
    "Pimento XL",
    "Morello",
    "Morocco",
    "Pimento",
)

#: What the price list is expected to price, for the completeness check. There is no Ford
#: Morocco or Ford Morocco XL — the Morocco page says "currently only based on the Fiat
#: Ducato LWB", which is a fact about the range agreed by two sources rather than a gap.
_EXPECTED: frozenset[tuple[str, str]] = frozenset(
    {
        ("Ford", "Pimento"),
        ("Ford", "Pimento XL"),
        ("Ford", "Morello"),
        ("Ford", "Morello XL"),
        ("Fiat", "Pimento"),
        ("Fiat", "Pimento XL"),
        ("Fiat", "Morello"),
        ("Fiat", "Morello XL"),
        ("Fiat", "Morocco"),
        ("Fiat", "Morocco XL"),
    }
)

#: The Fiat Morello XL prints two different VAT-inclusive prices, and £79,956 is the right
#: one. Its specification page (19) says £79,956 and its options page (20) says £78,596,
#: with a byte-identical ex-VAT £66,699 on both. Four independent grounds for the higher
#: figure: Morocco XL prints £79,956 on *both* its pages and shares that same ex-VAT figure;
#: the two are the same donor van (Fiat Ducato Maxi XLWB 35, L4H2) with the same dimensions
#: and the same 400kg payload, so they are priced identically by design; FMLV already holds
#: both at the same `rrp_pounds`; and three of the four printings say £79,956.
#:
#: **The same discrepancy is in the October 2025 list**, byte for byte, so it is a
#: long-standing typo in Murvi's document rather than a fresh slip, and it will not fix
#: itself. Requester's decision, 2 September 2026: take £79,956 and narrate it every run.
#:
#: Note this is a *data-quality* override, not a parse failure, which is why it warns rather
#: than dropping the product: the weights and dimensions on that page are fine and agree
#: with FMLV exactly. Keyed on the pair of figures rather than on the model, so the day
#: Murvi correct either page the override stops applying and the disagreement is reported
#: instead of silently re-resolved.
_KNOWN_PRICE_TYPO: dict[tuple[str, str], tuple[int, int, str]] = {
    ("Fiat", "Morello XL"): (
        79956,
        78596,
        "the options page's £78,596 contradicts the specification page's £79,956 on an "
        "identical ex-VAT £66,699; Morocco XL prints £79,956 on both its pages and is the "
        "same van at the same ex-VAT price, and the same discrepancy is in the October "
        "2025 list",
    ),
}

# --- Patterns -----------------------------------------------------------------------------
#
# Every one of these is matched against a page's text with newlines flattened to spaces.
# Flattening is safe *here* and would not be on a Sunlight or Morelo page: this document has
# no cells, so no boundary carries meaning — the only thing newlines do is wrap a sentence
# mid-word. What they must tolerate instead is pypdf splitting words internally, which it
# does freely on this file (`600 K gs`, `Mir f olded`, `2.059 M`), hence `\s*` inside almost
# every literal.

#: `MURVI Pimento XL motorcaravan based on the NEW Ford Transit` / `… the "NEW" Fiat Ducato`.
#: This one sentence carries the family *and* the make, which is why identity is read from it
#: rather than from the running header — the headers are corrupted by pypdf on five pages
#: (`FFiat Murvi Morello`, a doubled leading letter) and would need a looser pattern.
_IDENTITY = re.compile(
    r"MURVI\s+(?P<family>[A-Za-z]+(?:\s+XL)?)\s+motorcaravan\s+based\s+on\s+the\s+"
    r"[\"“]?NEW[\"”]?\s+(?P<make>Ford|Fiat)\b",
    re.IGNORECASE,
)

#: `(3,500kg GVW)` — the MTPLM, in the same sentence as the identity. Murvi publish no MRO
#: anywhere, so a product whose GVW cannot be read is a product whose spec block failed.
_GVW = re.compile(r"\(\s*([\d,]+)\s*kg\s*GVW\s*\)", re.IGNORECASE)

#: `MWB L2H2 High Roof van` (Ford) and `MWB High Roof van (L2H2)` (Fiat). The two makes write
#: the code in different positions — the Elddis "same field labelled differently per vehicle
#: type" trap — but the token itself is identical in both, so one pattern serves. It is the
#: donor van's body code, and it is what `_reconciles` checks length and height against.
_BODY_CODE = re.compile(r"\bL(\d)\s*H(\d)\b")

#: `Overall length  5.531M (18'1")`. Anchored on the label and stopping at the first metre
#: figure, which matters most for width: `Overall width 2.059M (6' 9") Mir folded 2.094M`
#: prints the body width first and the **mirrors-folded** width second. FMLV holds 2059 for
#: every Ford, so taking the first is confirmed by the customer's own data — and note this is
#: the first document where the mirrors-folded figure is the *larger* of the two, so "exclude
#: the mirrors" and "take the narrower" happen to agree here for different reasons.
def _dimension_pattern(label: str) -> re.Pattern[str]:
    spaced = r"\s*".join(label)
    return re.compile(rf"{spaced}\s*([\d]+\s*\.\s*[\d]+)\s*M\b", re.IGNORECASE)


_LENGTH = _dimension_pattern("Overall length")
_HEIGHT = _dimension_pattern("Overall height")
_WIDTH = _dimension_pattern("Overall width")

#: `Payload  600 K gs`, `Payload  500Kgs`, and on the Ford Pimento XL
#: `Payload 500 K gs (FWD) 340 Kgs (AWD)` — where the first figure is the front-wheel-drive
#: base vehicle and the second needs the optional all-wheel drive. Taking the first is the
#: base-vehicle rule, and FMLV holds 500 for that product.
_PAYLOAD = re.compile(r"P\s*a\s*y\s*l\s*o\s*a\s*d\s*([\d,]+)\s*K\s*g", re.IGNORECASE)

_PRICE_INC = re.compile(r"including\s*20\s*%\s*VAT\s*£\s*([\d,]+)", re.IGNORECASE)
_PRICE_EXC = re.compile(r"excluding\s*VAT\s*£\s*([\d,]+)", re.IGNORECASE)

#: The link on the price-list page. There is exactly one `.pdf` href on it.
_PDF_HREF = re.compile(r"""href=["']([^"']+\.pdf)["']""", re.IGNORECASE)

#: Murvi's own words for the two fields the document has no row for. Quoted into provenance
#: so a reviewer settles the value from the manufacturer's text rather than from our
#: reasoning about it — `docs/adapters/README.md`.
_BERTHS_EVIDENCE = (
    "converts to a generous size double bed (or, on the Morocco layouts, to two singles "
    "that alternatively form one double) — every Murvi sleeps two"
)
_SEATS_EVIDENCE = (
    "\"the option of up to two rear travel seats, one three-point, inertia reel seat belt "
    "and one lap restraint\" — so the standard fitment is the two cab seats and four is the "
    "ceiling, not the fitment"
)


def _to_int(text: str) -> int:
    return int(text.replace(",", "").replace(" ", ""))


def _metres_to_mm(text: str) -> int:
    return round(float(text.replace(" ", "")) * 1000)


def _flatten(text: str) -> str:
    """One page's text as a single line, for prose matching. See the Patterns note."""
    return " ".join(text.split())


@dataclass(frozen=True)
class MurviSpec:
    """One product, as read off its specification page in the price list."""

    make: str  # "Ford" | "Fiat", as printed
    family: str  # "Pimento" | "Pimento XL" | ...
    page_number: int
    body_code: str  # "L2H2" — the donor van's body code
    mtplm_kilograms: int
    mh_payload_kilograms: int
    mh_length_mm: int
    mh_width_mm: int
    mh_height_mm: int
    price_inc_vat: int
    price_exc_vat: int | None

    @property
    def key(self) -> tuple[str, str]:
        return (self.make, self.family)

    @property
    def label(self) -> str:
        return f"{self.make} Murvi {self.family}"

    @property
    def mro_kilograms(self) -> int:
        """Derived, because Murvi publish no MRO anywhere.

        This is why `payload == MTPLM − MRO` is **not** a self-check on this brand: it would
        be true by construction. `_reconciles` uses the donor van's body code instead.
        """
        return self.mtplm_kilograms - self.mh_payload_kilograms

    @property
    def manufacturer_range(self) -> str:
        """The family without the `XL`, which is what FMLV files these under."""
        return self.family[: -len(" XL")] if self.family.endswith(" XL") else self.family

    @property
    def model(self) -> str:
        """`XL Ford`, or plain `Ford` where the family name is already the range.

        FMLV holds range `Pimento` with model `Pimento` and range `Pimento` with model `XL`,
        so the chassis is appended to whatever actually distinguishes the layout: an `XL`
        keeps its `XL`, and a layout whose name *is* its range has nothing to keep and
        carries the chassis alone. That gives "Murvi Pimento XL Ford" and "Murvi Pimento
        Ford" — the requester's naming of 2 September 2026, which also drops FMLV's existing
        `Pimento` + `Pimento` doubling as a side effect.
        """
        if self.family.endswith(" XL"):
            return f"XL {self.make}"
        return self.make


def find_price_list_url(page_html: str) -> str | None:
    """The current price list's URL, from the page a customer clicks.

    Returns `None` rather than raising so a site change is narrated as a skip. Deliberately
    takes the page's own single link instead of matching a filename pattern — see
    `PRICE_LIST_PAGE_URL` for why a pattern is dangerous on this site.
    """
    for href in _PDF_HREF.findall(page_html):
        cleaned = href.replace("&#038;", "&").strip()
        if "price" in cleaned.lower():
            return cleaned if cleaned.startswith("http") else f"{BASE_URL}/{cleaned.lstrip('/')}"
    return None


def parse_specification_page(text: str, page_number: int) -> MurviSpec | None:
    """One specification page, or `None` if this is not one.

    An options page carries the same running header and the same price but no `Dimensions`
    block, so identity alone cannot tell the two apart — the dimensions are what qualify a
    page as the specification page. A page missing *any* required figure returns `None` and
    is narrated by the caller rather than being emitted half-parsed: with no MRO published,
    every field here is load-bearing.
    """
    flat = _flatten(text)

    identity = _IDENTITY.search(flat)
    if identity is None:
        return None

    family_raw = " ".join(identity.group("family").split())
    family = next(
        (known for known in _FAMILIES if known.lower() == family_raw.lower()),
        None,
    )
    if family is None:
        return None

    length, width, height = (_LENGTH.search(flat), _WIDTH.search(flat), _HEIGHT.search(flat))
    payload, gvw, code = (_PAYLOAD.search(flat), _GVW.search(flat), _BODY_CODE.search(flat))
    price_inc = _PRICE_INC.search(flat)
    if not all((length, width, height, payload, gvw, code, price_inc)):
        return None

    price_exc = _PRICE_EXC.search(flat)
    return MurviSpec(
        make=identity.group("make").title(),
        family=family,
        page_number=page_number,
        body_code=f"L{code.group(1)}H{code.group(2)}",
        mtplm_kilograms=_to_int(gvw.group(1)),
        mh_payload_kilograms=_to_int(payload.group(1)),
        mh_length_mm=_metres_to_mm(length.group(1)),
        mh_width_mm=_metres_to_mm(width.group(1)),
        mh_height_mm=_metres_to_mm(height.group(1)),
        price_inc_vat=_to_int(price_inc.group(1)),
        price_exc_vat=_to_int(price_exc.group(1)) if price_exc else None,
    )


def parse_price_list(pages: list[str]) -> list[MurviSpec]:
    """Every specification page in the price list, in document order.

    Options pages, the covering letter and anything unrecognised fall out silently here;
    `collect` reconciles the result against `_EXPECTED` so a page that *should* have parsed
    and did not is reported rather than quietly reducing the count.
    """
    specs: list[MurviSpec] = []
    for index, text in enumerate(pages, start=1):
        spec = parse_specification_page(text, index)
        if spec is not None:
            specs.append(spec)
    return specs


def other_page_prices(pages: list[str], spec: MurviSpec) -> list[int]:
    """The VAT-inclusive prices printed for `spec` on pages other than its own.

    A product's options page repeats its price under the same running header, which is the
    document's one genuine internal redundancy — and the only thing that catches the Fiat
    Morello XL error. Matched on the running header rather than on page adjacency because
    pypdf corrupts the header's first letter on five pages (`FFiat Murvi Morello`), so the
    make is matched loosely and the family exactly.
    """
    header = re.compile(
        rf"F?\s*{spec.make}\s+Murvi\s+{re.escape(spec.family)}(?!\s*XL)",
        re.IGNORECASE,
    )
    found: list[int] = []
    for index, text in enumerate(pages, start=1):
        if index == spec.page_number:
            continue
        flat = _flatten(text)
        if not header.search(flat):
            continue
        # An options page must not be read as another model's: the Ford Pimento XL's options
        # page carries a stray "Ford Murvi Morello" header (a Murvi layout error), so a page
        # is only trusted for this product if no *other* family's spec block sits on it.
        if _IDENTITY.search(flat) is not None:
            continue
        found.extend(_to_int(match) for match in _PRICE_INC.findall(flat))
    return found


def _price_from_pages(
    spec: MurviSpec,
    pages: list[str],
    on_progress: Callable[[str], None],
) -> int:
    """The VAT-inclusive price, reconciled across the two pages that print it.

    The basis needs no inference on this brand — the document prints `including 20% VAT` and
    `as above excluding VAT` side by side — and FMLV holds the **inclusive** figure, confirmed
    to the pound on all four Ford products. Murvi print no delivery or registration fee
    anywhere, so this is the headline a buyer sees.

    Note the two printed figures do **not** reconcile arithmetically: `exc × 1.2` misses `inc`
    by an inconsistent £80–£84 on all ten products, so neither is derived from the other and
    both are read as printed.
    """
    others = other_page_prices(pages, spec)
    disagreeing = sorted({price for price in others if price != spec.price_inc_vat})
    if not disagreeing:
        return spec.price_inc_vat

    known = _KNOWN_PRICE_TYPO.get(spec.key)
    if known is not None and known[0] == spec.price_inc_vat and [known[1]] == disagreeing:
        on_progress(
            f"NOTE: {spec.label} — taking £{spec.price_inc_vat:,} as published on its "
            f"specification page (p{spec.page_number}). This is a known, long-standing error "
            f"in Murvi's price list: {known[2]}. Decided with the requester on 2 September "
            f"2026; re-check if Murvi correct either page"
        )
        return spec.price_inc_vat

    on_progress(
        f"WARNING: {spec.label} — its specification page (p{spec.page_number}) prices it at "
        f"£{spec.price_inc_vat:,} but another page says "
        f"{', '.join(f'£{price:,}' for price in disagreeing)}. Taking the specification "
        f"page's figure; this is a NEW disagreement and should be checked against the "
        f"document by hand"
    )
    return spec.price_inc_vat


def _reconciles(spec: MurviSpec, siblings: list[MurviSpec]) -> str | None:
    """The self-check: the donor van's body code fixes the length and the height.

    Murvi publish no MRO, so the usual `payload == MTPLM − MRO` is unavailable — MRO is
    *derived* here, which makes that arithmetic true by construction and worthless.
    `docs/adapters/README.md` asks for "some redundancy in the document", and this is it:
    every product names the donor van's body code in prose, and a body code determines the
    van's exterior, so two Murvis on the same `(make, code)` must publish the **same** length
    and height however different their interiors are.

    Three of the six groups in the February 2026 list have more than one member and all three
    agree, so 7 of the 10 products are checked against a sibling:

    | Ford L3H2 | Morello, Pimento XL          | 5981 x 2580 |
    | Fiat L3H2 | Morello, Pimento XL, Morocco | 5998 x 2540 |
    | Fiat L4H2 | Morocco XL, Morello XL       | 6363 x 2565 |

    Returns `None` when the product reconciles, or the reason it does not — which is a page
    mis-attribution, exactly the failure that otherwise produces plausible, internally
    consistent motorhomes carrying each other's dimensions.

    A single-member group cannot be checked this way and passes; the sanity bounds below are
    what stand in for it, and they are deliberately wide enough to only ever catch a parse
    that has gone badly wrong rather than to second-guess the manufacturer.
    """
    if not 4000 <= spec.mh_length_mm <= 8000:
        return f"length {spec.mh_length_mm}mm is outside 4000-8000mm"
    if not 1800 <= spec.mh_width_mm <= 2500:
        return f"width {spec.mh_width_mm}mm is outside 1800-2500mm"
    if not 2000 <= spec.mh_height_mm <= 3200:
        return f"height {spec.mh_height_mm}mm is outside 2000-3200mm"
    if spec.mtplm_kilograms not in (3500, 3700, 4000):
        return f"MTPLM {spec.mtplm_kilograms}kg is not a Murvi GVW (3500, 3700 or 4000)"
    # Together with the GVW check above this also guarantees the derived MRO is a sane
    # weight — the lightest possible is 3500 - 1200 = 2300kg — so there is deliberately no
    # separate "is the MRO positive?" guard, which would be unreachable dead code.
    if not 200 <= spec.mh_payload_kilograms <= 1200:
        return f"payload {spec.mh_payload_kilograms}kg is outside 200-1200kg"

    for sibling in siblings:
        if sibling.key == spec.key:
            continue
        if (sibling.make, sibling.body_code) != (spec.make, spec.body_code):
            continue
        if sibling.mh_length_mm != spec.mh_length_mm or sibling.mh_height_mm != spec.mh_height_mm:
            return (
                f"it shares the {spec.make} {spec.body_code} donor van with "
                f"{sibling.family} but publishes {spec.mh_length_mm}x{spec.mh_height_mm}mm "
                f"against that van's {sibling.mh_length_mm}x{sibling.mh_height_mm}mm — one "
                f"of the two specification pages has been mis-attributed"
            )
    return None


def _build(
    spec: MurviSpec,
    price_inc_vat: int,
    document_url: str,
) -> ExtractedMotorhome:
    """One `ExtractedMotorhome`, with provenance on every field it sets.

    Every field is registered, including the two that come from a constant rather than a
    parsed cell. Bürstner 27 August 2026 is why: a value set on the model but absent from the
    provenance dict is never compared against the baseline *and* lands blank on a genuinely
    new product, and it is silent in both directions.
    """
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=spec.manufacturer_range,
        model=spec.model,
        base_vehicle_manufacturer=fmlv_base_vehicle(spec.make),
        body_type=BodyType.CAMPERVAN_HIGH_TOP,
        berths=2,
        mh_passenger_seats_inc_driver=2,
        rrp_pounds=price_inc_vat,
        mtplm_kilograms=spec.mtplm_kilograms,
        mro_kilograms=spec.mro_kilograms,
        mh_payload_kilograms=spec.mh_payload_kilograms,
        mh_length_mm=spec.mh_length_mm,
        mh_width_mm=spec.mh_width_mm,
        mh_height_mm=spec.mh_height_mm,
    )

    page = f"the February price list, p{spec.page_number}"
    provenance: dict[str, Provenance] = {}

    def record(field: str, snippet: str) -> None:
        provenance[field] = Provenance(
            source_url=document_url, snippet=f"{spec.label} — {snippet}"
        )

    record("manufacturer", f"{page}: Murvi Motorcaravans Limited, Ivybridge, Devon")
    record("manufacturer_display_name", f"{page}: Murvi")

    # Both halves of the identity, together, and each snippet says so. FMLV files a layout
    # sold on both vans as two rows with *identical* range and model, so the chassis is being
    # added to `model` to tell them apart — and a reviewer accepting one half needs to know
    # the other belongs with it (`docs/adapters/README.md`; Bailey is the worked example of
    # accepting a range rename alone and corrupting the name).
    identity_note = (
        f"{page}: \"MURVI {spec.family} motorcaravan based on the NEW {spec.make}\". "
        f"Range and model are one name in two columns — accept both or neither. The chassis "
        f"is in the model because FMLV files the {spec.make} and the other base vehicle "
        f"under identical range and model, distinguished only by base_vehicle_manufacturer; "
        f"this is a Murvi-specific decision of 2 September 2026, not a general rule"
    )
    record("manufacturer_range", identity_note)
    record("model", identity_note)

    record(
        "base_vehicle_manufacturer",
        f"{page}: \"based on the NEW {spec.make} "
        f"{'Transit 35 Leader' if spec.make == 'Ford' else 'Ducato 35'}\", body code "
        f"{spec.body_code}",
    )
    record(
        "body_type",
        f"{page}: a \"High Roof van\" panel-van conversion at {spec.mh_height_mm}mm, above "
        f"the {HIGH_TOP_ABOVE_MM}mm high-top threshold. No elevating roof is offered on any "
        f"Murvi — \"pop-top\" appears nowhere in the price list and the only roof option is a "
        f"taller fixed one (H3), so per the 21 August 2026 rule the standard specification "
        f"has no elevating roof",
    )
    record("berths", f"{page}: {_BERTHS_EVIDENCE}")
    record("mh_passenger_seats_inc_driver", f"{page}: {_SEATS_EVIDENCE}")
    record(
        "rrp_pounds",
        f"{page}: \"{spec.family.upper()} including 20% VAT £{price_inc_vat:,}\""
        + (
            f", against \"as above excluding VAT £{spec.price_exc_vat:,}\""
            if spec.price_exc_vat is not None
            else ""
        )
        + ". FMLV holds the VAT-inclusive figure, confirmed to the pound on all four Ford "
        "products; Murvi print no delivery or registration fee anywhere",
    )
    record(
        "mtplm_kilograms",
        f"{page}: \"({spec.mtplm_kilograms:,}kg GVW)\" in the base-vehicle sentence",
    )
    record("mh_payload_kilograms", f"{page}: \"Payload {spec.mh_payload_kilograms} Kgs\"")
    record(
        "mro_kilograms",
        f"{page}: DERIVED as MTPLM {spec.mtplm_kilograms}kg - payload "
        f"{spec.mh_payload_kilograms}kg. Murvi publish no mass in running order anywhere, "
        f"in this document or on the website",
    )
    record(
        "mh_length_mm",
        f"{page}: \"Overall length {spec.mh_length_mm / 1000:.3f}M\" ({spec.make} "
        f"{spec.body_code} donor van)",
    )
    record(
        "mh_width_mm",
        f"{page}: \"Overall width {spec.mh_width_mm / 1000:.3f}M\", the body width. The "
        f"mirrors-folded figure printed beside it is excluded per the NCC width rule",
    )
    record(
        "mh_height_mm",
        f"{page}: \"Overall height {spec.mh_height_mm / 1000:.3f}M\" ({spec.make} "
        f"{spec.body_code} donor van)",
    )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def baseline_in_scope(motorhome: Motorhome, labels: set[str]) -> bool:
    """Which baseline rows a `--range` run diffs against — `cli.baseline_scope`'s hook.

    Murvi's selectors are **base vehicles**, not FMLV ranges, so the default match on
    `manufacturer_range` would scope a `--range Fiat` run to zero rows and propose all six
    Fiat products as new. Scoping on the chassis instead is also what removes the
    `_dedupe_baseline` collapse that would otherwise discard two live products — see
    `DEFAULT_RANGES`.

    `Piccolo`'s 2024 row is out of scope for every run; `cli._is_current_model_year` drops it
    from a full run anyway.
    """
    return (motorhome.base_vehicle_manufacturer or "") in labels


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Murvi's data is in one plain PDF; see the docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every current Murvi from the price list linked on `PRICE_LIST_PAGE_URL`.

    Two fetches: the price-list page, then the PDF it links. A page or document that cannot
    be read is fatal — there is only one source, so there is nothing to carry on with — while
    an individual product that fails `_reconciles` is narrated and dropped.
    """
    wanted = {label for _key, label in ranges}

    if len(wanted) > 1:
        on_progress(
            "WARNING: this run covers more than one base vehicle, which is NOT SAFE for "
            "Murvi. FMLV files a layout sold on both vans as two rows with identical range "
            "and model, so cli._dedupe_baseline collapses them and two live products (7130 "
            "Fiat Pimento XL, 7135 Fiat Morello XL) are dropped from the baseline before the "
            "diff begins — measured against the 2026-09-02 export, a combined run matches 4 "
            "of 10 correctly and writes 2 onto the WRONG product_id. Run one chassis at a "
            "time instead: `--range Fiat` then `--range Ford`. See docs/adapters/murvi.md"
        )

    on_progress(f"reading the price-list page at {PRICE_LIST_PAGE_URL} ...")
    page = http.fetch(PRICE_LIST_PAGE_URL)
    document_url = find_price_list_url(Path(page.file_path).read_text("utf-8", errors="replace"))
    if document_url is None:
        msg = (
            f"no price list link found on {PRICE_LIST_PAGE_URL} — Murvi publish the whole "
            f"specification only there, and the page's markup must have changed. Do NOT "
            f"widen the search to the media library: eighteen superseded price lists back to "
            f"2021 are still live and would parse cleanly as current"
        )
        raise RuntimeError(msg)

    on_progress(f"fetching the price list at {document_url} ...")
    document = http.fetch(document_url)
    extracted = extract_text(document.file_path)
    if extracted.is_empty():
        msg = f"Murvi's price list at {document_url} yielded no text at all"
        raise RuntimeError(msg)
    pages = [page_text.text for page_text in extracted.pages]

    specs = parse_price_list(pages)
    on_progress(
        f"{document_url.rsplit('/', 1)[-1]}: {len(pages)} pages, "
        f"{len(specs)} specification page(s) parsed"
    )
    if not specs:
        msg = (
            f"no specification pages could be parsed from {document_url} — the document's "
            f"layout has changed"
        )
        raise RuntimeError(msg)

    found = {spec.key for spec in specs}
    for missing in sorted(_EXPECTED - found):
        on_progress(
            f"WARNING: expected a {missing[0]} Murvi {missing[1]} in the price list and "
            f"found none — either Murvi have withdrawn it or its page failed to parse"
        )
    for surprise in sorted(found - _EXPECTED):
        on_progress(
            f"NOTE: {surprise[0]} Murvi {surprise[1]} is priced but was not expected — "
            f"check whether Murvi have added a model, and update _EXPECTED"
        )

    results: list[ExtractedMotorhome] = []
    for spec in specs:
        if spec.make not in wanted:
            continue
        failure = _reconciles(spec, specs)
        if failure is not None:
            on_progress(f"SKIPPED {spec.label} (p{spec.page_number}): {failure}")
            continue
        price = _price_from_pages(spec, pages, on_progress)
        results.append(_build(spec, price, document_url))

    on_progress(
        f"collected {len(results)} product(s) for "
        f"{', '.join(sorted(wanted))} from {document_url.rsplit('/', 1)[-1]}"
    )
    return results
