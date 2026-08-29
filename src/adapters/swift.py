"""Swift (swiftgroup.co.uk) — motorhomes and campervans, from the range pages' own JSON.

See `docs/adapters/swift.md` for the full write-up.

**Rewritten 2026-08-28, because Swift retired the full brochure.** The first version of
this adapter read the "Specification at a glance" table out of the annual brochure PDFs.
For 2027 there is no full brochure: motorhomes, campervans and caravans all got a
two-page *quick guide* instead, and the detailed per-layout data moved onto the website.
The old brochure is still downloadable and still linked from `/brochures/`, which is the
trap here — a URL pattern loosened to match `2027-swift-motorhome-quick-guide.pdf`
would just as happily match `2026_swift_motorhome_brochure.pdf` and propose last
season's range as current. That is why this reads the site, not a PDF, and why nothing
here searches `/brochures/`.

**Where the data is now.** Each range has one page, `/{motorhomes,campervans}/product/
<id>/<slug>/`, carrying a `<script type="application/json" data-product-layouts-data>`
block with one object per layout — plain server-rendered HTML, so still no JavaScript:

    {"id":75041,"title":"Kon-Tiki 774","code":"kon-tiki-774","badge":"New for 2027",
     "priceLabel":"From \\u00A3114,395 OTR","berths":"6 berths",
     "travellingSeats":"5 travelling seats","licenceCategory":"C1","length":"8.22m",
     "width":"2.39m","weightMtplm":"4500kg","weightMro":"3638kg", ...}

This is better than the brochure it replaces in two ways and worse in one:

* **Price, on every layout.** The 2026 survey recorded that Swift published no price
  anywhere; for 2027 all 39 carry a `From £x OTR` figure, which is exactly the basis
  `docs/adapters/README.md` says FMLV records.
* **Range attribution is free**, and that matters more here than anywhere else — see
  the Trekker note below.
* **No height.** Neither the JSON nor the quick guide publishes one, so
  `mh_height_mm` is never emitted. It is left to arrive as a `MissingField`, which
  shows a reviewer the baseline figure alongside "nothing scraped" and leaves the
  stored value alone. Carrying the 2026 brochure's number forward *as a proposal* was
  considered and rejected: FMLV already holds heights that disagree with it on the
  Kon-Tikis (2890 against the brochure's 2880), so proposing it would rewrite good
  data with older data on no 2027 evidence at all.

**TREKKER IS TWO DIFFERENT RANGES**, one motorhome and one campervan — the same
collision as Auto-Trail's Expedition, and the requester flagged it independently. FMLV
already models it: the coachbuilts are range `Trekker 500` (models 540, 584, 594) and
the vans are range `Trekker` (models X, XF). So the motorhome range is renamed via
`RANGE_NAME_CORRECTIONS` and the range a layout belongs to comes from *which index page
led to its page*, never from its name.

It is worse than a name clash. The layout numbers collide too, with **identical length
and MTPLM**: Voyager 505 and Trekker 505 are both 6.19m at 3500kg, and 540, 584 and 594
are shared as well. Only MRO separates them (2837 against 2885). Nothing here may ever
key a layout on its number alone.

**The self-check is cross-document.** The JSON publishes MRO but no payload; the quick
guide publishes payload but no MRO. So `payload == MTPLM - MRO` can be checked across
the two, which is a real check rather than an arithmetic tautology. On 2026-08-28 it was
an exact bijection: 39 payload figures in the guides, 39 products on the site, all
reconciling, none left over.

The guide prints those figures two ways, and both are read (see `parse_guide_payloads`):
a full block per floorplan, and a compact `244 Max Payload / 470kg` line for a variant
that shares its sibling's floorplan and differs only in weight.

**One deliberate softness.** A layout is dropped when the guide contradicts it, but only
*warned* about when the guide has nothing to say. The brochure version dropped hard
because its two tables were joined on `(range, layout)` and a misjoin was the failure
being defended against. There is no join here — one JSON object is one vehicle — so
column misalignment is structurally impossible, and the remaining risk is Swift
mis-stating a figure. Losing a real vehicle over a gap in a marketing leaflet's coverage
would be the worse error.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://www.swiftgroup.co.uk"
MANUFACTURER = "Swift Group Ltd"
MANUFACTURER_DISPLAY_NAME = "Swift"

#: (index page path, category label). Both are ordinary server-rendered pages listing
#: one link per model range. Campervans are included on the same basis as Adria's and
#: as the brochure version's: FMLV treats them as motorhomes and the export's Swift
#: rows cover both.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes", "Motorhomes"),
    ("campervans", "Campervans"),
)

#: Where the site's range name differs from the one FMLV holds, keyed on
#: `(index path, range name as the site writes it)`.
#:
#: Only one entry, and it is the important one. Swift sells a `Trekker` coachbuilt range
#: *and* a `Trekker` campervan range. FMLV distinguishes them as `Trekker 500` and
#: `Trekker`, which the baseline export confirms (range `Trekker 500` holds 540/584/594,
#: range `Trekker` holds S/X/XF/XL). Emitting the site's bare "Trekker" for both would
#: merge two unrelated ranges — the mistake Auto-Trail's `expedition-coachbuilt` vs
#: `expedition-van` keys exist to prevent.
RANGE_NAME_CORRECTIONS: dict[tuple[str, str], str] = {
    ("motorhomes", "Trekker"): "Trekker 500",
}

#: The range pages linked from one index page, e.g.
#: `/motorhomes/product/42117/swift-kon-tiki/`. The numeric id is Swift's CMS node id
#: and the slug is not derivable from the range name (`swift-kon-tiki`, but plain
#: `merlin`), so these are always rediscovered per run rather than constructed.
#:
#: **The category must be interpolated, not alternated.** Swift's nav block is global and
#: repeated on every page, so the motorhomes index links every campervan range too. A
#: pattern accepting either category reads all nine ranges twice — once per index — and
#: applies the motorhome `Trekker` -> `Trekker 500` correction to the campervan Trekker
#: on the first pass. That is the same global-nav trap `chausson.py` hit.
_RANGE_PAGE_HREF_TEMPLATE = r'href="(/{category}/product/\d+/[^"#?]+/)"'

#: The layout data block. Anchored on the `data-product-layouts-data` attribute rather
#: than on a bare `[{"id"`, because the attribute is what actually names this block: it
#: is how Swift's own `/scripts/product-layouts-new.js` finds it. On 2026-08-28 the array
#: appeared exactly once on the page, so a looser pattern would have worked too — but it
#: would be matching a JSON shape rather than an identified element, and Swift adds
#: further JSON blocks to these pages (`optionalExtras`, image manifests) as they go.
_LAYOUTS_JSON = re.compile(
    r'<script[^>]*\bdata-product-layouts-data\b[^>]*>\s*(\[.*?\])\s*</script>',
    re.DOTALL,
)

#: The quick guide linked from an index page, e.g.
#: `/media/0yxdkzhv/2027-swift-motorhome-quick-guide.pdf`. Read only for the payload
#: self-check, never for product data.
#:
#: **Deliberately anchored on `quick-guide`, not on `.pdf`.** The `/media/` directory
#: segment is an opaque key that changes on re-upload, so the filename is all there is
#: to match on, and matching it loosely is how a run would end up parsing the still-live
#: `2026_swift_motorhome_brochure.pdf`.
_QUICK_GUIDE_HREF = re.compile(r'href="(/media/[^"]+-quick-guide\.pdf)"', re.IGNORECASE)

#: The base vehicle, stated once per range page in the "Exterior & Construction" list:
#: `Ford Transit Skeletal chassis cab in Magnetic Grey`, `Fiat chassis cab in New
#: Expedition Grey`, `Fiat Ducato panel van with body coloured grille`.
#:
#: **The make and the body phrase have to be matched together.** The Carrera page's
#: `<title>` is "Award-winning Swift Carrera panel van, refreshed for 2026", so anchoring
#: on `panel van` alone finds a heading with no make in it. Up to two words are allowed
#: between the two so that `Transit`, `Ducato` and `Transit Skeletal` all pass.
#:
#: Confirmed against the real export: reading this on all seven live ranges reproduces
#: FMLV's own split exactly — Ford 17 (Voyager 9, Trekker 500 3, Trekker 4, Monza 1) and
#: Fiat 14 (Escape 4, Kon-Tiki 4, Carrera 6) across all 31 baseline products.
_BASE_VEHICLE = re.compile(
    r"\b(Fiat|Ford|Peugeot|Citro[eë]n|Mercedes-Benz|Mercedes|Renault|IVECO|MAN|VW|Volkswagen)"
    r"\b(?:\s+[A-Z][A-Za-z]+){0,2}\s+(?:chassis cab|panel van)",
    re.IGNORECASE,
)

#: Tags, scripts and styles, so the feature prose can be read as text.
_MARKUP = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.DOTALL | re.IGNORECASE)

#: Overall height in mm for the Merlin, keyed on model. **Not scraped — nothing Swift
#: publishes for 2027 carries a height** (see the module docstring), so these come from a
#: pre-launch specification sheet Swift sent the requester in late July 2026, passed on
#: 2026-08-28. That sheet carries range, base vehicle and height and *no prices or
#: weights*, so it is useful for this one field and nothing else; everything else still
#: comes from the site, which by now has both.
#:
#: Recorded here rather than left blank because these are all **new products with no
#: baseline** — the flagged-no-op route that preserves a height for the other 30 has
#: nothing to preserve for a Merlin, so without this they would stay empty on every run.
#: Same pattern, and the same caveat, as `auto_trail._MANUALLY_SOURCED_MTPLM_KG`: it
#: CANNOT refresh itself, it is narrated on every run, and it must be re-verified at each
#: model-year changeover or as soon as Swift publish heights again.
#:
#: The five 2720s and four 2790s split exactly on the elevating roof, which the Merlin
#: page lists as standard equipment on `212, 244, 264 & 274` only — 70mm of roof
#: hardware. The Carrera corroborates it independently: same Fiat Ducato panel van, same
#: 2260mm width, 2720mm on its five plain models and 2790mm on the 244, which is the one
#: model its own page gives an elevating roof.
#:
#: **112, 122 and 212 are absent deliberately.** They were not on the extract supplied,
#: and the pattern above predicts 2720/2720/2790 for them — but a predicted height is not
#: a published one, so they are left blank and narrated instead of guessed.
_MANUALLY_SOURCED_HEIGHT_MM: dict[tuple[str, str], int] = {
    ("Merlin", "144"): 2720,
    ("Merlin", "164"): 2720,
    ("Merlin", "174"): 2720,
    ("Merlin", "244"): 2790,
    ("Merlin", "264"): 2790,
    ("Merlin", "274"): 2790,
}

#: A coachbuilt range's roof profile, from the range page's own construction list. Every
#: 2027 motorhome range states it: `GRP front low line pod` on the Voyager and Trekker
#: 500, `AL-KO low line chassis conversion` on the Escape and Kon-Tiki.
#:
#: **Matched rather than assumed** so that an A-class or an over-cab range added later
#: comes out unset and narrated instead of silently mislabelled `low profile`.
_LOW_PROFILE = re.compile(r"\blow[ -]line\b", re.IGNORECASE)

#: **`over-cab` on a Swift page does NOT mean an over-cab bed.** Both ranges that use the
#: phrase mean *storage*: "Zip pocket storage on the overcab side lockers" (Trekker 500),
#: "Moulded over-cab storage compartments with Skyview opening sunroof" (Kon-Tiki). Those
#: are lockers in the low-profile pod. Swift's extra berths come from a **drop-down bed
#: over the front lounge**, which is a low-profile feature, not a Luton.
#:
#: Kept only to make the distinction explicit and testable: a keyword search for
#: "over cab" would classify two low-profile ranges as `COACH_BUILT_OVER_CAB_BED`.
_OVER_CAB_BED = re.compile(r"over[ -]?cab\s+(?:double|bed|island)", re.IGNORECASE)

#: The models an elevating roof is standard on, from the campervan range pages:
#: `Elevating roof in Black with Mini-Heki skylight (212, 244, 264 & 274)`,
#: `Elevating roof in body colour (Trekker X)`, `Elevating roof ... (244 only)`.
#:
#: It appears in **no** `optionalExtras` list on any of the 39 products, so where it is
#: named it is standard fitment restricted by model — which per `docs/adapters/README.md`
#: is what decides the elevating half of the campervan 2x2.
_ELEVATING_ROOF = re.compile(r"Elevating roof[^(]{0,80}\(([^)]{1,80})\)", re.IGNORECASE)

#: A model name inside that parenthetical: `212, 244, 264 & 274`, `Trekker X`, `244 only`.
_ELEVATING_ROOF_MODEL = re.compile(r"(?:Trekker\s+)?([A-Z]{1,2}\b|\d{3})")

#: A campervan taller than this is a high top. The same shared threshold as
#: `auto_trail.HIGH_TOP_ABOVE_MM`, set by the NCC side on 16 August 2026: FMLV's tallest
#: standard-height campervan is 2050mm, so 2300mm clears every known standard roof.
#:
#: **Not 2680.** That figure appears in `docs/adapters/README.md` as a description of what
#: an extended high top characteristically measures, not as the cut-off, and the README
#: warns against the confusion in as many words — Elddis's 2610mm Boxer "**is** a high top,
#: so the shared `HIGH_TOP_ABOVE_MM = 2300` needed no adjustment". This adapter used 2680
#: briefly on 2026-08-29 and it was wrong. It changed no Swift result (the Merlin is
#: 2720/2790, above both) but it would have called a standard-roof van a plain campervan.
HIGH_TOP_ABOVE_MM = 2300

#: `From £114,395 OTR`. The site states the basis itself, which is the on-the-road
#: figure FMLV records as its guide price.
_PRICE = re.compile(r"£\s*([\d,]+)")

#: `6 berths` / `5 travelling seats` — a leading integer with a label after it.
_LEADING_INT = re.compile(r"^\s*(\d+)")

#: `8.22m` / `2.39m`. Swift publishes dimensions in metres; FMLV stores mm.
_METRES = re.compile(r"^\s*([\d.]+)\s*m\s*$", re.IGNORECASE)

#: `4500kg`, and `3500kg**` where Swift has attached a footnote mark.
_KILOGRAMS = re.compile(r"^\s*(\d+)\s*kg", re.IGNORECASE)

#: A full per-layout block in the quick guide: length, then payload, then MTPLM. Both
#: payload and MTPLM may carry footnote marks (`663kg*`, `3500kg**`) and may hold *two*
#: figures for the two weight plates a floorplan is sold on (`270kg | 400kg` against
#: `3500kg | 3700kg`), which is how the guide encodes what the site sells as separate
#: 2-berth and 4-berth products. The pairs are positional.
_GUIDE_BLOCK = re.compile(
    r"Length\s*\n\s*([\d.]+)m[^\n]*\n\s*Max Payload\s*\n\s*([^\n]+?)\s*\n\s*MTPLM\s*\n\s*([^\n]+)"
)

#: A variant that shares its sibling's floorplan and is printed as nothing but a payload:
#: `244 Max Payload / 470kg`. Nine of the seventeen campervans are only reachable this
#: way, so ignoring these would leave a third of the range unchecked.
_GUIDE_COMPACT = re.compile(r"(?:^|\n)\s*(?:\d{3}|X\w?)\*?\s+Max Payload\s*\n\s*(\d+)\s*kg")

#: `kg` figures in the guide are whole numbers and the site's MTPLM and MRO are too, so
#: the derived payload should match exactly. A tolerance is kept only because Swift
#: rounds MRO on some automatic-transmission rows, and it stays tight: a genuine
#: mismatch means two different vehicles, and is out by tens of kg at least.
WEIGHT_TOLERANCE_KG = 2


def _metres_to_mm(value: str | None) -> int | None:
    """`'8.22m'` -> `8220`."""
    if not value:
        return None
    match = _METRES.match(value)
    return round(float(match.group(1)) * 1000) if match else None


def _kilograms(value: str | None) -> int | None:
    """`'4500kg'` -> `4500`, tolerating a trailing footnote mark."""
    if not value:
        return None
    match = _KILOGRAMS.match(value)
    return int(match.group(1)) if match else None


def _leading_int(value: str | None) -> int | None:
    """`'6 berths'` -> `6`.

    Swift states one figure here, not a range, so the lower-figure rule in
    `docs/adapters/README.md` has nothing to bite on — but see the note there: the site
    sells the 2-berth and 4-berth builds of one floorplan as *separate products* with
    their own MTPLM and price, so each already carries its own standard berth count.
    """
    if not value:
        return None
    match = _LEADING_INT.match(value)
    return int(match.group(1)) if match else None


def _price(value: str | None) -> int | None:
    """`'From £114,395 OTR'` -> `114395`."""
    if not value:
        return None
    match = _PRICE.search(value)
    return int(match.group(1).replace(",", "")) if match else None


@dataclass(frozen=True)
class SwiftProduct:
    """One layout, as read from its range page's JSON."""

    range_label: str
    model: str
    berths: int | None = None
    mh_passenger_seats_inc_driver: int | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    rrp_pounds: int | None = None
    base_vehicle_manufacturer: str | None = None
    body_type: BodyType | None = None
    #: Which half of `BodyType` this product draws from. Known even when the exact
    #: subtype is not, because it comes from which index page led to the range page.
    is_campervan: bool = False

    @property
    def label(self) -> str:
        return f"{self.range_label} {self.model}"

    @property
    def mh_payload_kilograms(self) -> int | None:
        """`MTPLM - MRO`.

        Swift no longer publishes a payload alongside the weights — the quick guide
        prints one, but per-layout attribution in it is unrecoverable (its blocks lost
        their range headings in reading order). So payload is derived here and the
        guide's figure is used to *check* it, which is `_reconciles`.
        """
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms


@dataclass
class GuidePayloads:
    """Every payload figure one quick guide publishes, indexed two ways.

    `by_floorplan` holds the figures that came with dimensions attached, keyed on
    `(length_mm, mtplm_kg)`; `loose` holds the compact variant lines, which state a
    payload and nothing else. A floorplan can carry several payloads — that is the
    point, since `(length, MTPLM)` is exactly what fails to separate Voyager 505 from
    Trekker 505 — so membership within the group is the test, not equality.
    """

    by_floorplan: dict[tuple[int, int], Counter[int]] = field(default_factory=dict)
    loose: Counter[int] = field(default_factory=Counter)

    def is_empty(self) -> bool:
        return not self.by_floorplan and not self.loose

    def _near(self, payloads: Counter[int], wanted: int) -> int | None:
        """The closest figure in `payloads` within tolerance, or `None`."""
        candidates = [value for value in payloads if abs(value - wanted) <= WEIGHT_TOLERANCE_KG]
        return min(candidates, key=lambda value: abs(value - wanted)) if candidates else None

    def check(self, product: SwiftProduct) -> tuple[bool, str]:
        """Whether the guide corroborates `product`'s derived payload.

        Returns `(ok, explanation)`. `ok` is True both when the guide agrees and when it
        has nothing to say — the caller tells those apart by the explanation, warning on
        a gap and dropping only on a contradiction. See the module docstring for why a
        gap is not fatal here.
        """
        payload = product.mh_payload_kilograms
        if payload is None:
            return True, "no weights to check"

        floorplan = (product.mh_length_mm or 0, product.mtplm_kilograms or 0)
        group = self.by_floorplan.get(floorplan)
        if group:
            found = self._near(group, payload)
            if found is not None:
                group[found] -= 1
                if group[found] <= 0:
                    del group[found]
                return True, f"quick guide prints {found}kg for this floorplan"

        found = self._near(self.loose, payload)
        if found is not None:
            self.loose[found] -= 1
            if self.loose[found] <= 0:
                del self.loose[found]
            return True, f"quick guide prints {found}kg"

        if group:
            return False, (
                f"quick guide prints {sorted(group)}kg for {floorplan[0]}mm/"
                f"{floorplan[1]}kg, none of them {payload}kg"
            )
        return True, "quick guide prints no payload for this floorplan"


def _reconciles(product: SwiftProduct, guide: GuidePayloads) -> tuple[bool, str]:
    """`payload == MTPLM - MRO`, checked across the two documents that split it."""
    return guide.check(product)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def find_range_page_paths(index_html: str, index_path: str) -> list[str]:
    """Every range page for `index_path` linked from that index page, first-seen order.

    `index_path` scopes the match to one category, which is essential rather than tidy —
    see `_RANGE_PAGE_HREF_TEMPLATE`. Paths are de-duplicated because Swift links each
    range from both the page body and the global nav.

    A path that returns an empty body is a dead CMS node and is dropped by `collect`,
    not here — three such `merlin` placeholders were live on 2026-08-28 and only one of
    them carried layouts.
    """
    pattern = re.compile(_RANGE_PAGE_HREF_TEMPLATE.format(category=re.escape(index_path)))
    seen: list[str] = []
    for path in pattern.findall(index_html):
        if path not in seen:
            seen.append(path)
    return seen


def find_quick_guide_url(index_html: str) -> str | None:
    """The absolute URL of the quick guide linked from one index page, if any.

    `None` is an ordinary outcome, not an error: the guide is only the self-check, and
    `collect` proceeds without it rather than losing the whole range.
    """
    match = _QUICK_GUIDE_HREF.search(index_html)
    return f"{BASE_URL}{match.group(1)}" if match else None


def parse_layouts_json(page_html: str) -> list[dict]:
    """The layout objects embedded in one range page.

    An empty list covers both "no block" and "a block holding nothing", which are the
    same thing to a caller and both mean the page is not a real range page.
    """
    match = _LAYOUTS_JSON.search(page_html)
    if match is None:
        return []
    try:
        layouts = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return [layout for layout in layouts if isinstance(layout, dict)]


def range_and_model(title: str, slug: str) -> tuple[str, str] | None:
    """Split a layout's title into `(range, model)` using its page's slug.

    The title carries both (`"Kon-Tiki 774"`), and the range half has to be identified
    rather than guessed at, because the model half is not always a number: the campervan
    Trekker's layouts are `"Trekker X"` and `"Trekker XF"`.

    The slug supplies the boundary. `swift-kon-tiki` -> `kon-tiki`, which matches the
    first 8 characters of `Kon-Tiki 774`, leaving `774`. Taking the range from the
    *title* rather than from the slug keeps Swift's own capitalisation and hyphenation
    (`Kon-Tiki`, not `Kon Tiki`), which is what FMLV holds.

    A common prefix cannot be used for this: `"Trekker X"` and `"Trekker XF"` share
    `"Trekker X"`, which would make the second model `"F"`.
    """
    name = slug.removeprefix("swift-").replace("-", " ").strip()
    if not name:
        return None
    flattened = title.replace("-", " ")
    if flattened[: len(name)].casefold() != name.casefold():
        return None
    range_label = title[: len(name)].strip()
    model = title[len(name) :].strip()
    if not range_label or not model:
        return None
    return range_label, model


def find_elevating_roof_models(page_html: str) -> frozenset[str]:
    """The models a campervan range fits an elevating roof to as standard.

    Swift name them in a parenthetical after the feature, and the feature is listed twice
    on a page (range highlights and Exterior & Construction), so every match is merged.
    An empty set means the range has no elevating roof anywhere — not that the answer is
    unknown, since a range that fits one always says so.
    """
    models: set[str] = set()
    for group in _ELEVATING_ROOF.findall(_MARKUP.sub(" ", page_html)):
        models.update(_ELEVATING_ROOF_MODEL.findall(group))
    return frozenset(models - {"ONLY", "AND"})


def find_body_type(
    page_html: str, *, index_path: str, height_mm: int | None, model: str, elevating: frozenset[str]
) -> BodyType | None:
    """One product's body type, or `None` when the page does not settle it.

    **Motorhomes** need no height. Every 2027 Swift coachbuilt range states `low line` in
    its construction list, and none has an over-cab bed — see `_OVER_CAB_BED` for the trap
    that makes that worth asserting rather than assuming. A range stating neither comes
    back `None` rather than being guessed at, which is what would happen the day Swift add
    an A-class.

    **Campervans** need both halves of the 2x2 in `docs/adapters/README.md`: the roof
    height, which decides `campervan` vs `campervan_high_top`, and whether an elevating
    roof is standard *on this model*. Without a height the first half is unanswerable, so
    the whole thing returns `None` and the baseline value is left alone — that is why the
    Carrera and Trekker campervans get no body type while the Merlin does.
    """
    text = _MARKUP.sub(" ", page_html)

    if index_path == "motorhomes":
        if _OVER_CAB_BED.search(text):
            return BodyType.COACH_BUILT_OVER_CAB_BED
        return BodyType.COACH_BUILT_LOW_PROFILE if _LOW_PROFILE.search(text) else None

    if height_mm is None:
        return None
    high_top = height_mm > HIGH_TOP_ABOVE_MM
    has_roof = model in elevating
    if high_top:
        return (
            BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF
            if has_roof
            else BodyType.CAMPERVAN_HIGH_TOP
        )
    return BodyType.CAMPERVAN_ELEVATING_ROOF if has_roof else BodyType.CAMPERVAN


def find_base_vehicle(page_html: str) -> str | None:
    """The base-vehicle make stated on one range page, as FMLV spells it.

    Swift name the chassis once per range, in the "Exterior & Construction" feature list,
    and every layout in that range is built on it — so this is a range-level fact, not a
    per-layout one. Routed through `base.fmlv_base_vehicle` so the spelling decision lives
    in one place, as it does for the other adapters.
    """
    text = _MARKUP.sub(" ", page_html)
    match = _BASE_VEHICLE.search(text)
    return fmlv_base_vehicle(match.group(1)) if match else None


def parse_range_page(page_html: str, *, slug: str, index_path: str) -> list[SwiftProduct]:
    """Every layout on one range page.

    A layout whose title cannot be split against the slug is skipped rather than
    guessed at — emitting it under the wrong range is the one failure mode this
    manufacturer punishes hardest.
    """
    base_vehicle = find_base_vehicle(page_html)
    elevating = find_elevating_roof_models(page_html)

    layouts = []
    for layout in parse_layouts_json(page_html):
        title = (layout.get("title") or "").strip()
        split = range_and_model(title, slug) if title else None
        if split is None:
            continue
        range_label, model = split
        layouts.append((RANGE_NAME_CORRECTIONS.get((index_path, range_label), range_label), model, layout))

    # A campervan range is one bodyshell, so the high-top half of the 2x2 is a property of
    # the range rather than of a layout. Merlin publishes a height for six of its nine
    # models; the shortest of them decides the roof class for all nine, which is what lets
    # 112, 122 and 212 be classified without inventing a height for them. Their own
    # `mh_height_mm` still stays empty — this settles the body type, not the figure.
    known = [_MANUALLY_SOURCED_HEIGHT_MM.get((r, m)) for r, m, _ in layouts]
    range_height = min((h for h in known if h is not None), default=None)

    products: list[SwiftProduct] = []
    for range_label, model, layout in layouts:
        products.append(
            SwiftProduct(
                range_label=range_label,
                model=model,
                berths=_leading_int(layout.get("berths")),
                mh_passenger_seats_inc_driver=_leading_int(layout.get("travellingSeats")),
                mh_length_mm=_metres_to_mm(layout.get("length")),
                mh_width_mm=_metres_to_mm(layout.get("width")),
                mh_height_mm=_MANUALLY_SOURCED_HEIGHT_MM.get((range_label, model)),
                mtplm_kilograms=_kilograms(layout.get("weightMtplm")),
                mro_kilograms=_kilograms(layout.get("weightMro")),
                rrp_pounds=_price(layout.get("priceLabel")),
                base_vehicle_manufacturer=base_vehicle,
                is_campervan=index_path == "campervans",
                body_type=find_body_type(
                    page_html,
                    index_path=index_path,
                    height_mm=range_height,
                    model=model,
                    elevating=elevating,
                ),
            )
        )
    return products


def parse_guide_payloads(guide_text: str) -> GuidePayloads:
    """Every payload figure a quick guide publishes.

    Both printed forms are read — see `_GUIDE_BLOCK` and `_GUIDE_COMPACT`. Nothing here
    tries to attribute a figure to a named model: the guide's blocks lost their range
    headings in extraction order, and two ranges can share a layout number (Carrera 244
    and Merlin 244 both appear, with different payloads). The figures are collected as a
    multiset instead, which is all `GuidePayloads.check` needs.
    """
    payloads = GuidePayloads()
    for length, payload_column, mtplm_column in _GUIDE_BLOCK.findall(guide_text):
        found = [int(value) for value in re.findall(r"(\d+)\s*kg", payload_column)]
        plates = [int(value) for value in re.findall(r"(\d+)\s*kg", mtplm_column)]
        length_mm = round(float(length) * 1000)
        for payload, mtplm in zip(found, plates):
            payloads.by_floorplan.setdefault((length_mm, mtplm), Counter())[payload] += 1
    for payload in _GUIDE_COMPACT.findall(guide_text):
        payloads.loose[int(payload)] += 1
    return payloads


# --------------------------------------------------------------------------- #
# Orchestration: fetch + parse -> ExtractedMotorhome
# --------------------------------------------------------------------------- #


def _body_type_basis(product: SwiftProduct) -> str:
    """Why this product got the body type it did, for the reviewer.

    `body_type` is a layout field, which `diff/compare.py` marks high-suspicion and sorts
    to the back of a reviewer's queue — so the reasoning has to travel with it.

    **When the subtype is undetermined this still returns a snippet**, and the caller
    still records provenance, so the field reaches the reviewer as a choice rather than
    as silence. On a new product `store.changes.persist_diff` proposes every field an
    adapter puts in `provenance`, whether or not it carries a value, and the review form
    renders a single-select for it (`webapp/choices.py`). Requested 2026-08-29, after the
    first review of the 15 new Swift products found the field blank with nothing to act
    on.
    """
    if product.body_type is None:
        family = "campervan" if product.is_campervan else "coachbuilt motorhome"
        return (
            f"Body type NOT DETERMINED — please choose one. Swift publish no height for "
            f"this {family} and no roof wording anywhere on the range page, so the high "
            f"top / standard roof half of the rule cannot be answered from the site. "
            f"This vehicle is a {family}, so the choice is between the "
            f"{'four campervan' if product.is_campervan else 'three coach built'} types"
        )
    if product.body_type in {
        BodyType.COACH_BUILT_LOW_PROFILE,
        BodyType.COACH_BUILT_OVER_CAB_BED,
    }:
        return (
            f"Body type: {product.body_type.value}, from the range page's construction "
            f"list stating a 'low line' front pod / chassis conversion. Swift's extra "
            f"berths come from a drop-down bed over the front lounge, not a Luton — the "
            f"page's 'over-cab' wording refers to storage lockers"
        )
    roof = "with a standard elevating roof" if "elevating" in product.body_type.value else "with no elevating roof"
    return (
        f"Body type: {product.body_type.value}. Roof class from the range's published "
        f"height (above {HIGH_TOP_ABOVE_MM}mm is a high top per "
        f"docs/adapters/README.md); this model is listed {roof} in the range page's "
        f"standard equipment, and no elevating roof appears in any optional-extras list"
    )


def _build_extracted_motorhome(
    product: SwiftProduct, source_url: str, *, payload_basis: str
) -> ExtractedMotorhome:
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
        rrp_pounds=product.rrp_pounds,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        body_type=product.body_type,
    )

    snippets = {
        "berths": f"Berths: {product.berths}",
        "mh_passenger_seats_inc_driver": (
            f"Travelling seats: {product.mh_passenger_seats_inc_driver}"
        ),
        "mh_length_mm": f"Length: {product.mh_length_mm}mm",
        "mh_width_mm": f"Width: {product.mh_width_mm}mm",
        "mh_height_mm": (
            f"Overall height: {product.mh_height_mm}mm. NOT FROM THE SITE — Swift publish "
            f"no height for 2027. Taken from the pre-launch specification sheet Swift sent "
            f"the requester in late July 2026. This value cannot refresh itself: re-verify "
            f"it at the next model-year changeover, or as soon as Swift publish heights again"
        ),
        "base_vehicle_manufacturer": (
            f"Base vehicle: {product.base_vehicle_manufacturer}, from the range page's own "
            f"Exterior & Construction list, which names the chassis once for the whole range"
        ),
        "body_type": _body_type_basis(product),
        "mtplm_kilograms": f"MTPLM: {product.mtplm_kilograms}kg",
        "mro_kilograms": f"MRO: {product.mro_kilograms}kg",
        "rrp_pounds": (
            f"From £{product.rrp_pounds:,} OTR — the on-the-road price as published on "
            f"the range page, which is the basis FMLV records as its guide price"
            if product.rrp_pounds is not None
            else ""
        ),
        "mh_payload_kilograms": (
            f"Payload: {product.mh_payload_kilograms}kg, derived as MTPLM - MRO "
            f"({product.mtplm_kilograms} - {product.mro_kilograms}); {payload_basis}"
        ),
    }
    values = {
        "berths": product.berths,
        "mh_passenger_seats_inc_driver": product.mh_passenger_seats_inc_driver,
        "mh_length_mm": product.mh_length_mm,
        "mh_width_mm": product.mh_width_mm,
        "mh_height_mm": product.mh_height_mm,
        "mtplm_kilograms": product.mtplm_kilograms,
        "mro_kilograms": product.mro_kilograms,
        "rrp_pounds": product.rrp_pounds,
        "base_vehicle_manufacturer": product.base_vehicle_manufacturer,
        "body_type": product.body_type,
        "mh_payload_kilograms": product.mh_payload_kilograms,
    }
    #: `body_type` is recorded even when unset, so an undetermined subtype reaches the
    #: reviewer as a selectable proposal instead of a silent blank. See
    #: `_body_type_basis` and `webapp/choices.py`.
    always_record = {"body_type"}
    provenance = {
        name: Provenance(source_url=source_url, snippet=f"{product.label} — {snippets[name]}")
        for name, value in values.items()
        if value is not None or name in always_record
    }

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — the range pages are server-rendered; no JS needed
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every Swift motorhome and campervan layout from the range pages.

    `ranges` selects which category index to read, so `--range Campervans` runs one of
    them. As in the brochure version, a Swift "range" at this level is a whole category
    rather than a model range; the model ranges inside it (Voyager, Merlin, …) are
    discovered from the index page.

    A category that can't be read is narrated and skipped rather than raised, so a
    change to one index page doesn't cost the other.
    """
    results: list[ExtractedMotorhome] = []

    for index_path, category in ranges:
        index_url = f"{BASE_URL}/{index_path}/"
        on_progress(f"[{category}] reading {index_url} ...")
        index = http.fetch(index_url)
        if index.status_code != 200:
            on_progress(f"[{category}] SKIPPED: {index_url} returned {index.status_code}")
            continue
        index_html = index.file_path.read_text(encoding="utf-8", errors="replace")

        range_paths = find_range_page_paths(index_html, index_path)
        if not range_paths:
            on_progress(f"[{category}] SKIPPED: no range pages linked from {index_url}")
            continue
        on_progress(f"[{category}] {len(range_paths)} range page(s) linked")

        guide = _load_guide(http, index_html, category=category, on_progress=on_progress)

        for range_path in range_paths:
            page = http.fetch(f"{BASE_URL}{range_path}")
            if page.status_code != 200:
                on_progress(
                    f"[{category}] SKIPPED {range_path}: returned {page.status_code}"
                )
                continue
            slug = range_path.rstrip("/").rsplit("/", 1)[-1]
            products = parse_range_page(
                page.file_path.read_text(encoding="utf-8", errors="replace"),
                slug=slug,
                index_path=index_path,
            )
            if not products:
                # Swift leaves empty placeholder nodes live — three `merlin` paths were
                # linked on 2026-08-28 and only one carried layouts.
                on_progress(f"[{category}] SKIPPED {range_path}: no layout data on the page")
                continue
            base_vehicle = products[0].base_vehicle_manufacturer
            on_progress(
                f"[{category}] {products[0].range_label}: {len(products)} layout(s)"
                + (f", built on {base_vehicle}" if base_vehicle else ", BASE VEHICLE NOT FOUND")
            )
            _narrate_heights(products, category=category, on_progress=on_progress)

            for product in products:
                ok, basis = _reconciles(product, guide)
                if not ok:
                    on_progress(
                        f"[{category}] {product.label} — SKIPPED: payload doesn't "
                        f"reconcile ({product.mtplm_kilograms} - "
                        f"{product.mro_kilograms} = {product.mh_payload_kilograms}kg, "
                        f"but the {basis})"
                    )
                    continue
                if basis.startswith("quick guide prints no"):
                    on_progress(
                        f"[{category}] {product.label} — payload "
                        f"{product.mh_payload_kilograms}kg UNCHECKED: {basis}"
                    )
                results.append(
                    _build_extracted_motorhome(
                        product, f"{BASE_URL}{range_path}", payload_basis=basis
                    )
                )

    on_progress(f"{len(results)} product(s) collected")
    return results


def _narrate_heights(
    products: list[SwiftProduct],
    *,
    category: str,
    on_progress: Callable[[str], None],
) -> None:
    """Say which heights came from the hand-sourced sheet, and which are absent.

    Both halves have to be visible. A carried figure that nobody re-checks silently ages
    into a wrong one, and a blank on a brand-new product is the only case where the
    baseline cannot supply it — see `_MANUALLY_SOURCED_HEIGHT_MM`.
    """
    sourced = [p for p in products if p.mh_height_mm is not None]
    if sourced:
        on_progress(
            f"[{category}] {len(sourced)} height(s) taken from Swift's July 2026 "
            f"specification sheet, NOT from the site — re-verify at changeover: "
            + ", ".join(f"{p.model} {p.mh_height_mm}mm" for p in sourced)
        )
    blank = [p for p in products if p.mh_height_mm is None]
    if blank and sourced:
        on_progress(
            f"[{category}] {products[0].range_label} {', '.join(p.model for p in blank)} "
            f"— NO HEIGHT: not on the sheet supplied and not published on the site, so "
            f"left blank rather than inferred from the range's other layouts"
        )


def _load_guide(
    http: Fetcher,
    index_html: str,
    *,
    category: str,
    on_progress: Callable[[str], None],
) -> GuidePayloads:
    """The quick guide's payload figures, or an empty set if it can't be read.

    Narrated loudly when unavailable: without it every product in the category goes out
    unchecked, which a reviewer should know about even though it isn't fatal.
    """
    guide_url = find_quick_guide_url(index_html)
    if guide_url is None:
        on_progress(
            f"[{category}] WARNING: no quick guide linked, so no payload can be "
            f"cross-checked"
        )
        return GuidePayloads()

    on_progress(f"[{category}] downloading {guide_url} for the payload cross-check ...")
    guide = http.fetch(guide_url)
    if guide.status_code != 200:
        on_progress(
            f"[{category}] WARNING: quick guide returned {guide.status_code}, so no "
            f"payload can be cross-checked"
        )
        return GuidePayloads()

    payloads = parse_guide_payloads(extract_text(guide.file_path).text)
    if payloads.is_empty():
        on_progress(
            f"[{category}] WARNING: no payload figures found in the quick guide, so "
            f"none can be cross-checked"
        )
        return payloads

    total = sum(sum(group.values()) for group in payloads.by_floorplan.values())
    on_progress(
        f"[{category}] quick guide holds {total + sum(payloads.loose.values())} "
        f"payload figure(s) to check against"
    )
    return payloads
