"""Bailey (baileyofbristol.co.uk) — the twelfth adapter, motorhomes and campervans.

See `docs/adapters/bailey.md` for the full write-up. Bailey is the cleanest source
surveyed so far: **one URL is one vehicle**. Every model has its own page under
`/motorhomes/<range>/<slug>/` or `/campervan/<range>/<slug>/`, plain server-rendered HTML
(no JavaScript, no PDF, no login), carrying a "Technical specification" section with one
row per fact and — unlike every manufacturer surveyed before this one — **explicit
literal `Range` and `Model` text fields**:

    Range                                    Adamo
    Model                                    60-2
    Berths                                   2
    Designated Travelling Seats              2
    Chassis                                  Ford Transit skeletal chassis
    Roof Profile                             Low Profile
    Overall Body Length                      6.096m
    Max Width Vehicle with Mirrors Extended  2.740m
    Max Width Vehicle with Mirrors Folded    2.393m
    Overall Height                           2.863m
    MTPLM                                    3500kg
    MRO                                      2827kg
    Total User Payload                       673kg
    OTR Price                                £75,999

Because it is one vehicle per page there is no column to misalign — the real risk on
almost every other manufacturer surveyed (Morelo, Swift, Sunlight, Etrusco, Bürstner all
print several layouts side by side). `Total User Payload == MTPLM - MRO` reconciles
exactly on every page checked, which is a genuine arithmetic check even without a
column-slip failure mode for it to be defending against here.

**Two places where the site's own naming disagrees with the real FMLV export, resolved
two different ways by the requester (2026-08-20):**

* Three "Adamo" models state `Model: XL-I` / `XL-T` / `XL-DL`. FMLV currently holds these
  under a separate range, `Adamo XL`. **Decision: follow the site.** `Range` and `Model`
  are read verbatim, with no `XL-` splitting — `XL-I` is a model within `Adamo`, not a
  second range. This merges the 3 existing `Adamo XL` products into `Adamo` on the first
  run; that is the intended outcome, not a problem to fix.
* Every "Autograph" model states `Range: Autograph`; FMLV holds `Autograph IV`. **Decision:
  correct it** — see `RANGE_NAME_CORRECTIONS`. Purely cosmetic, no vehicles combined.

**Body type is unusually reliable here too**, because Bailey states it directly rather
than this adapter having to infer it:

* Every motorhome states `Roof Profile: Low Profile` — no A-class or over-cab range
  currently exists, so only that one value is mapped; anything else is left unset and
  narrated rather than guessed (see `_MOTORHOME_ROOF_PROFILES`).
* Campervans state a van body-height code (`H3` seen on both ranges) instead, so the
  existing height-threshold rule from `docs/adapters/README.md` is used against the page's
  own `Overall Height` figure. **No current Bailey campervan gets the elevating-roof
  variant**: the pop-top is stated as a factory-fit *optional* extra on specific models
  only ("B65 & B68 only"), never standard, so per the base-vehicle rule it never changes
  the body type. Revisit `_campervan_body_type` if that ever changes.

**Width**: every page gives `Max Width Vehicle with Mirrors Extended` and `...Folded`,
never a mirror-free figure. The base-vehicle rule takes the narrower one — `Folded`.
Campervan pages also carry a plain `Overall Width` that duplicated the mirrors-extended
figure exactly on the one page checked; treated as a template quirk and not read.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.baileyofbristol.co.uk"
MANUFACTURER = "Bailey"
MANUFACTURER_DISPLAY_NAME = "Bailey"

#: (range index path, label). The label is what a reviewer sees for `--range` selection;
#: the real `manufacturer_range` is read from each model page's own `Range` field (see
#: `RANGE_NAME_CORRECTIONS`), so the label here does not need to match FMLV's naming.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes/adamo", "Adamo"),
    ("motorhomes/alora", "Alora"),
    ("motorhomes/autograph", "Autograph"),
    ("campervan/endeavour", "Endeavour"),
    ("campervan/endurance", "Endurance"),
)

#: A range whose literal `Range` field disagrees with FMLV's own name for it — see the
#: module docstring. `Adamo` deliberately has no entry: the site's `XL-I`/`XL-T`/`XL-DL`
#: models are read as plain models of `Adamo`, per the requester's decision.
RANGE_NAME_CORRECTIONS: dict[str, str] = {
    "Autograph": "Autograph IV",
}

#: Bailey's own stated roof profile for a motorhome, mapped to FMLV's body type. Only the
#: value actually seen during the survey is mapped — an unmapped value is left unset and
#: narrated (`collect`), never guessed, since a wrong body type is worse than a visible gap.
_MOTORHOME_ROOF_PROFILES: dict[str, BodyType] = {
    "low profile": BodyType.COACH_BUILT_LOW_PROFILE,
}

#: A campervan taller than this is a high top — the roof line materially above the side
#: windows. Same threshold as every other adapter that needs it (`auto_trail.py`,
#: `chausson.py`), set by the NCC side from FMLV's own data.
HIGH_TOP_ABOVE_MM = 2300

#: One label's value: text immediately following the label's own `<div>...</div>` pair,
#: inside the next `col-6` value `<div>`. Both the label and the value may wrap an inner
#: `<span>` (Bailey does this for the two fields carrying a tooltip "more info" link, MRO
#: and the top-of-page "Payload" summary) — optional groups absorb that without needing a
#: second pattern.
def _is_blank(value: str) -> bool:
    """Whether a captured value is really empty once its unit/entity noise is discounted.

    Bailey's template repeats several labels — `Overall Height`, `Chassis`, `OTR Price` —
    in a top-of-page summary block that is sometimes left unfilled (or, for campervans,
    HTML-commented out entirely) ahead of the real "Technical specification" section
    further down the same page. An unfilled value still matches `_field`'s pattern, just
    with nothing between the unit symbol and the closing tag (`'m /'`, `'£'`), so a plain
    "did it match" check would stop at the empty one and never reach the real figure.
    """
    cleaned = re.sub(r"&prime;|&Prime;", "", value)
    cleaned = re.sub(r"\bm\b", "", cleaned)
    cleaned = re.sub(r"\bkg\b", "", cleaned)
    cleaned = re.sub(r"[\s/£]", "", cleaned)
    return cleaned == ""


def _field(html: str, label: str) -> str | None:
    """The first non-blank value of `label`, skipping any earlier unfilled occurrence."""
    pattern = re.compile(
        rf'{re.escape(label)}\s*(?:</span>)?\s*</div>\s*'
        rf'<div class="col-6[^"]*">\s*(?:<span[^>]*>)?\s*([^<]*)'
    )
    for match in pattern.finditer(html):
        value = match.group(1).strip()
        if not _is_blank(value):
            return value
    return None


def _metres_to_mm(raw: str | None) -> int | None:
    if raw is None:
        return None
    match = re.search(r"([\d.]+)\s*m\b", raw)
    return round(float(match.group(1)) * 1000) if match else None


def _kilograms(raw: str | None) -> int | None:
    """`'3500kg'` -> `3500`; `'3431.5kg'` -> `3432`.

    Weights are usually whole kilograms but not always — the Autograph IV 79-4F page
    gives MRO as `3431.5kg`. `[\\d,]+` alone (no decimal point) matched the `5` out of
    `.5kg` and silently returned a 5kg motorhome, so the decimal has to be captured too.
    """
    if raw is None:
        return None
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*kg", raw)
    return round(float(match.group(1).replace(",", ""))) if match else None


def _leading_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    match = re.search(r"\d+", raw)
    return int(match.group(0)) if match else None


#: The OTR price, from the page's own hero banner rather than the "Technical
#: specification" section's `OTR Price` row — which is HTML-commented out on every
#: campervan page checked, alongside an equally dead `RRP Price` row, both inside markup
#: whose own tooltip text still says "your new Bailey **caravan**": a block copy-pasted
#: from the caravan template and disabled rather than adapted. The hero banner's price is
#: present and correct on both motorhomes and campervans.
_HERO_PRICE = re.compile(r'<small class="t3 mr-2">OTR</small>\s*£\s*([\d,]+)')


def _hero_price(html: str) -> int | None:
    match = _HERO_PRICE.search(html)
    return int(match.group(1).replace(",", "")) if match else None


def find_model_urls(range_html: str, path: str) -> list[str]:
    """Every model page linked from one range's overview page, in document order.

    Scoped to `path` (e.g. `motorhomes/adamo`) rather than matched loosely, so a link to
    a different range elsewhere on the page (nav, footer, "you might also like") is never
    picked up.
    """
    pattern = re.compile(rf'href="({re.escape(BASE_URL)}/{re.escape(path)}/[a-z0-9-]+/)"')
    seen: dict[str, None] = {}
    for match in pattern.finditer(range_html):
        seen.setdefault(match.group(1), None)
    return list(seen)


@dataclass(frozen=True)
class BaileyProduct:
    """One model, as read from its own page."""

    range_label: str
    model: str
    is_campervan: bool
    base_vehicle_manufacturer: str | None = None
    roof_profile_published: str | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    mh_payload_kilograms_published: int | None = None
    mh_passenger_seats_inc_driver: int | None = None
    berths: int | None = None
    rrp_pounds: int | None = None

    @property
    def label(self) -> str:
        return f"{self.range_label} {self.model}"

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Bailey publish payload directly; this is only a fallback if that row is missing."""
        if self.mh_payload_kilograms_published is not None:
            return self.mh_payload_kilograms_published
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms

    @property
    def body_type(self) -> BodyType | None:
        """Bailey's own classification, mapped rather than inferred — see the module docstring."""
        if self.is_campervan:
            if self.mh_height_mm is None:
                return None
            return (
                BodyType.CAMPERVAN_HIGH_TOP
                if self.mh_height_mm > HIGH_TOP_ABOVE_MM
                else BodyType.CAMPERVAN
            )
        if self.roof_profile_published is None:
            return None
        return _MOTORHOME_ROOF_PROFILES.get(self.roof_profile_published.lower())


def _reconciles(product: BaileyProduct) -> bool:
    """Whether Bailey's own three weights agree: payload == MTPLM - MRO.

    Bailey publish payload directly, so unlike most adapters this is a check on Bailey's
    own arithmetic and this parser's reading of it together, rather than a defence against
    a column-attribution failure — there is only one vehicle on the page, so there is no
    column to misattribute. A product missing any of the three passes, having nothing to
    contradict.

    1kg of slack is allowed: a few models (Autograph IV 79-4F) publish MRO and payload to
    one decimal place, and `_kilograms` rounds each independently, so the two roundings
    can differ by 1kg even when the underlying figures are exactly consistent.
    """
    mtplm, mro, payload = (
        product.mtplm_kilograms,
        product.mro_kilograms,
        product.mh_payload_kilograms_published,
    )
    if mtplm is None or mro is None or payload is None:
        return True
    return abs((mtplm - mro) - payload) <= 1


def parse_model_page(html: str, *, is_campervan: bool) -> BaileyProduct | None:
    """One model's data, from its own page's "Technical specification" section.

    `None` if the page carries no `Range`/`Model` fields at all — a template change worth
    raising loudly rather than silently producing an empty product.
    """
    range_published = _field(html, "Range")
    model = _field(html, "Model")
    if not range_published or not model:
        return None

    range_label = RANGE_NAME_CORRECTIONS.get(range_published, range_published)
    # "Cab" is the actual base vehicle brand ("Peugeot Cab (Graphite)"); "Chassis" can
    # instead name an add-on subframe system bolted onto that cab ("AL-KO AMC" on
    # Autograph IV) which is not a vehicle manufacturer at all. "Cab" is tried first for
    # exactly this reason — Chassis is the fallback, used only where Cab is absent
    # (campervans have neither, and use "Base Vehicle" instead).
    base_vehicle = (
        _field(html, "Base Vehicle") or _field(html, "Cab") or _field(html, "Chassis")
    )

    return BaileyProduct(
        range_label=range_label,
        model=model,
        is_campervan=is_campervan,
        base_vehicle_manufacturer=base_vehicle.split()[0] if base_vehicle else None,
        roof_profile_published=_field(html, "Roof Profile"),
        mh_length_mm=_metres_to_mm(_field(html, "Overall Body Length")),
        mh_width_mm=_metres_to_mm(_field(html, "Max Width Vehicle with Mirrors Folded")),
        mh_height_mm=_metres_to_mm(_field(html, "Overall Height")),
        mtplm_kilograms=_kilograms(_field(html, "MTPLM")),
        mro_kilograms=_kilograms(_field(html, "MRO")),
        mh_payload_kilograms_published=_kilograms(_field(html, "Total User Payload")),
        mh_passenger_seats_inc_driver=_leading_int(_field(html, "Designated Travelling Seats")),
        berths=_leading_int(_field(html, "Berths")),
        rrp_pounds=_hero_price(html),
    )


def _build_extracted_motorhome(product: BaileyProduct, source_url: str) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        rrp_pounds=product.rrp_pounds,
        mro_kilograms=product.mro_kilograms,
        mtplm_kilograms=product.mtplm_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=product.mh_length_mm,
        mh_width_mm=product.mh_width_mm,
        mh_height_mm=product.mh_height_mm,
        mh_passenger_seats_inc_driver=product.mh_passenger_seats_inc_driver,
        berths=product.berths,
        body_type=product.body_type,
    )

    provenance: dict[str, Provenance] = {}

    def record(field: str, snippet: str) -> None:
        provenance[field] = Provenance(source_url=source_url, snippet=f"{product.label} — {snippet}")

    if product.rrp_pounds is not None:
        record("rrp_pounds", f"OTR price, from the page's own hero banner: £{product.rrp_pounds:,}")
    if product.mh_length_mm is not None:
        record("mh_length_mm", f"Overall Body Length: {product.mh_length_mm / 1000:.3f}m")
    if product.mh_width_mm is not None:
        record("mh_width_mm", f"Max Width Vehicle with Mirrors Folded: {product.mh_width_mm / 1000:.3f}m")
    if product.mh_height_mm is not None:
        record("mh_height_mm", f"Overall Height: {product.mh_height_mm / 1000:.3f}m")
    if product.mtplm_kilograms is not None:
        record("mtplm_kilograms", f"MTPLM: {product.mtplm_kilograms}kg")
    if product.mro_kilograms is not None:
        record("mro_kilograms", f"MRO: {product.mro_kilograms}kg")
    if product.mh_payload_kilograms_published is not None:
        record("mh_payload_kilograms", f"Total User Payload: {product.mh_payload_kilograms_published}kg")
    elif product.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"derived: {product.mtplm_kilograms}kg MTPLM - {product.mro_kilograms}kg MRO "
            f"= {product.mh_payload_kilograms}kg (Total User Payload row was not found)",
        )
    if product.mh_passenger_seats_inc_driver is not None:
        record("mh_passenger_seats_inc_driver", f"Designated Travelling Seats: {product.mh_passenger_seats_inc_driver}")
    if product.berths is not None:
        record("berths", f"Berths: {product.berths}")
    if product.base_vehicle_manufacturer is not None:
        record("base_vehicle_manufacturer", f"Chassis/Base Vehicle: {product.base_vehicle_manufacturer}")
    if product.body_type is not None:
        basis = (
            f"Overall Height {product.mh_height_mm}mm"
            if product.is_campervan
            else f"Roof Profile '{product.roof_profile_published}'"
        )
        record("body_type", f"{basis}")
    record(
        "manufacturer_range",
        f"Range '{product.range_label}' read from the page's own field"
        + (
            f" (site states '{product.range_label}' verbatim)"
            if product.range_label not in RANGE_NAME_CORRECTIONS.values()
            else " (corrected from the site's own name against the real FMLV export)"
        ),
    )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Bailey needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every current Bailey motorhome and campervan model.

    One fetch per range overview page, then one fetch per model page it links. A model
    page that can't be fetched or carries no `Range`/`Model` fields is narrated and
    skipped rather than raised — one broken page shouldn't cost the other twenty-one.
    """
    results: list[ExtractedMotorhome] = []

    for path, label in ranges:
        is_campervan = path.startswith("campervan/")
        range_url = f"{BASE_URL}/{path}/"
        on_progress(f"[{label}] fetching {range_url} ...")
        overview = http.fetch(range_url)
        if overview.status_code != 200:
            on_progress(f"[{label}] SKIPPED: {range_url} returned {overview.status_code}")
            continue

        overview_html = overview.file_path.read_text(encoding="utf-8", errors="replace")
        model_urls = find_model_urls(overview_html, path)
        if not model_urls:
            on_progress(f"[{label}] SKIPPED: no model pages linked from {range_url}")
            continue
        on_progress(f"[{label}] {len(model_urls)} model page(s) linked")

        for model_url in model_urls:
            page = http.fetch(model_url)
            if page.status_code != 200:
                on_progress(f"[{label}] SKIPPED: {model_url} returned {page.status_code}")
                continue

            html = page.file_path.read_text(encoding="utf-8", errors="replace")
            product = parse_model_page(html, is_campervan=is_campervan)
            if product is None:
                on_progress(
                    f"[{label}] SKIPPED: no Range/Model fields found on {model_url}"
                )
                continue

            if not _reconciles(product):
                on_progress(
                    f"[{product.label}] SKIPPED: published payload "
                    f"({product.mh_payload_kilograms_published}kg) does not equal "
                    f"MTPLM ({product.mtplm_kilograms}kg) - MRO ({product.mro_kilograms}kg), "
                    f"so a figure may have been misread from {model_url}"
                )
                continue

            if product.rrp_pounds is None:
                on_progress(f"[{product.label}] WARNING: no OTR Price found, left blank")
            if product.body_type is None:
                basis = "Overall Height" if is_campervan else "Roof Profile"
                on_progress(
                    f"[{product.label}] WARNING: body type not known ({basis} did not "
                    f"resolve to a mapped value), left blank rather than guessed"
                )

            results.append(_build_extracted_motorhome(product, model_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
