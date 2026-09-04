"""Bailey (baileyofbristol.co.uk) — touring caravans. The first caravan adapter.

The sibling of `bailey.py`, and a separate module rather than a flag on it: FMLV keeps
motorhomes and touring caravans as separate exports with separate schemas, so this one
produces `Caravan`s and registers under `(Bailey, caravan)`. See `docs/adapters/bailey.md`
for the motorhome survey; the caravan section of that file covers what follows.

**The site is as clean here as it is for motorhomes** — one URL is one vehicle, at
`/touring-caravans/<range>/<slug>/`, plain server-rendered HTML with a "Technical
specification" section carrying explicit literal `Range` and `Model` fields. The
`col-6` markup is identical, so every parsing helper is imported from `bailey.py`
unchanged rather than reimplemented:

    Range                 Pegasus Black
    Model                 Messina
    Berths                4
    Axle                  Twin
    Internal Length       6.332m / 20'9"
    Shipping Length       7.905m / 25'11"
    Overall Width         2.433m / 8'0"
    Overall Height        2.582m / 8'6"
    Internal Headroom     1.960m / 6'5"
    Awning Size           1089.1cm
    MTPLM                 1712kg
    MRO                   1552kg
    Total User Payload    160kg
    RRP Price             £34,499

**Three things this adapter does not do, each for a stated reason.**

*No exterior body length.* Bailey publish internal and shipping length and nothing
between them — the field does not appear on any of the 23 model pages. The requester's
reading (3 September 2026) is that this is an industry trend rather than one brand's
omission, so `exterior_body_length_mm` was taken out of automated scope in
`config/field_guide_caravan.csv` entirely. Whatever FMLV already holds is left alone.

*No layout flags.* The pages describe the layout in marketing prose — "parallel seat
front lounge and rear island king size bed" — and a bed-sizes block naming Front Double,
Front N/S Single and Rear Fixed Double. That is enough to guess from and not enough to be
right, and a wrong layout flag is worse than a visible gap. `bailey.py` takes the same
line: it sets `body_type` only because Bailey state the roof profile outright.

*No `optional_equipment_payload_kilograms`.* Out of scope, and blank on all 92 real
caravan products FMLV holds.

**Body type is always rigid.** Not inferred — stated by the requester, and true of all 81
Bailey caravans in FMLV. The micro rule (manufacturer's own naming *and* MTPLM ≤ 1250kg)
never fires here: Bailey market nothing as a micro, and the four products under that
weight are all held as rigid.

**Two range names are abbreviated in the spec table.** It gives `Pegasus Black` and
`Phoenix Black`; FMLV holds `Pegasus Black Edition` and `Phoenix Black Edition`. The
requester confirmed the longer form is the real name — the brochure and the URL slug both
carry "Edition", and only the specification template drops it. Note the page's own `<h1>`
and `<title>` abbreviate it too, so there is no better in-page source to read instead:
hence an explicit correction table, the same resolution `bailey.py` uses for
`Autograph` -> `Autograph IV`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.caravan import Caravan
from ..product_model.enums import CaravanBodyType
from ..vehicle_class import VehicleClass
from .bailey import _field, _kilograms, _leading_int, _metres_to_mm
from .base import ExtractedCaravan, Provenance

BASE_URL = "https://www.baileyofbristol.co.uk"
MANUFACTURER = "Bailey"
MANUFACTURER_DISPLAY_NAME = "Bailey"

#: What makes this adapter the caravan one. Without it `ADAPTERS` would register it under
#: `(Bailey, motorhome)` and it would silently replace `bailey.py`.
VEHICLE_CLASS = VehicleClass.CARAVAN

#: The index listing every current model, across all ranges. Bailey have a per-range page
#: too, but this one page links all 23 models, so a full sweep is one fetch rather than
#: five. Note `/caravans/` — the URL a person would guess — returns an `image/png` with a
#: 200 status; `/touring-caravans/` is the real section root.
MODELS_INDEX_PATH = "current-caravan-models"

#: (range path segment, label) for `--range`. The label is what a reviewer picks; the real
#: `manufacturer_range` is read from each page's own `Range` field.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("alicanto-grande-deluxe", "Alicanto Grande Deluxe"),
    ("discovery", "Discovery"),
    ("pegasus-black-edition", "Pegasus Black Edition"),
    ("phoenix-black-edition", "Phoenix Black Edition"),
    ("unicorn-deluxe", "Unicorn Deluxe"),
)

#: A range whose literal `Range` field abbreviates the real name — see the module
#: docstring. `Unicorn Deluxe`, `Alicanto Grande Deluxe` and `Discovery` need no entry:
#: the spec table already gives FMLV's own spelling for those three.
RANGE_NAME_CORRECTIONS: dict[str, str] = {
    "Pegasus Black": "Pegasus Black Edition",
    "Phoenix Black": "Phoenix Black Edition",
}

#: Bailey's own `Axle` value, lower-cased, that means two axles. Anything else — `Single`,
#: or a value nobody has seen yet — leaves `twin_axle` False, which is also the FMLV
#: default, so an unrecognised value understates rather than inventing a second axle.
_TWIN_AXLE_VALUE = "twin"

#: Awning size is the one dimension Bailey give in centimetres rather than metres
#: (`1089.1cm`), and to a tenth of a centimetre. 1089.1cm -> 10891mm exactly, which is the
#: figure FMLV already holds for that product.
_CENTIMETRES = re.compile(r"([\d.]+)\s*cm")

#: `'£34,499'` -> `34499`. Read from the spec table's own `RRP Price` row, unlike
#: `bailey.py`, which has to use the hero banner because both price rows are
#: HTML-commented out on motorhome and campervan pages. On caravan pages `RRP Price` is
#: live and `OTR Price` is the empty one — the reverse of the motorhome template.
_PRICE = re.compile(r"£\s*([\d,]+)")

#: One model page URL, scoped to a range so a link elsewhere on the page is never picked
#: up. Anchored on the `/touring-caravans/<range>/<slug>/` shape, which also excludes the
#: `#interior360` variants the index lists alongside each model.
_MODEL_URL = re.compile(
    rf'href="({re.escape(BASE_URL)}/touring-caravans/[a-z0-9-]+/[a-z0-9-]+/)"'
)


def _centimetres_to_mm(raw: str | None) -> int | None:
    if raw is None:
        return None
    match = _CENTIMETRES.search(raw)
    return round(float(match.group(1)) * 10) if match else None


def _price(raw: str | None) -> int | None:
    if raw is None:
        return None
    match = _PRICE.search(raw)
    return int(match.group(1).replace(",", "")) if match else None


def fmlv_range_name(raw: str | None) -> str | None:
    """The range name as FMLV spells it, correcting the spec table's abbreviations."""
    if raw is None:
        return None
    cleaned = " ".join(raw.split())
    return RANGE_NAME_CORRECTIONS.get(cleaned, cleaned) or None


def find_model_urls(index_html: str, path: str | None = None) -> list[str]:
    """Every model page linked from the index, in document order, optionally one range.

    `path` narrows to a single range segment for a `--range` run; `None` takes all of
    them. Duplicates are collapsed because the index links each model twice — once for
    the model itself and once for its `#interior360` tour.
    """
    seen: dict[str, None] = {}
    for match in _MODEL_URL.finditer(index_html):
        url = match.group(1)
        if path is None or url.startswith(f"{BASE_URL}/touring-caravans/{path}/"):
            seen.setdefault(url, None)
    return list(seen)


@dataclass(frozen=True)
class BaileyCaravan:
    """One caravan model, as read from its own page."""

    manufacturer_range: str | None
    model: str | None
    berths: int | None
    twin_axle: bool
    rrp_pounds: int | None
    mtplm_kilograms: int | None
    mro_kilograms: int | None
    personal_effects_payload_kilograms: int | None
    internal_length_mm: int | None
    shipping_length_mm: int | None
    overall_width_mm: int | None
    height_mm: int | None
    headroom_mm: int | None
    awning_length_mm: int | None

    @property
    def label(self) -> str:
        return " ".join(part for part in (self.manufacturer_range, self.model) if part)

    @property
    def payload_reconciles(self) -> bool | None:
        """Whether `Total User Payload` equals `MTPLM - MRO`, or `None` if unknowable.

        True on all 23 current models. `bailey.py` runs the same check for the same
        reason: it is the one arithmetic relationship the page states three sides of, so
        it catches a misread figure that is otherwise perfectly plausible.
        """
        if None in (self.mtplm_kilograms, self.mro_kilograms):
            return None
        if self.personal_effects_payload_kilograms is None:
            return None
        assert self.mtplm_kilograms is not None
        assert self.mro_kilograms is not None
        derived = self.mtplm_kilograms - self.mro_kilograms
        return derived == self.personal_effects_payload_kilograms


def parse_model_page(html: str) -> BaileyCaravan:
    """Read one model page's "Technical specification" section."""
    axle = _field(html, "Axle")
    return BaileyCaravan(
        manufacturer_range=fmlv_range_name(_field(html, "Range")),
        model=_field(html, "Model"),
        berths=_leading_int(_field(html, "Berths")),
        twin_axle=bool(axle and axle.strip().lower() == _TWIN_AXLE_VALUE),
        rrp_pounds=_price(_field(html, "RRP Price")),
        mtplm_kilograms=_kilograms(_field(html, "MTPLM")),
        mro_kilograms=_kilograms(_field(html, "MRO")),
        personal_effects_payload_kilograms=_kilograms(_field(html, "Total User Payload")),
        internal_length_mm=_metres_to_mm(_field(html, "Internal Length")),
        shipping_length_mm=_metres_to_mm(_field(html, "Shipping Length")),
        overall_width_mm=_metres_to_mm(_field(html, "Overall Width")),
        height_mm=_metres_to_mm(_field(html, "Overall Height")),
        headroom_mm=_metres_to_mm(_field(html, "Internal Headroom")),
        awning_length_mm=_centimetres_to_mm(_field(html, "Awning Size")),
    )


def build_extracted(product: BaileyCaravan, source_url: str) -> ExtractedCaravan:
    """One parsed page as a `Caravan` plus the provenance a reviewer sees beside it."""
    caravan = Caravan(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.manufacturer_range,
        model=product.model,
        berths=product.berths,
        rrp_pounds=product.rrp_pounds,
        mtplm_kilograms=product.mtplm_kilograms,
        mro_kilograms=product.mro_kilograms,
        personal_effects_payload_kilograms=product.personal_effects_payload_kilograms,
        internal_length_mm=product.internal_length_mm,
        shipping_length_mm=product.shipping_length_mm,
        overall_width_mm=product.overall_width_mm,
        height_mm=product.height_mm,
        headroom_mm=product.headroom_mm,
        awning_length_mm=product.awning_length_mm,
        twin_axle=product.twin_axle,
        body_type=CaravanBodyType.RIGID,
    )

    provenance: dict[str, Provenance] = {}

    def record(field_name: str, snippet: str) -> None:
        provenance[field_name] = Provenance(
            source_url=source_url, snippet=f"{product.label} — {snippet}"
        )

    if product.rrp_pounds is not None:
        record("rrp_pounds", f"RRP Price: £{product.rrp_pounds:,}")
    if product.berths is not None:
        record("berths", f"Berths: {product.berths}")
    if product.mtplm_kilograms is not None:
        record("mtplm_kilograms", f"MTPLM: {product.mtplm_kilograms}kg")
    if product.mro_kilograms is not None:
        record("mro_kilograms", f"MRO: {product.mro_kilograms}kg")
    if product.personal_effects_payload_kilograms is not None:
        record(
            "personal_effects_payload_kilograms",
            f"Total User Payload: {product.personal_effects_payload_kilograms}kg",
        )
    if product.internal_length_mm is not None:
        record("internal_length_mm", f"Internal Length: {product.internal_length_mm / 1000:.3f}m")
    if product.shipping_length_mm is not None:
        record("shipping_length_mm", f"Shipping Length: {product.shipping_length_mm / 1000:.3f}m")
    if product.overall_width_mm is not None:
        record("overall_width_mm", f"Overall Width: {product.overall_width_mm / 1000:.3f}m")
    if product.height_mm is not None:
        record("height_mm", f"Overall Height: {product.height_mm / 1000:.3f}m")
    if product.headroom_mm is not None:
        record("headroom_mm", f"Internal Headroom: {product.headroom_mm / 1000:.3f}m")
    if product.awning_length_mm is not None:
        record("awning_length_mm", f"Awning Size: {product.awning_length_mm / 10:.1f}cm")

    # Always recorded, never conditional: both are asserted by this adapter rather than
    # read off the page, and a reviewer should see that stated rather than infer it from
    # a value appearing with no source.
    record("twin_axle", f"Axle: {'Twin' if product.twin_axle else 'Single'}")
    record("body_type", "Bailey build only rigid caravans — no folding, pop-up or micro")

    return ExtractedCaravan(caravan=caravan, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object = None,
    snapshot_dir: Path | None = None,
    *,
    ranges: tuple[tuple[str, str], ...] | None = None,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedCaravan]:
    """Fetch and parse every current Bailey caravan, or just the named ranges.

    `browser` and `snapshot_dir` are unused — the whole site is server-rendered, and
    `http` snapshots every request itself — but stay in the signature because
    `cli.execute_run` passes them positionally to every adapter.
    """
    index_url = f"{BASE_URL}/{MODELS_INDEX_PATH}/"
    on_progress(f"fetching the Bailey caravan model index: {index_url}")
    index_html = http.fetch(index_url).file_path.read_text(encoding="utf-8", errors="replace")

    paths = [path for path, _label in (ranges or DEFAULT_RANGES)] if ranges else [None]
    model_urls: list[str] = []
    for path in paths:
        found = find_model_urls(index_html, path)
        if path is not None and not found:
            on_progress(f"no model pages found for range {path!r} — skipping")
        model_urls.extend(url for url in found if url not in model_urls)

    on_progress(f"found {len(model_urls)} Bailey caravan model page(s)")

    extracted: list[ExtractedCaravan] = []
    for url in model_urls:
        html = http.fetch(url).file_path.read_text(encoding="utf-8", errors="replace")
        product = parse_model_page(html)

        if not product.model:
            on_progress(f"skipping {url} — no Model field in its technical specification")
            continue

        if product.payload_reconciles is False:
            # Narrated, not dropped: the figures are Bailey's own, and a reviewer seeing
            # the three numbers can judge. Silently discarding the product would hide a
            # real page behind an arithmetic quibble.
            on_progress(
                f"{product.label}: Total User Payload "
                f"{product.personal_effects_payload_kilograms}kg does not equal MTPLM - MRO "
                f"({product.mtplm_kilograms} - {product.mro_kilograms}) — recording anyway"
            )

        extracted.append(build_extracted(product, url))
        on_progress(f"read {product.label}")

    return extracted
