"""Swift (swiftgroup.co.uk) — touring caravans, from the range pages' own JSON.

The sibling of `swift.py`, and a separate module rather than a flag on it: FMLV keeps
motorhomes and touring caravans as separate exports with separate schemas, so this one
produces `Caravan`s and registers under `("Swift Group Ltd", caravan)`. See the caravan
section of `docs/adapters/swift.md` for the survey this was built from.

**Built on `swift.py`, not on `bailey_caravan.py`.** Bailey's caravans are one page per
vehicle with a literal spec table; Swift's are the same shape as Swift's motorhomes —
one page per *range*, carrying a `<script type="application/json"
data-product-layouts-data>` block with one object per layout. Every parsing helper is
imported from the motorhome module unchanged, `range_and_model` included:

    {"id":1479,"title":"Sprite Alpine 4","code":"sprite-alpine-4",
     "priceLabel":"From \\u00A322,585","berths":"4 berths",
     "axleType":"Caravan - Single axle","length":"6.45m","width":"2.23m",
     "weightMtplm":"1247kg","weightMro":"1102kg",
     "optionalWeightPlateUpgrade":"1300kg", ...}

Seven range pages, 26 layouts: Sprite (4), Sprite Grande (1), Challenger (6), Challenger
Grande (4), Conqueror (3), Conqueror Grande (4), Elegance Grande (4). The same
brochure-retirement trap applies as for the motorhomes and for the same reason —
`2026_swift_caravan_brochure.pdf` is still live and still linked from `/brochures/`, so
nothing here searches that directory and the guide pattern is anchored on `quick-guide`.

**`length` IS THE SHIPPING LENGTH.** This is the single most consequential thing the
survey established, and it is not inferable from the site: Swift publish one length and
never say which of the four it is. Two independent sources settle it. The 2026 brochure's
"Specification at a glance" table labels its columns, and gives the Alpine 4 an *Internal
Length* of 4.74m against an *Overall Length* of 6.45m; FMLV holds that product as
`internal_length_mm=4740, shipping_length_mm=6450`. The site's `6.45m` is the overall
figure, so it maps to `shipping_length_mm` and to nothing else. Mapping it to
`internal_length_mm` would overstate every caravan's habitable space by 1.5-1.7m while
looking entirely plausible on any one product — `docs/adapters/README.md` names this as
the most likely single way to get a caravan adapter wrong.

**Range names need no corrections, which was checked rather than assumed.** FMLV's own
export already holds `Sprite`, `Challenger`, `Challenger Grande`, `Conqueror`,
`Conqueror Grande` and `Elegance Grande` exactly as the site's range pages divide them,
`Conqueror Grande` + `560L` included; `Sprite Grande` is in the export from an earlier
model year, so the 2027 Quattro FB joins a range FMLV already knows. Contrast the
brochure, which files every Grande as a *model* under its parent range ("Challenger /
Grande 580") — following the printed document instead of the site would have proposed
nine renames FMLV does not want.

**Four fields Swift published in the brochure and no longer publish at all**, so all four
are deliberately not emitted and are narrated once per run instead. FMLV holds good
figures for every one of them on the 24 carried-over products, and per
`docs/adapters/README.md` a figure that could not be found must be left alone rather than
guessed at or back-filled from last season's document — the same call `swift.py` makes
for motorhome heights, and for the same reason.

* `internal_length_mm` — brochure only. Not to be confused with
  `exterior_body_length_mm`, which is out of automated scope globally.
* `height_mm` — brochure only (2.59m/2.61m).
* `awning_length_mm` — brochure's "Awning A/A Dimension" only.
* `personal_effects_payload_kilograms` — see below. This one is subtler.

**THE PAYLOAD IS A TOTAL, AND MUST NOT BE WRITTEN TO THE PERSONAL-EFFECTS COLUMN.**
Swift publish one figure, `Max Payload`, and it equals `MTPLM - MRO` on all 26. FMLV has
*two* payload columns, and on the four Elegance Grandes it uses both: `personal_effects`
160kg plus `optional_equipment` 41kg makes the 201kg the guide prints. Emitting 201 as
the personal-effects figure would propose 160 -> 201 on those four, and since
`optional_equipment_payload_kilograms` is out of scope its 41kg would survive untouched —
leaving 242kg of payload against 201kg of actual capacity, an internally inconsistent
product that reads as a routine update. Swift do not publish the split (the 2026 brochure
does not either), so this adapter cannot supply it and does not try. The figure is used
as the self-check and nowhere else.

Note this contradicts `docs/adapters/README.md`'s "blank on all 92 real caravan products",
which was true of Bailey and Adria and is not true of Swift.

**The self-check is cross-document and came out an exact bijection.** The JSON publishes
MTPLM and MRO but no payload; the quick guide publishes payload, length, width and MTPLM
but no MRO. So `payload == MTPLM - MRO` is a real check across two documents rather than
an arithmetic tautology, and the guide's length and width corroborate the site's on top of
it. On 2026-09-03: 26 guide blocks, 26 site products, every one agreeing on all three
figures, none left over.

Entries are keyed on **MTPLM, not on the model name**, because Swift's two documents
disagree about names — the guide calls the Elegance layouts `Grande 850 L` and
`Grande 860 L` where both the site and FMLV call them `850` and `860`, and it prefixes
`Grande ` to every model the site leaves bare. MTPLM is published identically by both and
is near-unique: the only repeat across all 26 is 1886kg, shared by Conqueror Grande 645
and 650L, which carry the same payload as each other anyway.

**Two axle corrections are expected on the first run, and they are this adapter working.**
FMLV holds Challenger Grande 580 and Conqueror Grande 580 as twin-axle. Swift's 2027 JSON
says `Caravan - Single axle` for both; the 2027 guide's per-range counts agree (Challenger
7 single / 3 twin, Conqueror 5 single / 2 twin, which only balances if those two are
single); and the 2026 brochure's "Number of Axles" column already said 1. Three Swift
sources against one FMLV field.

**`optionalWeightPlateUpgrade` is not the MTPLM.** Every layout carries one — 1300kg
against the Alpine 4's 1247kg MTPLM — and it is an optional dealer upgrade. Per
`docs/adapters/README.md` the base figure is the one to record, so this field is read by
nothing here. It is named in the docstring and covered by a test because it sits
immediately beside `weightMtplm` in the same object and is the obvious wrong pick.

**Everything is rigid.** Swift's 2027 caravans are all rigid: no folding or pop-up, and no
micro. The micro trap is live rather than theoretical — Challenger 390's MTPLM is 1118kg,
below the 1250kg threshold — but the rule needs the manufacturer's own naming *as well as*
the weight, and Swift market nothing as a micro. Their one genuinely small vehicle,
Basecamp (1043kg), was held by FMLV as rigid too and is discontinued for 2027, so it will
be reported as disappeared.

**Headroom is scraped, not assumed.** Every range page states `1.95m (6'5") headroom` in
its own highlights, and FMLV holds 1950mm on all 26. It is read off each page rather than
hard-coded so that a range which changes it, or a page which stops saying it, comes out
narrated instead of silently wrong.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.caravan import Caravan
from ..product_model.enums import CaravanBodyType
from ..vehicle_class import VehicleClass
from .base import ExtractedCaravan, Provenance
from .swift import (
    BASE_URL,
    MANUFACTURER,
    MANUFACTURER_DISPLAY_NAME,
    _kilograms,
    _leading_int,
    _metres_to_mm,
    _price,
    find_quick_guide_url,
    parse_layouts_json,
    range_and_model,
)

__all__ = [
    "BASE_URL",
    "DEFAULT_RANGES",
    "MANUFACTURER",
    "MANUFACTURER_DISPLAY_NAME",
    "VEHICLE_CLASS",
    "SwiftCaravan",
    "collect",
]

#: What makes this adapter the caravan one. Without it `ADAPTERS` would register it under
#: `("Swift Group Ltd", motorhome)` and it would silently replace `swift.py`.
VEHICLE_CLASS = VehicleClass.CARAVAN

#: The one index page listing every caravan range. Unlike Bailey — where `/caravans/`
#: serves an `image/png` with a 200 status and `/touring-caravans/` is the real root —
#: Swift's guessable URL is the right one.
CARAVANS_INDEX_PATH = "caravans"

#: (range page slug, label) for `--range`. The label is what a reviewer picks; the real
#: `manufacturer_range` is read from each layout's own title via `range_and_model`.
#:
#: The slug is the key rather than the full path because the path carries Swift's CMS node
#: id (`/caravans/product/1303/swift-sprite/`), which is not derivable and changes when a
#: range is rebuilt — Conqueror's is 72924 where the other six are four-digit. So paths
#: are always rediscovered from the index per run and filtered by slug.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("swift-sprite", "Sprite"),
    ("swift-sprite-grande", "Sprite Grande"),
    ("swift-challenger", "Challenger"),
    ("swift-challenger-grande", "Challenger Grande"),
    ("swift-conqueror", "Conqueror"),
    ("swift-conqueror-grande", "Conqueror Grande"),
    ("swift-elegance-grande", "Elegance Grande"),
)

#: The range pages linked from the caravan index, e.g.
#: `/caravans/product/1303/swift-sprite/`.
#:
#: **Scoped to `/caravans/` on purpose**, the same way `swift.py` interpolates its
#: category. Swift's nav block is global and repeated on every page, so this index links
#: every motorhome and campervan range too; a pattern matching `/[^/]+/product/` would
#: read all sixteen ranges and hand nine motorhome ranges to a caravan parser.
_RANGE_PAGE_HREF = re.compile(r'href="(/caravans/product/\d+/[^"#?]+/)"')

#: `Caravan - Twin axle` against `Caravan - Single axle`. Matched on the word rather than
#: on the whole string so an unseen prefix still reads: anything that is not recognisably
#: twin leaves `twin_axle` False, which is also FMLV's default, so a new value
#: understates rather than inventing a second axle.
_TWIN_AXLE = re.compile(r"\btwin\b", re.IGNORECASE)

#: `1.95m (6'5") headroom` from a range page's own highlights list, after markup is
#: stripped. Stated once per range and identical on all seven.
_HEADROOM = re.compile(r"([\d.]+)\s*m\s*\([^)]{0,20}\)\s*headroom", re.IGNORECASE)

#: Tags, scripts and styles, so the highlights prose can be read as text.
_MARKUP = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.DOTALL | re.IGNORECASE)

#: One layout's block in the quick guide. Every one of the 26 is printed in full, so
#: unlike the motorhome guide there is no compact payload-only variant to also read.
#:
#: The model name is deliberately **not** captured. It is there in the PDF, but the
#: preceding layout's berth count runs into it with no separator (`4Alpine 4`, `2390`),
#: and the guide spells names differently from the site anyway — see the module docstring.
#: MTPLM is the key instead.
_GUIDE_BLOCK = re.compile(
    r"Length\s*\n\s*([\d.]+)m[^\n]*\n"
    r"\s*Max Payload\s*\n\s*(\d+)\s*kg[^\n]*\n"
    r"\s*MTPLM\s*\n\s*(\d+)\s*kg[^\n]*\n"
    r"\s*Width[^\n]*\n\s*([\d.]+)\s*m"
)


@dataclass(frozen=True)
class GuideEntry:
    """One layout as the quick guide prints it: the three figures it shares with the site."""

    payload_kilograms: int
    shipping_length_mm: int
    overall_width_mm: int


@dataclass
class GuideSpecs:
    """Every quick guide block, keyed on MTPLM — see the module docstring for why.

    `matched` records which MTPLMs a site product claimed, so `collect` can report guide
    entries nothing on the site accounts for. A left-over entry means the guide and the
    site disagree about what Swift currently sell, which is worth a reviewer's attention
    even though neither document is wrong about the products it does list.
    """

    by_mtplm: dict[int, list[GuideEntry]] = field(default_factory=dict)
    matched: set[int] = field(default_factory=set)

    @property
    def entry_count(self) -> int:
        return sum(len(entries) for entries in self.by_mtplm.values())

    def unmatched(self) -> list[int]:
        return sorted(set(self.by_mtplm) - self.matched)

    def check(self, product: SwiftCaravan) -> tuple[bool, str]:
        """Whether the guide corroborates this layout's payload, length and width.

        Returns `(True, reason)` when the guide agrees *and* when it has nothing to say —
        the two are distinguished by the reason string, and `collect` drops only on
        `False`. That asymmetry is `swift.py`'s and is deliberate: one JSON object is one
        vehicle, so there is no join here to misalign, and the risk being defended against
        is Swift mis-stating a figure. Losing a real caravan over a gap in a marketing
        leaflet's coverage would be the worse error.
        """
        if not self.by_mtplm:
            return True, "no quick guide to check against"
        if product.mtplm_kilograms is None:
            return True, "no MTPLM on the site to check"
        entries = self.by_mtplm.get(product.mtplm_kilograms)
        if not entries:
            return True, f"MTPLM {product.mtplm_kilograms}kg is not in the quick guide"
        self.matched.add(product.mtplm_kilograms)
        derived = product.derived_payload_kilograms
        if derived is None:
            return True, "no MRO on the site, so no payload to check"
        for entry in entries:
            if (
                entry.payload_kilograms == derived
                and entry.shipping_length_mm == product.shipping_length_mm
                and entry.overall_width_mm == product.overall_width_mm
            ):
                return True, f"quick guide agrees: Max Payload {derived}kg"
        expected = ", ".join(
            f"payload {entry.payload_kilograms}kg / length {entry.shipping_length_mm}mm / "
            f"width {entry.overall_width_mm}mm"
            for entry in entries
        )
        return False, (
            f"MTPLM {product.mtplm_kilograms}kg - MRO {product.mro_kilograms}kg = "
            f"{derived}kg with length {product.shipping_length_mm}mm and width "
            f"{product.overall_width_mm}mm, but the quick guide says {expected}"
        )


@dataclass(frozen=True)
class SwiftCaravan:
    """One caravan layout, as read from its range page's JSON."""

    manufacturer_range: str
    model: str
    berths: int | None = None
    rrp_pounds: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    shipping_length_mm: int | None = None
    overall_width_mm: int | None = None
    headroom_mm: int | None = None
    twin_axle: bool = False
    #: Swift's own `axleType` string, quoted to the reviewer beside `twin_axle` — the two
    #: corrections this adapter proposes against FMLV's baseline are both axle counts, so
    #: the evidence needs to be visible rather than implied by a bare Yes/No.
    axle_evidence: str | None = None

    @property
    def label(self) -> str:
        return f"{self.manufacturer_range} {self.model}"

    @property
    def derived_payload_kilograms(self) -> int | None:
        """`MTPLM - MRO`, the total the guide's `Max Payload` is checked against.

        Not emitted as `personal_effects_payload_kilograms` — see the module docstring.
        """
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms


def find_range_page_paths(index_html: str, slug: str | None = None) -> list[str]:
    """Every caravan range page linked from the index, first-seen order, optionally one.

    `slug` narrows to a single range for a `--range` run; `None` takes all seven. Paths
    are de-duplicated because Swift link each range from both the page body and the
    global nav.
    """
    seen: list[str] = []
    for path in _RANGE_PAGE_HREF.findall(index_html):
        if slug is not None and not path.rstrip("/").endswith(f"/{slug}"):
            continue
        if path not in seen:
            seen.append(path)
    return seen


def find_headroom_mm(page_html: str) -> int | None:
    """The internal headroom a range page states in its own highlights, in mm."""
    text = _MARKUP.sub("\n", page_html)
    match = _HEADROOM.search(text)
    return _metres_to_mm(f"{match.group(1)}m") if match else None


def parse_guide_specs(guide_text: str) -> GuideSpecs:
    """Every layout block in the caravan quick guide, keyed on MTPLM."""
    specs = GuideSpecs()
    for length, payload, mtplm, width in _GUIDE_BLOCK.findall(guide_text):
        shipping = _metres_to_mm(f"{length}m")
        overall_width = _metres_to_mm(f"{width}m")
        if shipping is None or overall_width is None:
            continue
        specs.by_mtplm.setdefault(int(mtplm), []).append(
            GuideEntry(
                payload_kilograms=int(payload),
                shipping_length_mm=shipping,
                overall_width_mm=overall_width,
            )
        )
    return specs


def parse_range_page(page_html: str, *, slug: str) -> list[SwiftCaravan]:
    """Every layout on one range page.

    A layout whose title cannot be split into a range and a model is dropped here and
    reported by `collect`: without both halves there is nothing to match a baseline
    product on, and `docs/adapters/README.md` requires the two to move together.
    """
    headroom_mm = find_headroom_mm(page_html)
    products: list[SwiftCaravan] = []
    for layout in parse_layouts_json(page_html):
        title = str(layout.get("title") or "")
        split = range_and_model(title, slug)
        if split is None:
            continue
        manufacturer_range, model = split
        axle = layout.get("axleType")
        products.append(
            SwiftCaravan(
                manufacturer_range=manufacturer_range,
                model=model,
                berths=_leading_int(layout.get("berths")),
                rrp_pounds=_price(layout.get("priceLabel")),
                # `optionalWeightPlateUpgrade` sits right beside this and is an optional
                # dealer upgrade, never the base figure — see the module docstring.
                mtplm_kilograms=_kilograms(layout.get("weightMtplm")),
                mro_kilograms=_kilograms(layout.get("weightMro")),
                # Swift's one published length is the overall/shipping figure.
                shipping_length_mm=_metres_to_mm(layout.get("length")),
                overall_width_mm=_metres_to_mm(layout.get("width")),
                headroom_mm=headroom_mm,
                twin_axle=bool(axle and _TWIN_AXLE.search(axle)),
                axle_evidence=str(axle) if axle else None,
            )
        )
    return products


def unsplittable_titles(page_html: str, *, slug: str) -> list[str]:
    """Layout titles on this page that `range_and_model` could not split.

    Kept separate from `parse_range_page` so the narration in `collect` can name them
    without that function having to return two lists.
    """
    return [
        str(layout.get("title") or "")
        for layout in parse_layouts_json(page_html)
        if range_and_model(str(layout.get("title") or ""), slug) is None
    ]


def build_extracted(product: SwiftCaravan, source_url: str) -> ExtractedCaravan:
    """One parsed layout as a `Caravan` plus the provenance a reviewer sees beside it."""
    caravan = Caravan(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.manufacturer_range,
        model=product.model,
        berths=product.berths,
        rrp_pounds=product.rrp_pounds,
        mtplm_kilograms=product.mtplm_kilograms,
        mro_kilograms=product.mro_kilograms,
        shipping_length_mm=product.shipping_length_mm,
        overall_width_mm=product.overall_width_mm,
        headroom_mm=product.headroom_mm,
        twin_axle=product.twin_axle,
        body_type=CaravanBodyType.RIGID,
    )

    provenance: dict[str, Provenance] = {}

    def record(field_name: str, snippet: str) -> None:
        provenance[field_name] = Provenance(
            source_url=source_url, snippet=f"{product.label} — {snippet}"
        )

    # Both halves of the identity, always, and each snippet says so. `compare_fields`
    # walks only fields that have provenance and the missing-field check fires only where
    # nothing at all was found, so a `model` read but left unrecorded is neither compared
    # nor reported — and accepting a range change without its model corrupts the name.
    record(
        "manufacturer_range",
        f'range "{product.manufacturer_range}" from the layout title '
        f'"{product.label}" — accept with the model, they are one name',
    )
    record(
        "model",
        f'model "{product.model}" from the layout title "{product.label}" '
        f"— accept with the range, they are one name",
    )

    if product.rrp_pounds is not None:
        record("rrp_pounds", f"From £{product.rrp_pounds:,}")
    if product.berths is not None:
        record("berths", f"{product.berths} berths")
    if product.mtplm_kilograms is not None:
        record("mtplm_kilograms", f"MTPLM: {product.mtplm_kilograms}kg")
    if product.mro_kilograms is not None:
        record("mro_kilograms", f"MRO: {product.mro_kilograms}kg")
    if product.shipping_length_mm is not None:
        record(
            "shipping_length_mm",
            f"Length: {product.shipping_length_mm / 1000:.2f}m — Swift's one published "
            f"length is the overall figure, which includes the towing hitch",
        )
    if product.overall_width_mm is not None:
        record("overall_width_mm", f"Width: {product.overall_width_mm / 1000:.2f}m")
    if product.headroom_mm is not None:
        record(
            "headroom_mm",
            f"{product.headroom_mm / 1000:.2f}m headroom, stated on the range page",
        )

    # Always recorded, never conditional. `twin_axle` is Swift's own value but its
    # provenance has to carry their wording, because two of these disagree with FMLV's
    # baseline. `body_type` is asserted by this adapter rather than read off the page, and
    # a reviewer should see that stated rather than infer it from an unsourced value.
    record("twin_axle", f"axleType: {product.axle_evidence or 'not stated'}")
    record(
        "body_type",
        "Swift's 2027 caravans are all rigid — no folding or pop-up, and nothing marketed "
        "as a micro",
    )

    return ExtractedCaravan(caravan=caravan, provenance=provenance)


def _load_guide(
    http: Fetcher, index_html: str, on_progress: Callable[[str], None]
) -> GuideSpecs:
    """The quick guide's payload/length/width blocks, or an empty set if unavailable.

    Every failure here is narrated and survivable: the guide is the self-check, not the
    product source, so a run without it collects the same 26 caravans with the check
    reported as unavailable rather than losing the lot.
    """
    guide_url = find_quick_guide_url(index_html)
    if guide_url is None:
        on_progress("no caravan quick guide linked from the index — self-check unavailable")
        return GuideSpecs()

    on_progress(f"fetching the caravan quick guide: {guide_url}")
    guide = extract_text(http.fetch(guide_url).file_path)
    if guide.is_empty():
        on_progress(f"{guide_url} holds no extractable text — self-check unavailable")
        return GuideSpecs()

    specs = parse_guide_specs(guide.text)
    if not specs.by_mtplm:
        on_progress(f"no payload blocks found in {guide_url} — self-check unavailable")
        return specs

    on_progress(f"read {specs.entry_count} payload block(s) from the quick guide")
    return specs


def collect(
    http: Fetcher,
    browser: object = None,
    snapshot_dir: Path | None = None,
    *,
    ranges: tuple[tuple[str, str], ...] | None = None,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedCaravan]:
    """Fetch and parse every current Swift caravan, or just the named ranges.

    `browser` and `snapshot_dir` are unused — the range pages are server-rendered and
    `http` snapshots every request itself — but stay in the signature because
    `cli.execute_run` passes them positionally to every adapter.
    """
    index_url = f"{BASE_URL}/{CARAVANS_INDEX_PATH}/"
    on_progress(f"fetching the Swift caravan index: {index_url}")
    index_html = http.fetch(index_url).file_path.read_text(encoding="utf-8", errors="replace")

    guide = _load_guide(http, index_html, on_progress)

    slugs = [slug for slug, _label in ranges] if ranges else [None]
    paths: list[str] = []
    for slug in slugs:
        found = find_range_page_paths(index_html, slug)
        if slug is not None and not found:
            on_progress(f"no range page found for {slug!r} — skipping")
        paths.extend(path for path in found if path not in paths)

    on_progress(f"found {len(paths)} Swift caravan range page(s)")

    extracted: list[ExtractedCaravan] = []
    for path in paths:
        url = f"{BASE_URL}{path}"
        slug = path.rstrip("/").split("/")[-1]
        page_html = http.fetch(url).file_path.read_text(encoding="utf-8", errors="replace")

        for title in unsplittable_titles(page_html, slug=slug):
            # Dropped rather than guessed at: both halves of the identity have to move
            # together, and a layout with only one is unmatchable against the baseline.
            on_progress(f"skipping layout {title!r} on {url} — cannot split range from model")

        products = parse_range_page(page_html, slug=slug)
        if not products:
            # A dead CMS node, which Swift leave live — `swift.py` hit three such
            # `merlin` placeholders on the motorhome side.
            on_progress(f"no layouts on {url} — skipping")
            continue

        if products[0].headroom_mm is None:
            on_progress(f"{slug}: no headroom stated on {url} — leaving FMLV's own figure")

        for product in products:
            reconciles, reason = guide.check(product)
            if not reconciles:
                on_progress(f"dropping {product.label} — {reason}")
                continue
            if not product.mtplm_kilograms or not product.mro_kilograms:
                on_progress(f"{product.label}: {reason}")
            extracted.append(build_extracted(product, url))
            on_progress(f"read {product.label}")

    for mtplm in guide.unmatched():
        on_progress(
            f"quick guide lists a layout at MTPLM {mtplm}kg that no range page accounts for"
        )

    # Narrated every run, on purpose. These four are all fields Swift published in the
    # retired brochure and publish nowhere now; each is left to arrive as a MissingField
    # so FMLV's own figure is preserved and visibly not scraped. If Swift start publishing
    # any of them again, this is the line that should stop being printed.
    if extracted:
        on_progress(
            f"emitted {len(extracted)} caravan(s) with no internal length, height or awning "
            "size — Swift publish none of them for 2027, and no personal effects payload: "
            "their Max Payload is the MTPLM - MRO total, which FMLV splits across two "
            "columns on the Elegance Grande"
        )

    return extracted
