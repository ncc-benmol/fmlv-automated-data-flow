"""Elddis (elddis.co.uk) — the thirteenth adapter, motorhomes and campervans.

See `docs/adapters/elddis.md` for the full write-up. Structurally this is the safest
source surveyed: **one URL is one vehicle**, plain server-rendered HTML, no JavaScript,
no PDF anywhere on the site, and every number sits in a labelled `Label: value` block
that the page heads "Technical Specification". There are no columns, so the
misattribution failure that dominates the PDF adapters cannot happen here.

    Technical Specification
    Year: 2026
    Model: Whirlwind GT 155
    Base Vehicle: Peugeot X250 Boxer Euro 6E Engine Motorhome Chassis
    Number of Berths : 4
    Number of Seat Belts: 4
    Exterior Length: 7373mm/24'2"
    Overall Width Including Wing Mirrors: 2678mm/8'9"
    Overall Body Width: 2239mm/7'4"
    Overall Height Including Aerial: 2925mm/9'7"
    Mass in Running Order (MIRO): 2926kgs/57.60cwt
    Maximum User Payload: 530kgs/10.43cwt
    M.T.P.L.M: 3500kgs/68.89cwt
    NOTES

The field mapping is not inferred — it was checked against the 29 products FMLV already
holds and agrees on berths, seats, MRO, MTPLM, length and width **29 of 29**, payload
28 of 29 and height 27 of 29. In particular `Overall Body Width` is the width FMLV holds,
not `Overall Width Including Wing Mirrors`, which the base-vehicle rule in
`docs/adapters/README.md` would have chosen anyway. `Maximum Headroom` and `Interior
Width` are decoys — both are always present, and `Maximum Headroom` is 2080 on every
motorhome.

**The self-check is a band, not an equality.** Elddis publishes MIRO, MTPLM *and*
payload, and its own footnote declares the reason they do not simply subtract:

    Note 9: A MIRO tolerance of +1.5% is permitted as per the NCC COP 304/402
    regulation to account for build variance

Most models publish `payload = MTPLM - MIRO * 1.015`; a minority publish the plain
`MTPLM - MIRO`. Both are legitimate, so `_reconciles` accepts the closed interval between
them — see its docstring. A consequence worth knowing: `validation._validate_payload`
tests the exact equality, so it warns on most Elddis products. That is **pre-existing, not
caused here** — FMLV's own baseline already carries the tolerance-adjusted figures.

**Name collisions, flagged by the requester (2026-08-21) and worse than they look.**
"Whirlwind" names a motorhome range, a campervan range *and* a caravan range; "Autoquest"
names one motorhome range and three campervan ranges. Two consequences:

* Layout numbers repeat across ranges — `105`-`196+` appear in Whirlwind GT, Whirlwind GT
  Evolve *and* Autoquest APEX — so nothing can be keyed on the model half alone.
* `diff/matching.py` scores `Whirlwind GT 155` against `Whirlwind GT Evolve 155` at 0.750
  and `Avalon 250` against `Avalon Evolve 250` at 0.667, both above its 0.5 accept
  threshold and above Adria's documented *good* match. The Evolve ranges are all new
  products whose most plausible wrong partner is already in the baseline.

**FMLV folds campervans into the motorhome range**, which the website does not suggest and
only the real export revealed. `Autoquest Apex` holds both the 8 motorhomes (`105`…) and
the 4 campervans (`CV20`…); the site's separate `Autoquest CV` range collapses to range
`Autoquest`. See `_SEGMENT_RANGES`. The site's `196+` is `196P` in FMLV — getting that
wrong costs twice, since the product reads as new *and* its baseline row reads as gone.

**Price is the published headline, as-is** (decision from the NCC side, 2026-08-21). Elddis
labels it "OTR" and then charges a £1,690 OTR fee on top, so the true on-the-road figure is
£1,690 higher and is never printed as a single number; FMLV's existing rows hold the
headline *minus* £1,690. Recording the headline therefore proposes a +£1,690 change on
every matched product on the first run. That is the intended outcome, not a parse error.

**The three Whirlwind GTV campervans are the trap** and every defence below exists for
them: dimensions in metres not millimetres, masses with thousands separators, height given
`Excluding Aerial` where every other model gives `Including Aerial`, berths and seats as
prose, and weights split four ways (Fixed Roof / Pop Top x Manual / Automatic) with the
model name and a seat count embedded in the label on the 563. The base vehicle is
Fixed Roof + Manual, falling back to Automatic where no manual figure exists — the GTV 554
is automatic-only. Selected that way the self-check passes exactly.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://elddis.co.uk"
MANUFACTURER = "Elddis (EHG UK)"
MANUFACTURER_DISPLAY_NAME = "Elddis"

SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

#: The two listing pages that carry every layout as a card. Used only as a free
#: completeness cross-check against the sitemap — `docs/adapters/README.md`'s "no single
#: menu is a complete roster" rule, which here has a happy answer: the sitemap and these
#: two pages agreed exactly (34 and 15) during the survey.
SPECIFICATION_INDEXES: tuple[tuple[str, str], ...] = (
    ("motorhome-specification", "motorhome"),
    ("campervan-specification", "campervan"),
)

#: (URL segment, label) per range. The label is what a reviewer picks with `--range`; the
#: real `manufacturer_range` comes from `_SEGMENT_RANGES`, so labels here follow the site's
#: own marketing names rather than FMLV's.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes/whirlwind-gt", "Whirlwind GT"),
    ("motorhomes/whirlwind-gt-evolve", "Whirlwind GT Evolve"),
    ("motorhomes/autoquest-apex", "Autoquest APEX"),
    ("motorhomes/avalon", "Avalon"),
    ("motorhomes/avalon-evolve", "Avalon Evolve"),
    ("campervans/autoquest-cv", "Autoquest CV"),
    ("campervans/autoquest-cv-evolve", "Autoquest CV Evolve"),
    ("campervans/autoquest-apex-cv", "Autoquest APEX CV"),
    ("campervans/whirlwind-gtv", "Whirlwind GTV"),
)

#: URL segment -> the `manufacturer_range` FMLV actually holds. Read off the real export,
#: not the website: FMLV files the Apex campervans under the *motorhome* range
#: `Autoquest Apex` (distinguished only by the `CV` prefix on the model half), and the
#: site's `Autoquest CV` range under the bare name `Autoquest`. Emitting the site's own
#: names would have proposed a rename on all 12 Apex products and orphaned the four
#: `Autoquest` campervans.
_SEGMENT_RANGES: dict[str, str] = {
    "whirlwind-gt": "Whirlwind GT",
    "whirlwind-gt-evolve": "Whirlwind GT Evolve",
    "autoquest-apex": "Autoquest Apex",
    "avalon": "Avalon",
    "avalon-evolve": "Avalon Evolve",
    "autoquest-cv": "Autoquest",
    "autoquest-cv-evolve": "Autoquest Evolve",
    "autoquest-apex-cv": "Autoquest Apex",
    "whirlwind-gtv": "Whirlwind GTV",
}

#: A campervan taller than this is a high top — the roof line materially above the side
#: windows. The same threshold as `auto_trail.py`, `bailey.py`, `chausson.py` and
#: `etrusco.py`, set by the NCC side from FMLV's own data. It reproduces FMLV's existing
#: value on all 8 matched Elddis campervans, which is the reason for reusing it rather
#: than inventing a brand-specific figure: every Elddis van is 2610mm or 2670mm, so all of
#: them are high tops on this rule.
HIGH_TOP_ABOVE_MM = 2300

#: Elddis's only motorhome body shape. The site never uses the words "low profile",
#: "coach built", "high top" or "A-class" — zero occurrences on any page — so this cannot
#: be read from its wording. FMLV holds all 21 of its current Elddis motorhomes as low
#: profile across Whirlwind GT, Autoquest Apex and Avalon, and the range contains no
#: over-cab-bed or A-class model. The 29 "overcab pod" mentions on the site are a styling
#: feature, not a bed, and appear on ranges FMLV already files as low profile.
_MOTORHOME_BODY_TYPE = BodyType.COACH_BUILT_LOW_PROFILE

#: A pop-top fitted **as standard**, which does change the body type. Only the three CV80
#: layouts say this, and they say it twice ("comes with a pop-top with an opening
#: Skylight", "adds a pop-top roof to create a flexible 4-berth campervan under 6m");
#: CV20, CV40 and CV60 never mention a pop-top at all. Contrast the Whirlwind GTVs, which
#: offer one as a *cost option* ("All models are available as a pop-top 5 berth version")
#: and are therefore excluded by `_offers_pop_top_variant` below — per the base-vehicle
#: rule in `docs/adapters/README.md`, the word after the feature decides it.
_STANDARD_POP_TOP = re.compile(r"comes with a pop[-\s]?top", re.IGNORECASE)

#: The hero price, from the `<h1>` that carries the model name. Anchored on `</h1>` so it
#: cannot pick up the option prices further down (`Gearbox - £3,246`, `Colour - £847`,
#: `Tow Bar - £706`, all in `<h2>`), the `£1,690` OTR footnote, or the enquiry form's
#: client-side configuration summary, which repeats the same figure lower on the page.
_HERO_PRICE = re.compile(r"</h1>\s*<span[^>]*>\s*£\s*([\d,]+)")

#: The model page's own spec section, and the footnotes that end it. Motorhomes head these
#: `Technical Specification` / `NOTES`; campervans use `Technical Specifications` /
#: `Notes`. Matching the motorhome spelling exactly finds 34 of 49 products and silently
#: drops every campervan — which is how this was found.
_SPEC_HEADING = re.compile(r"^Technical Specifications?$", re.IGNORECASE)
_NOTES_HEADING = re.compile(r"^Notes?$", re.IGNORECASE)
#: A numbered footnote, in case the `NOTES` heading itself ever goes missing — without
#: this the notes would be absorbed as spec fields labelled `Note 1`, `Note 2`, …
_NOTE_LINE = re.compile(r"^Note\s*\d+\s*[:.]", re.IGNORECASE)

#: The trailing layout code in the site's own model name, which is the `model` half FMLV
#: holds: `Autoquest APEX 105` -> `105`, `Autoquest Evolve CV20` -> `CV20`,
#: `Whirlwind GTV 554` -> `554`. `196+` becomes `196P` (see `_model_code`).
_MODEL_CODE = re.compile(r"(CV\d+|\d+\+?)$", re.IGNORECASE)

#: A model page under one range, e.g. `/motorhomes/whirlwind-gt/whirlwind-gt-155`. Three
#: segments exactly — the two-segment form is the range's own overview page.
_MODEL_PATH = re.compile(
    r"^https://elddis\.co\.uk/(motorhomes|campervans)/([^/]+)/([^/]+)$"
)


def _text_lines(html: str) -> list[str]:
    """The page's visible text, one line per element, scripts and styles removed.

    The spec block is rendered as one element per `Label: value` line, so flattening tags
    to newlines recovers it exactly. Scripts have to go first: the enquiry form's Alpine
    component embeds JSON that contains its own colon-separated keys, and the option
    blocks embed escaped markup that would otherwise read as spec lines.
    """
    body = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body, flags=re.IGNORECASE)
    body = unescape(re.sub(r"<[^>]+>", "\n", body))
    return [line.strip() for line in body.split("\n") if line.strip()]


def spec_fields(lines: list[str]) -> dict[str, str]:
    """The `Label: value` pairs of one page's technical specification block.

    Keyed on the label verbatim, first occurrence winning. Stops at the footnotes, so the
    `Note 1: …` prose never lands in here, and never reaches past the block into the
    options and enquiry sections below it.
    """
    start: int | None = None
    for index, line in enumerate(lines):
        if _SPEC_HEADING.match(line):
            start = index
            break
    if start is None:
        return {}

    fields: dict[str, str] = {}
    for line in lines[start + 1 :]:
        if _NOTES_HEADING.match(line) or _NOTE_LINE.match(line):
            break
        label, separator, value = line.partition(":")
        if not separator:
            continue
        label, value = label.strip(), value.strip()
        # `Number of Berths :` carries a space before its colon on every page, so the
        # label is stripped rather than matched raw.
        if label and value and label not in fields:
            fields[label] = value
    return fields


def _exact(fields: dict[str, str], *labels: str) -> str | None:
    """The value of the first of `labels` present, compared case-insensitively.

    Exact matching matters more than it looks. `Maximum User Payload` must not pick up
    `Mass Available for Optional Payload`, and `Overall Height Including Aerial` must not
    pick up `Overall Height Including Pop Top` — which is the raised-roof figure, and on
    the GTVs sits two lines away from the one wanted.
    """
    lowered = {label.lower(): value for label, value in fields.items()}
    for label in labels:
        value = lowered.get(label.lower())
        if value:
            return value
    return None


def _matching(
    fields: dict[str, str], include: tuple[str, ...], exclude: tuple[str, ...] = ()
) -> str | None:
    """The first value whose label contains every `include` term and no `exclude` term.

    Only the Whirlwind GTVs need this. Their weight labels are unique per model and per
    variant — `Mass in running order - (Manual) - Fixed Roof` on the 560,
    `GTV 563 (4-seats) Fixed Roof - Mass in running order - (Manual) - Fixed Roof` on the
    563 — so no fixed set of labels covers them, but "mentions fixed roof, does not
    mention pop top" does.
    """
    for label, value in fields.items():
        lowered = label.lower()
        if all(term in lowered for term in include) and not any(
            term in lowered for term in exclude
        ):
            return value
    return None


def _base_variant(fields: dict[str, str], *what: str) -> str | None:
    """One weight for the *base* vehicle: fixed roof, manual gearbox.

    Falls back to the automatic figure where no manual one exists — the GTV 554 is
    `Automatic as standard` and publishes nothing else — and then to any fixed-roof figure,
    for the 554's `Maximum User Payload - Fixed Roof`, which is qualified by roof only.
    Pop-top figures are always excluded: the raised roof is a cost option on every model
    that offers one, so the fixed-roof vehicle is the base vehicle.
    """
    return (
        _matching(fields, (*what, "fixed roof", "(manual)"), ("pop top",))
        or _matching(fields, (*what, "fixed roof", "(automatic)"), ("pop top",))
        or _matching(fields, (*what, "fixed roof"), ("pop top",))
    )


def _millimetres(raw: str | None) -> int | None:
    """`"7373mm/24'2\\""` -> 7373; `"5.99m"` -> 5990; `"2.05m"` -> 2050.

    Two units are in play. Every model but the three Whirlwind GTVs publishes millimetres
    with an imperial equivalent after a slash; the GTVs publish metres to two decimal
    places, so their dimensions are only good to the nearest 10mm and no other document
    gives them more precisely. Millimetres are tried first, and the metre pattern refuses
    to match the `m` of `mm`, so a stray reading of `7373mm` as 7.373km cannot happen.

    The imperial half must never be parsed — note it contains digits *and* a quote
    character (`24'2"`), so it survives naive cleaning.
    """
    if raw is None:
        return None
    cleaned = raw.replace(",", "")
    match = re.search(r"([\d.]+)\s*mm", cleaned)
    if match:
        return round(float(match.group(1)))
    match = re.search(r"([\d.]+)\s*m(?![m\w])", cleaned)
    return round(float(match.group(1)) * 1000) if match else None


def _kilograms(raw: str | None) -> int | None:
    """`"2926kgs/57.60cwt"` -> 2926; `"2,710kg"` -> 2710; `"194.5kgs"` -> 194.

    The GTVs comma-separate their masses where nothing else does, and a few models publish
    a half-kilogram, so both have to be tolerated. The `cwt` half is never parsed.

    Rounding is Python's banker's rounding, so an exact `.5` goes to even — the same as
    `bailey.py`'s equivalent, and the reason `_reconciles` allows 1kg of slack. No field
    FMLV records is currently published to half a kilogram (only `Mass Available for
    Optional Payload` is, and that has no FMLV column), so this affects nothing today.
    """
    if raw is None:
        return None
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*kgs?", raw)
    return round(float(match.group(1).replace(",", ""))) if match else None


def _leading_int(raw: str | None) -> int | None:
    """The first integer in a value, which is the base-vehicle figure for a range.

    `docs/adapters/README.md` takes the lower figure of a berth or seat range, because the
    higher one needs options — and Elddis writes the fixed-roof (base) figure first every
    time: `Fixed Roof 3 Berth or Pop Top Roof 5 Berth` -> 3, and the GTV 563's
    `Fixed Roof (Manual or Automatic) 4 seats or Pop Top (Manual or Automatic) 3 seats`
    -> 4. Note the second of those is the case where the base figure is the *higher* one,
    so "take the lower number" would have been wrong; "take the fixed-roof one" is the
    rule, and reading order expresses it.
    """
    if raw is None:
        return None
    match = re.search(r"\d+", raw)
    return int(match.group(0)) if match else None


def _model_code(site_model_name: str) -> str | None:
    """The `model` half FMLV holds, from the site's own `Model:` field.

    `196+` becomes `196P`, which is what the export contains for both the Autoquest Apex
    and Whirlwind GT layouts of that name. Beyond matching the baseline, this matters
    because `diff/matching.py` tokenizes letters and digits only: the `+` is discarded, so
    `Whirlwind GT 196+` and `Whirlwind GT 196` reduce to the same token bag and the two
    genuinely different vehicles become indistinguishable to the matcher.
    """
    match = _MODEL_CODE.search(site_model_name.strip())
    if match is None:
        return None
    return match.group(1).upper().replace("+", "P")


def _offers_pop_top_variant(fields: dict[str, str]) -> bool:
    """Whether the spec block prices the pop-top as an alternative to the fixed roof.

    True for the Whirlwind GTVs, which publish a whole parallel set of weights and an
    `Overall Height Including Pop Top` for it. That makes the pop-top a variant of the
    vehicle rather than part of it, so the fixed-roof figures are the base vehicle and the
    body type keeps its fixed-roof value.
    """
    return any("pop top" in label.lower() for label in fields)


@dataclass(frozen=True)
class ElddisProduct:
    """One model, as read from its own page."""

    manufacturer_range: str
    model: str
    site_model_name: str
    is_campervan: bool
    year: int | None = None
    base_vehicle_published: str | None = None
    pop_top_standard: bool = False
    pop_top_optional: bool = False
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    mh_payload_kilograms: int | None = None
    mh_passenger_seats_inc_driver: int | None = None
    berths: int | None = None
    rrp_pounds: int | None = None

    @property
    def label(self) -> str:
        return f"{self.manufacturer_range} {self.model}"

    @property
    def base_vehicle_manufacturer(self) -> str | None:
        """`"Peugeot X250 Boxer Euro 6E Engine Motorhome Chassis"` -> `"Peugeot"`.

        The bare marque is what FMLV holds — `Fiat` on 39 rows, `Peugeot` on 38.
        """
        if not self.base_vehicle_published:
            return None
        first = self.base_vehicle_published.split()
        return first[0] if first else None

    @property
    def body_type(self) -> BodyType | None:
        """FMLV's body type, from the baseline for motorhomes and the height for vans.

        Reproduces the baseline exactly on all 8 matched campervans: every Elddis van is
        above `HIGH_TOP_ABOVE_MM`, and only the CV80s carry a standard pop-top.
        """
        if not self.is_campervan:
            return _MOTORHOME_BODY_TYPE
        if self.mh_height_mm is None:
            # The missing-data rule: an unknown height leaves this blank rather than
            # assuming a high top.
            return None
        high_top = self.mh_height_mm > HIGH_TOP_ABOVE_MM
        if self.pop_top_standard:
            return (
                BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF
                if high_top
                else BodyType.CAMPERVAN_ELEVATING_ROOF
            )
        return BodyType.CAMPERVAN_HIGH_TOP if high_top else BodyType.CAMPERVAN


def _reconciles(product: ElddisProduct) -> bool:
    """Whether Elddis's three published masses agree, within its own stated tolerance.

    The check is the closed interval

        MTPLM - MIRO * 1.015   <=   payload   <=   MTPLM - MIRO

    because both ends occur in the real data. The upper end is the plain subtraction; the
    lower applies the +1.5% MIRO tolerance the page's own footnote declares ("A MIRO
    tolerance of +1.5% is permitted as per the NCC COP 304/402 regulation"). Most models
    sit on the lower bound, a minority — Avalon 250 and all three GTVs — on the upper, and
    an equality test against either alone rejects roughly half the range.

    This is a real check even though there is no column to misalign: it ties three
    separately-located labels together, so a value picked up from a neighbouring row
    cannot pass. On the GTVs it also confirms the fixed-roof/manual variant was selected
    consistently across all three masses — mixing a pop-top MIRO with a fixed-roof MTPLM
    fails it by exactly the 160kg the raised roof weighs.

    A product missing any of the three passes, having nothing to contradict. 1kg of slack
    absorbs independent rounding of the three figures.
    """
    mtplm, mro, payload = (
        product.mtplm_kilograms,
        product.mro_kilograms,
        product.mh_payload_kilograms,
    )
    if mtplm is None or mro is None or payload is None:
        return True
    return (mtplm - mro * 1.015) - 1 <= payload <= (mtplm - mro) + 1


def find_model_urls(sitemap_xml: str, segment: str, vehicle_type: str) -> list[str]:
    """Every model page for one range, from `sitemap.xml`, in document order.

    The sitemap is the roster. `docs/adapters/README.md` prefers it because no single menu
    has been complete on any manufacturer surveyed; Elddis is the pleasant case where it
    agrees with the navigation, but taking it from here still means a layout added without
    a menu link is found, and it costs one fetch for all nine ranges.

    Scoped to `<vehicle_type>/<segment>/` and to three path segments exactly, so a range's
    own overview page is not mistaken for a model.
    """
    urls: dict[str, None] = {}
    for match in re.finditer(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap_xml):
        parts = _MODEL_PATH.match(match.group(1))
        if parts and parts.group(1) == vehicle_type and parts.group(2) == segment:
            urls.setdefault(match.group(1), None)
    return list(urls)


def count_index_cards(index_html: str) -> int:
    """How many layouts one `*-specification` page lists, for a completeness check.

    Each card prints its price as `£NN,NNN OTR`, once per layout, and nothing else on the
    page uses that form — the OTR-charge footnote writes `£1,690 RRP`. So counting these is
    counting layouts, and it is a second opinion on the sitemap's roster for two fetches.
    """
    return len(re.findall(r"£[\d,]+\s*OTR", index_html))


def parse_model_page(
    html: str, *, segment: str, is_campervan: bool
) -> ElddisProduct | None:
    """One model's data, from its own page's technical specification block.

    `None` if the block is absent or carries no usable `Model:` field — a template change
    worth narrating loudly rather than silently emitting an empty product.
    """
    lines = _text_lines(html)
    fields = spec_fields(lines)
    if not fields:
        return None

    site_model_name = _exact(fields, "Model")
    if not site_model_name:
        return None
    model = _model_code(site_model_name)
    if model is None:
        return None

    manufacturer_range = _SEGMENT_RANGES.get(segment)
    if manufacturer_range is None:
        return None

    pop_top_optional = _offers_pop_top_variant(fields)
    # A standard pop-top is only claimed in the page's own prose, so the whole page is
    # searched — but never where the spec block prices the pop-top as an alternative,
    # which makes it an option no matter how the marketing copy phrases it.
    pop_top_standard = not pop_top_optional and bool(_STANDARD_POP_TOP.search(html))

    return ElddisProduct(
        manufacturer_range=manufacturer_range,
        model=model,
        site_model_name=site_model_name,
        is_campervan=is_campervan,
        year=_leading_int(_exact(fields, "Year")),
        base_vehicle_published=_exact(fields, "Base Vehicle"),
        pop_top_standard=pop_top_standard,
        pop_top_optional=pop_top_optional,
        mh_length_mm=_millimetres(_exact(fields, "Exterior Length")),
        mh_width_mm=_millimetres(_exact(fields, "Overall Body Width")),
        mh_height_mm=_millimetres(
            _exact(
                fields,
                "Overall Height Including Aerial",
                "Overall Height Excluding Aerial",
            )
        ),
        mtplm_kilograms=_kilograms(
            _exact(fields, "M.T.P.L.M")
            or _matching(fields, ("m.t.p.l.m", "fixed roof"), ("pop top",))
        ),
        mro_kilograms=_kilograms(
            _exact(fields, "Mass in Running Order (MIRO)")
            or _base_variant(fields, "mass in running order")
        ),
        mh_payload_kilograms=_kilograms(
            _exact(fields, "Maximum User Payload")
            or _base_variant(fields, "maximum user payload")
        ),
        mh_passenger_seats_inc_driver=_leading_int(
            _exact(fields, "Number of Seat Belts")
        ),
        berths=_leading_int(_exact(fields, "Number of Berths")),
        rrp_pounds=_hero_price(html),
    )


def _hero_price(html: str) -> int | None:
    match = _HERO_PRICE.search(html)
    return int(match.group(1).replace(",", "")) if match else None


def _build_extracted_motorhome(
    product: ElddisProduct, source_url: str
) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.manufacturer_range,
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
        provenance[field] = Provenance(
            source_url=source_url, snippet=f"{product.site_model_name} — {snippet}"
        )

    if product.rrp_pounds is not None:
        record(
            "rrp_pounds",
            f"£{product.rrp_pounds:,} as published beside the model name. Elddis labels "
            f"this 'OTR' but charges the £1,690 on-the-road fee (delivery, registration, "
            f"PDI) on top, so the figure a buyer pays is £{product.rrp_pounds + 1690:,}. "
            f"Recorded as published, per the NCC decision of 2026-08-21",
        )
    if product.berths is not None:
        record("berths", f"Number of Berths: {product.berths}")
    if product.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            f"Number of Seat Belts: {product.mh_passenger_seats_inc_driver}",
        )
    if product.mh_length_mm is not None:
        record("mh_length_mm", f"Exterior Length: {product.mh_length_mm}mm")
    if product.mh_width_mm is not None:
        record(
            "mh_width_mm",
            f"Overall Body Width: {product.mh_width_mm}mm — the mirrors-excluded figure, "
            f"per the base-vehicle rule; the page also gives a wider "
            f"'Including Wing Mirrors' width",
        )
    if product.mh_height_mm is not None:
        record("mh_height_mm", f"Overall Height: {product.mh_height_mm}mm")
    if product.mtplm_kilograms is not None:
        record("mtplm_kilograms", f"M.T.P.L.M: {product.mtplm_kilograms}kg")
    if product.mro_kilograms is not None:
        record(
            "mro_kilograms", f"Mass in Running Order (MIRO): {product.mro_kilograms}kg"
        )
    if product.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"Maximum User Payload: {product.mh_payload_kilograms}kg as published. Note "
            f"this is usually less than MTPLM - MIRO, because Elddis applies the +1.5% "
            f"MIRO tolerance its own footnotes cite from NCC COP 304/402",
        )
    if product.base_vehicle_manufacturer is not None:
        record(
            "base_vehicle_manufacturer",
            f"Base Vehicle: {product.base_vehicle_published}",
        )
    if product.body_type is not None:
        if product.is_campervan:
            basis = f"Overall Height {product.mh_height_mm}mm"
            if product.pop_top_standard:
                basis += ", with a pop-top fitted as standard"
            elif product.pop_top_optional:
                basis += (
                    "; the pop-top is a cost option offering extra berths, so per the "
                    "base-vehicle rule it does not change the body type"
                )
        else:
            basis = (
                "Elddis publishes no body class, and FMLV holds every current Elddis "
                "motorhome as coach built low profile"
            )
        record("body_type", basis)

    # Both halves of the identity, recorded together — the Bailey lesson in
    # `docs/adapters/README.md`. Accepting a range rename without the matching model
    # rename writes back a corrupted name, and `model` is invisible to both the field
    # comparison and the missing-field check unless it has provenance of its own.
    record(
        "manufacturer_range",
        f"range '{product.manufacturer_range}', from the real FMLV export rather than "
        f"the site, which markets this vehicle as '{product.site_model_name}'. FMLV files "
        f"campervans under the same range as the motorhomes they share a name with. "
        f"Paired with the model below — accept or reject both together",
    )
    record(
        "model",
        f"model '{product.model}', the layout code from the site's own "
        f"'{product.site_model_name}'"
        + (
            " (the site writes this '+', FMLV writes 'P')"
            if product.model.endswith("P") and product.site_model_name.endswith("+")
            else ""
        )
        + ". Paired with the range above: together they name this vehicle",
    )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — no JavaScript needed; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every current Elddis motorhome and campervan.

    One fetch for the sitemap, one per model page it lists, and two for the specification
    index pages that cross-check the roster. A model page that cannot be fetched or parsed
    is narrated and skipped rather than raised — one broken page should not cost the other
    forty-eight — but an unreachable sitemap raises, since without it there is no roster
    at all and collecting nothing would look like a discontinued brand.
    """
    on_progress(f"fetching the roster from {SITEMAP_URL} ...")
    sitemap = http.fetch(SITEMAP_URL)
    if sitemap.status_code != 200:
        message = f"{SITEMAP_URL} returned {sitemap.status_code}; no roster to collect"
        raise RuntimeError(message)
    sitemap_xml = sitemap.file_path.read_text(encoding="utf-8", errors="replace")

    results: list[ExtractedMotorhome] = []
    expected_by_type: dict[str, int] = {"motorhome": 0, "campervan": 0}

    for path, label in ranges:
        vehicle_type_plural, _, segment = path.partition("/")
        is_campervan = vehicle_type_plural == "campervans"
        vehicle_type = "campervan" if is_campervan else "motorhome"

        model_urls = find_model_urls(sitemap_xml, segment, vehicle_type_plural)
        if not model_urls:
            on_progress(f"[{label}] SKIPPED: no model pages for '{segment}' in the sitemap")
            continue
        expected_by_type[vehicle_type] += len(model_urls)
        on_progress(f"[{label}] {len(model_urls)} model page(s) in the sitemap")

        collected_here = 0
        for model_url in model_urls:
            page = http.fetch(model_url)
            if page.status_code != 200:
                on_progress(f"[{label}] SKIPPED: {model_url} returned {page.status_code}")
                continue

            html = page.file_path.read_text(encoding="utf-8", errors="replace")
            product = parse_model_page(
                html, segment=segment, is_campervan=is_campervan
            )
            if product is None:
                on_progress(
                    f"[{label}] SKIPPED: no usable technical specification block on "
                    f"{model_url}"
                )
                continue

            if not _reconciles(product):
                on_progress(
                    f"[{product.label}] SKIPPED: published payload "
                    f"({product.mh_payload_kilograms}kg) is outside the band implied by "
                    f"MTPLM {product.mtplm_kilograms}kg and MIRO {product.mro_kilograms}kg "
                    f"(expected {product.mtplm_kilograms - round(product.mro_kilograms * 1.015)}"
                    f"-{product.mtplm_kilograms - product.mro_kilograms}kg), so a mass may "
                    f"have been misread from {model_url}"
                )
                continue

            if product.rrp_pounds is None:
                on_progress(f"[{product.label}] WARNING: no price found, left blank")
            if product.body_type is None:
                on_progress(
                    f"[{product.label}] WARNING: body type not known (no usable height), "
                    f"left blank rather than guessed"
                )

            results.append(_build_extracted_motorhome(product, model_url))
            collected_here += 1

        if collected_here != len(model_urls):
            on_progress(
                f"[{label}] WARNING: collected {collected_here} of "
                f"{len(model_urls)} model page(s) listed in the sitemap"
            )

    _cross_check_roster(http, expected_by_type, ranges, on_progress)

    on_progress(f"{len(results)} product(s) collected")
    return results


def _ranges_by_vehicle_type(ranges: tuple[tuple[str, str], ...]) -> dict[str, int]:
    """How many ranges of each vehicle type a given range selection covers."""
    counts = {"motorhome": 0, "campervan": 0}
    for path, _ in ranges:
        counts["campervan" if path.startswith("campervans/") else "motorhome"] += 1
    return counts


def _cross_check_roster(
    http: Fetcher,
    expected_by_type: dict[str, int],
    ranges: tuple[tuple[str, str], ...],
    on_progress: Callable[[str], None],
) -> None:
    """Compare the sitemap's roster against the specification index pages.

    A free second opinion, and the thing that would catch a range quietly dropping out of
    the sitemap. Only checked for a vehicle type whose ranges were **all** requested: a
    `--range` run legitimately collects a subset, and comparing three Whirlwind GTVs
    against the campervan index's fifteen cards reports a mismatch that is not one. The
    comparison must therefore be against `ranges` as actually passed, not against
    `DEFAULT_RANGES` — getting that wrong warned on every single-range run.

    Never fatal: a failed cross-check means the check is broken, not necessarily the
    roster.
    """
    requested = _ranges_by_vehicle_type(ranges)
    available = _ranges_by_vehicle_type(DEFAULT_RANGES)

    for index_path, vehicle_type in SPECIFICATION_INDEXES:
        expected = expected_by_type.get(vehicle_type, 0)
        if not expected:
            continue
        if requested[vehicle_type] != available[vehicle_type]:
            on_progress(
                f"NOTE: skipping the {vehicle_type} roster cross-check — this run covers "
                f"{requested[vehicle_type]} of {available[vehicle_type]} {vehicle_type} "
                f"range(s), so {index_path}'s full listing is not a fair comparison"
            )
            continue

        url = f"{BASE_URL}/{index_path}"
        index = http.fetch(url)
        if index.status_code != 200:
            on_progress(
                f"NOTE: could not cross-check the {vehicle_type} roster — {url} "
                f"returned {index.status_code}"
            )
            continue
        listed = count_index_cards(
            index.file_path.read_text(encoding="utf-8", errors="replace")
        )
        if listed == expected:
            on_progress(
                f"roster cross-check: {expected} {vehicle_type}(s) in both the sitemap "
                f"and {index_path}"
            )
        else:
            on_progress(
                f"WARNING: roster mismatch for {vehicle_type}s — the sitemap lists "
                f"{expected} but {index_path} shows {listed}. One of the two is stale, so "
                f"a layout may be missing from this run"
            )
