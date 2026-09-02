"""Moto-Trek (moto-trek.co.uk) — the fourteenth adapter, campervans and coachbuilts.

See `docs/adapters/moto-trek.md` for the full write-up. Plain server-rendered
WordPress/Elementor, no JavaScript, and **one URL is one vehicle** — so like Bailey there
is no column to misalign in the usual sense. The risk here is a different one, and it is
worse, because the spec table is not a table at all:

    container 288a948                     <- the "Vehicle Specification" accordion panel
      container b284b60                   <- LABELS: n text-editor widgets
        "Berths" "Engine Size" "Overall Length" ... "Overall Height (Inc. Aerial)*"
      container 9b3642f                   <- VALUES: m text-editor widgets, m <= n
        "2" "2.0L 140BHP" "6.36m / 20’10”" ... "3500kg"

**Two parallel columns with no row element and nothing pairing them but position.** Label
*i* means value *i* and that is the only join. The columns are different lengths on every
page, because Dynamic Content for Elementor drops an empty widget rather than rendering it
blank — 15/13 on the Leisure-Treka EB, 12/10 on the ELD, 9/7 on the X-Cite, 5/5 on the
Pioneer. It drops the label *and* its value together for every field it controls, so the
surviving pairs stay in step; the label set itself therefore varies per model, and only the
ELD publishes `M.I.R.O` / `M.T.P.L.M` / `Maximum User Payload` at all.

**Only two labels are ever empty, which is what makes the alignment checkable.**
`Overall Width (Mirrors Folded)*` and `Overall Height (Inc. Aerial)*` appear on twelve of
the thirteen vehicle pages and are empty on all twelve; the Pioneer, which publishes no
width or height at all, carries neither. So the surplus is a **subset** of
`_ALWAYS_EMPTY_LABELS` (`surplus_is_expected`) rather than equal to it — requiring equality
silently dropped the Pioneer while this adapter was being written, which is the check's own
failure mode pointed the wrong way. What it really asserts is that no *data-bearing* label
runs past the end of the value column.

It also means the asterisked figures are already the base-vehicle ones. The ELD's own
handbook decodes the asterisk, which the site never does: "2.26m wide **with the mirrors
folded** / 2.64m tall **with the TV aerial stowed**".

**A real error on their site, and the arithmetic that proves the pairing is right.** The
Leisure-Treka ELD reads `Garage Length = 3160kg`. That looks exactly like a one-place shift,
but `3500 - 3160 = 340` holds as printed and any shift breaks it, and the value widget id
carrying it (`6aa2ced`) holds `2.59m` on the EB page. So Moto-Trek have typed the M.I.R.O
into their own Garage Length field. `SpecBlock.mismatches` catches it — a `Length` label
whose value is `kg` is not a length — and because it is *one* mismatch on an out-of-scope
field it is narrated and the product kept. **More than one mismatch drops the product**, on
the reasoning that a genuine column shift would break several pairs at once while a typo
breaks one. This is the check that covers a value missing from the *middle* of the column,
which the surplus check cannot see.

**Identity comes from a table, not from the page.** Moto-Trek's names do not mechanically
yield FMLV's `manufacturer_range` + `model` split: the Pioneer's page is titled just
"Pioneer" and never mentions the `IB` layout FMLV holds, "X-Cite EB Elite" has to lose its
trim to become `X-Cite` + `EB`, and `The Terrain` and `Tornado` repeat the range in the
model. See `VEHICLE_IDENTITIES`, which is checked against the real export.

**Two vehicles in the roster are deliberately not collected** — see `IGNORED_SLUGS`. One of
them, Cyclone 180S, is a braked trailer. The other, the Ford Custom Campervan, is branded
*Three Peaks* and is a separate NCC supplier with its own baseline, and its page carries no
spec block at all. The Tornado Transporter is filed under *Motorsport* and **is** collected,
because FMLV holds it as a current product; note its spec block is byte-identical to the
Leisure-Treka EB's except for berths, which `collect` narrates.

**Price is the website's headline figure**, `from £72495.00`, which is ex works plus VAT.
Moto-Trek's two withdrawn 2024 price lists (hidden in the media library, in no page and no
sitemap) restate identical net prices as an on-the-road `GRAND TOTAL`, +£400 flat. The rule
is to record the headline a buyer sees, so that FMLV and moto-trek.co.uk agree — requester,
27 August 2026. `POA` is not a price and never becomes zero.

Four vehicles are `POA`, and for those the run **narrates** the last figure Moto-Trek did
publish, with its date, from `LAST_PUBLISHED_PRICES` — so a reviewer entering a guide price
by hand has the manufacturer's own number rather than an estimate. It is never written to
`rrp_pounds`; asserting a withdrawn figure as collected is a different thing from a reviewer
choosing it knowingly.

**Seats are unpublished everywhere on this manufacturer** — the vehicle pages, the index
cards and the ELD handbook all decline to give a number — so `mh_passenger_seats_inc_driver`
is always left unset and narrated once per run.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://moto-trek.co.uk"
MANUFACTURER = "MOTO-TREK LIMITED"
MANUFACTURER_DISPLAY_NAME = "MOTO-TREK"

#: The complete leisure roster, and the only place the FMLV identity split is decided.
#:
#: Keyed by the site's own `/vehicle/<slug>/` slug. Values are `(manufacturer_range, model,
#: is_campervan)` exactly as the real export holds them — verified against
#: `Moto-Trek`'s export on 27 August 2026, where emitting these gives a 1.000 match on all
#: ten current products, so no rename is ever proposed.
#:
#: Three entries cannot be derived from the page and are the reason this table exists:
#:
#: * `pioneer` — the page is titled "Pioneer" and names no layout; FMLV holds model `IB`.
#: * `x-cite-*-elite` — "Elite" is a trim, not part of the model. FMLV holds `EB` and `G`.
#: * `the-terrain` and `tornado-transporter` — FMLV repeats the range in the model, which the
#:   product slug `moto-trek-the-terrain-the-terrain-peugeot` confirms is deliberate.
#:
#: `is_campervan` is the shape judgement, taken as declared per `docs/adapters/README.md`.
#: Every Leisure-Treka, the Terrain and the Tornado are Peugeot Boxer van conversions; the
#: Xploras, X-Cites, Euro-Treka and Pioneer are coachbuilts, and return no body type because
#: the site never says whether they are low-profile or over-cab.
#:
#: **The ELD is a van conversion too, and an earlier version of this table had it wrong.**
#: It looks like a coachbuilt sitting between its siblings — 2.26m wide against their 2.05m,
#: 2.64m tall against their 2.76m, and a 3160kg mass against their 2500kg. All three are
#: measurement conventions, not a different vehicle:
#:
#: * its own handbook says "2.26m wide **with the mirrors folded**", and 2260 − 2050 = 210mm
#:   is about 105mm per mirror, exactly what a folded van mirror adds;
#: * the same handbook says "2.64m tall **with the TV aerial stowed**", so the 120mm is an
#:   aerial;
#: * and the masses are different measurements — the siblings publish `Unladen Weight`,
#:   the ELD `M.I.R.O`, which its handbook defines as *including* habitation equipment, a
#:   90% gas tank, a full 70L of water and the hook-up cable.
#:
#: All four are 6.36m long on the same Boxer. FMLV holds it as `campervan_high_top` and that
#: is right — the requester queried the proposed correction and it did not survive.
VEHICLE_IDENTITIES: dict[str, tuple[str, str, bool]] = {
    "leisure-treka-rl": ("Leisure-Treka", "RL", True),
    "leisure-treka-eb": ("Leisure-Treka", "EB", True),
    "leisure-treka-eld": ("Leisure-Treka", "ELD", True),
    "the-terrain": ("The Terrain", "The Terrain", True),
    "xplora-fdb": ("Xplora", "FDB", False),
    "xplora-eld": ("Xplora", "ELD", False),
    "x-cite-eb-elite": ("X-Cite", "EB", False),
    "x-cite-g-elite": ("X-Cite", "G", False),
    "euro-treka-ib": ("Euro-Treka", "IB", False),
    "pioneer": ("Pioneer", "IB", False),
    "tornado-transporter": ("Tornado", "Tornado", True),
}

#: Slugs in the site's own navigation that are known and deliberately not collected, with
#: the reason, so the roster check reports only genuinely *new* vehicles.
IGNORED_SLUGS: dict[str, str] = {
    "cyclone-180s": (
        "a braked trailer, not a motor vehicle — galvanised steel chassis, lockable "
        "coupling, six fully braked wheels"
    ),
    "ford-custom-campervan": (
        "branded Three Peaks, a separate NCC supplier ('Three-Peaks Campers', "
        "manufacturer_id 210) with its own baseline export; its page also carries no spec "
        "block at all, so none of FMLV's figures for it are recoverable from this site"
    ),
}

#: The last price Moto-Trek published for each vehicle the site now marks `POA`, with the
#: date of the document it came from. `(pounds, document date)`.
#:
#: **Narrated only — never written to `rrp_pounds`.** A run must not assert a withdrawn
#: figure as though it had collected one, and the price rule is to record the manufacturer's
#: *headline website* price, which for these four does not exist. What this does is put the
#: number in front of the reviewer on the run page, so entering a guide price by hand is a
#: sourced decision rather than an estimate (requester, 27 August 2026).
#:
#: The figures are the `2024 Retail Price` column of `January-2024-Retail-Price-List.pdf` —
#: net plus VAT, which is the basis FMLV already holds. The October 2024 guide restates the
#: identical net prices on an on-the-road basis (+£400 flat: £153,215, £98,395 and £70,395),
#: and is deliberately not used, per the headline-price rule.
#:
#: **Two model years old, but not obviously stale:** all seven prices the site *still*
#: publishes are identical to this same list, to the pound — Moto-Trek have not moved a
#: published price since January 2024. Re-check when a newer list appears in the media
#: library (`/wp-json/wp/v2/media?mime_type=application/pdf`), which is where these hide.
#:
#: **All three now agree with FMLV**, which is the narration having done its job: the
#: requester corrected the Tornado in Nova on 27 August 2026 from £64,995 — a figure older
#: than anything on the site — to the £69,995 below, and the out-of-scope Three Peaks Ford
#: Camper from £63,995 to its own £75,995. So these entries are no longer flagging a
#: discrepancy; they exist for the Euro-Treka IB, which has no FMLV price at all until it is
#: uploaded, and to keep a figure in front of a reviewer if the site's `POA` ever outlives
#: what FMLV holds.
LAST_PUBLISHED_PRICES: dict[str, tuple[int, str]] = {
    "euro-treka-ib": (152_995, "January 2024"),
    "x-cite-eb-elite": (97_995, "January 2024"),
    "x-cite-g-elite": (97_995, "January 2024"),
    "tornado-transporter": (69_995, "January 2024"),
}

#: `(informational slug, label)`. The label is the FMLV `manufacturer_range`, so
#: `cli.baseline_scope`'s default match on that column is correct and no
#: `baseline_in_scope` hook is needed. The first element is *not* a fetch path: Moto-Trek's
#: own range index pages (`/leisure-treka/`, `/xplora/`, `/slideouts/`) cut across FMLV's
#: ranges — `/slideouts/` alone holds X-Cite, Euro-Treka, Pioneer and the Terrain — so the
#: selector filters the roster instead of choosing a URL.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = tuple(
    (label.lower().replace(" ", "-"), label)
    for label in dict.fromkeys(identity[0] for identity in VEHICLE_IDENTITIES.values())
)

#: The only labels ever seen with no value beside them, so the only ones a page's label
#: column may legitimately run past its value column by.
#:
#: **Twelve of the thirteen vehicle pages carry both, empty.** The Pioneer carries neither —
#: it publishes no width or height at all, and DCE drops these two along with
#: `Overall Width*` and `Overall Height*`. So the surplus is a *subset* of this tuple, not
#: always equal to it: an earlier version of this adapter required equality and silently
#: dropped the Pioneer, which is exactly the failure the check exists to prevent, pointed
#: the wrong way.
#:
#: The check still bites, because what it really asserts is that **no data-bearing label
#: runs past the value column** — the signature of the two columns having come out of step.
#: A value missing from the *middle* of the column slips past it untouched, which is what
#: `_type_mismatches` is for; the two checks cover different halves of the same risk.
_ALWAYS_EMPTY_LABELS: tuple[str, ...] = (
    "Overall Width (Mirrors Folded)*",
    "Overall Height (Inc. Aerial)*",
)

#: Every label seen across the 13 vehicle pages, mapped to `(Motorhome field or None, kind)`.
#:
#: `kind` is the type check, and it is applied to **every** pair including the out-of-scope
#: ones — a garage dimension carrying a `kg` value is evidence about the alignment of the
#: whole column, which is worth more than the garage dimension itself.
#:
#: The two mass labels are duplicated because the vocabulary is not consistent between
#: models: the ELD publishes `M.I.R.O`/`M.T.P.L.M`, everything else `Unladen Weight`/`Gross
#: Weight`, for the same two figures.
_FIELDS: dict[str, tuple[str | None, str]] = {
    "Berths": ("berths", "int"),
    "Engine Size": (None, "engine"),
    "Overall Length": ("mh_length_mm", "metres"),
    "Overall Width*": ("mh_width_mm", "metres"),
    "Overall Height*": ("mh_height_mm", "metres"),
    "Garage Length": (None, "metres"),
    "Garage Width": (None, "metres"),
    "Garage Height": (None, "metres"),
    "Living Area Length": (None, "metres"),
    "Living Area Width": (None, "metres"),
    "Living Area Height": (None, "metres"),
    "Unladen Weight": ("mro_kilograms", "kg"),
    "Gross Weight": ("mtplm_kilograms", "kg"),
    "M.I.R.O": ("mro_kilograms", "kg"),
    "M.T.P.L.M": ("mtplm_kilograms", "kg"),
    "Maximum User Payload": ("mh_payload_kilograms_published", "kg"),
    "Waste Water Capacity": (None, "litres"),
    "Overall Width (Mirrors Folded)*": (None, "metres"),
    "Overall Height (Inc. Aerial)*": (None, "metres"),
}

#: Base vehicle makes Moto-Trek actually name, from the warranty text ("Peugeot, Fiat &
#: Ford ... Mercedes and Iveco"). Matched against the first word of the "Cab and Body"
#: block so a template change cannot turn prose into a manufacturer name.
_BASE_VEHICLE_MAKES: frozenset[str] = frozenset(
    {"Peugeot", "Fiat", "Ford", "Mercedes", "Iveco"}
)

#: A campervan taller than this is a high top. Same threshold as every other adapter that
#: needs it, set by the NCC side. **It only ever separates `campervan` from
#: `campervan_high_top`** — it never promotes a coachbuilt, which is why it is reached only
#: inside the `is_campervan` branch of `MotoTrekProduct.body_type` (requester, 27 August
#: 2026: the X-Cite at 2870mm is simply a low-profile motorhome).
HIGH_TOP_ABOVE_MM = 2300

#: Inches of slack allowed between a cell's metric and imperial halves. Moto-Trek round the
#: imperial figure carelessly — the ELD's `6.36m / 20’9″` is 1.4" out and its
#: `2.64m / 8’6″` is 1.9" out — so this is a warning, never a reason to drop anything.
_IMPERIAL_TOLERANCE_INCHES = 3.0

_WIDGET_TEXT = re.compile(
    r'data-element_type="widget"[^>]*data-widget_type="text-editor[^"]*"[^>]*>'
    r'\s*<div class="elementor-widget-container">(.*?)</div>',
    re.S,
)
_DIV = re.compile(r"<div\b[^>]*>|</div>")
_CONTAINER_OPEN = re.compile(r'<div\b[^>]*data-element_type="container"[^>]*>')
_HEADING_TEXT = re.compile(r"<h[1-6][^>]*class=\"elementor-heading-title[^\"]*\"[^>]*>(.*?)</h[1-6]>", re.S)
_SPEC_PANEL_TITLE = "Vehicle Specification"


def _text(fragment: str) -> str:
    """Visible text of one widget's inner HTML, with entities resolved."""
    cleaned = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", fragment)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    for entity, char in (
        ("&#8217;", "’"), ("&#8216;", "‘"), ("&#8221;", "”"),
        ("&#8220;", "“"), ("&#8243;", "″"), ("&#8242;", "′"),
        ("&#8211;", "–"), ("&#8212;", "—"), ("&nbsp;", " "),
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#038;", "&"),
    ):
        cleaned = cleaned.replace(entity, char)
    return re.sub(r"\s+", " ", cleaned).strip()


def _panel_span(html: str) -> tuple[int, int] | None:
    """Byte span of the "Vehicle Specification" accordion panel's own container.

    Bounding the widget scan to this one container is what keeps the equipment blobs out:
    "Cab and Body", "Optional Extras" and the warranty text are sibling accordion panels
    full of `text-editor` widgets, and their headings are not consistently named across
    models (`Cab and Body` on the Leisure-Trekas, `CAB & BODY` on the Xploras), so they
    cannot be used as a reliable end marker. The container's own closing tag can.
    """
    title = html.find(_SPEC_PANEL_TITLE)
    if title < 0:
        return None
    opening = _CONTAINER_OPEN.search(html, title)
    if opening is None:
        return None

    depth = 0
    for match in _DIV.finditer(html, opening.start()):
        if match.group(0) == "</div>":
            depth -= 1
            if depth == 0:
                return (opening.end(), match.start())
        else:
            depth += 1
    return None


@dataclass(frozen=True)
class SpecBlock:
    """One vehicle's label/value pairs, plus what was wrong with them."""

    pairs: tuple[tuple[str, str], ...]
    #: Labels running past the end of the value column. Always `_ALWAYS_EMPTY_LABELS`.
    surplus: tuple[str, ...]
    #: `(label, value, expected kind)` for every pair whose value is the wrong type.
    mismatches: tuple[tuple[str, str, str], ...]


def surplus_is_expected(block: SpecBlock) -> bool:
    """Whether every label running past the value column is one that is always empty.

    A subset test rather than an equality test — see `_ALWAYS_EMPTY_LABELS` for why the
    Pioneer, which publishes no width or height, has no surplus at all.
    """
    return all(label in _ALWAYS_EMPTY_LABELS for label in block.surplus)


def _value_kind(value: str) -> str:
    """The kind a value's own text says it is, independent of the label beside it."""
    if re.fullmatch(r"\d{3,5}\s*kg", value, re.I):
        return "kg"
    if re.match(r"^\d+(\.\d+)?\s*m\b", value):
        return "metres"
    if re.fullmatch(r"\d+\s*L", value, re.I):
        return "litres"
    if re.search(r"BHP", value, re.I):
        return "engine"
    if re.fullmatch(r"\d+(\s*/\s*\d+)?", value):
        return "int"
    return "unknown"


def parse_spec_block(html: str) -> SpecBlock | None:
    """Pair up the spec panel's two columns, or `None` if it has no recognisable labels.

    `None` covers the Ford Custom Campervan, whose page has a "Vehicle Specification"
    heading and then a prose bullet list rather than the two-column block — and would
    cover a template change, which is worth narrating loudly rather than half-parsing.

    The labels are the *leading* run of recognised labels and the values are what follows,
    which works because the two columns are separate sibling containers rendered in that
    order. A page whose surplus holds a label that is not one of `_ALWAYS_EMPTY_LABELS`
    returns a `SpecBlock` with that surplus recorded, and `collect` drops it — the pairing
    cannot be trusted once a data-bearing label has run past the end of the value column.
    """
    span = _panel_span(html)
    if span is None:
        return None

    texts = [_text(m.group(1)) for m in _WIDGET_TEXT.finditer(html, span[0], span[1])]

    labels: list[str] = []
    for text in texts:
        if text in _FIELDS:
            labels.append(text)
        elif labels:
            break
        # Anything before the first label (a stray heading widget) is skipped.
    if not labels:
        return None

    values = [text for text in texts[len(labels) :] if text][: len(labels)]

    pairs = tuple(zip(labels, values, strict=False))
    mismatches = tuple(
        (label, value, _FIELDS[label][1])
        for label, value in pairs
        if _value_kind(value) != _FIELDS[label][1]
    )
    return SpecBlock(pairs=pairs, surplus=tuple(labels[len(values) :]), mismatches=mismatches)


def _metres_to_mm(raw: str) -> int | None:
    """`'6.36m / 20’10”'` -> `6360`. Reads the metric half only; see `_imperial_inches`."""
    match = re.match(r"^(\d+(?:\.\d+)?)\s*m\b", raw)
    return round(float(match.group(1)) * 1000) if match else None


def _kilograms(raw: str) -> int | None:
    match = re.match(r"^(\d+(?:\.\d+)?)\s*kg", raw, re.I)
    return round(float(match.group(1))) if match else None


def _lower_int(raw: str) -> int | None:
    """`'4/6'` -> `4`, per the lower-figure berths rule; `'2'` -> `2`."""
    numbers = re.findall(r"\d+", raw)
    return min(int(number) for number in numbers) if numbers else None


def _imperial_inches(raw: str) -> float | None:
    """Total inches from a cell's imperial half, or `None` where it publishes none.

    Feet and inches are marked with curly quotes (`20’10”`), and one cell separates the two
    halves with a stray left single quote instead of a slash (`2.17m ‘ 7’1″` on four pages),
    which is why the metric half is parsed by anchoring at the start of the string rather
    than by splitting on the separator.
    """
    match = re.search(r"(\d+)\s*[’′']\s*(\d+)\s*[″”\"]", raw)
    return int(match.group(1)) * 12 + int(match.group(2)) if match else None


def _imperial_disagreements(pairs: tuple[tuple[str, str], ...]) -> list[str]:
    """Cells whose two published halves disagree by more than the tolerance."""
    out: list[str] = []
    for label, value in pairs:
        millimetres, inches = _metres_to_mm(value), _imperial_inches(value)
        if millimetres is None or inches is None:
            continue
        if abs(millimetres / 25.4 - inches) > _IMPERIAL_TOLERANCE_INCHES:
            out.append(f"{label} {value} (metric is {millimetres / 25.4:.1f}in)")
    return out


def _base_vehicle(html: str) -> str | None:
    """The make from the "Cab and Body" block's first line, or `None`.

    Absent on the Pioneer and the Tornado, both of which FMLV already holds a base vehicle
    for. The field is out of collection scope, so a gap costs nothing on a matched product
    — but it is a `schema.REQUIRED` field, so filling it matters on a new one.
    """
    match = re.search(r"Cab\s*(?:and|&(?:amp;)?)\s*Body(.{0,80})", html, re.I | re.S)
    if match is None:
        return None
    for word in _text(match.group(1)).split():
        if word in _BASE_VEHICLE_MAKES:
            return fmlv_base_vehicle(word)
    return None


def _headline_price(html: str) -> tuple[int | None, bool]:
    """`(price, is_poa)` from the page's own headline heading.

    Anchored on the heading widget, not on a loose `£` search: the Leisure-Treka body copy
    repeats the figure as `£72,495.00` with a thousands comma, and reading that instead
    would work right up until a model whose prose price is out of step with its headline.
    """
    for match in _HEADING_TEXT.finditer(html):
        text = _text(match.group(1))
        if text.upper() == "POA":
            return (None, True)
        priced = re.fullmatch(r"(?:from\s*)?£\s*([\d,]+(?:\.\d+)?)", text, re.I)
        if priced:
            return (round(float(priced.group(1).replace(",", ""))), False)
    return (None, False)


@dataclass(frozen=True)
class MotoTrekProduct:
    """One vehicle, as read from its own page."""

    slug: str
    manufacturer_range: str
    model: str
    is_campervan: bool
    base_vehicle_manufacturer: str | None = None
    berths: int | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mro_kilograms: int | None = None
    mtplm_kilograms: int | None = None
    mh_payload_kilograms_published: int | None = None
    rrp_pounds: int | None = None
    is_poa: bool = False

    @property
    def label(self) -> str:
        return f"{self.manufacturer_range} {self.model}"

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload, published only by the ELD and otherwise derived from the two masses.

        Deriving rather than leaving it blank matches what FMLV already holds — the Tornado
        and The Terrain carry 1000kg against 3500 - 2500 — and leaving it alone would be
        worse than either updating or blanking it: the Leisure-Treka EB and RL would keep a
        340kg payload beside a 1000kg gap, an inherited figure that is now arithmetically
        impossible.
        """
        if self.mh_payload_kilograms_published is not None:
            return self.mh_payload_kilograms_published
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms

    @property
    def body_type(self) -> BodyType | None:
        """Campervan-or-coachbuilt first, from the declared shape; only then the height.

        Out of collection scope, so this is never compared or proposed — but it is recorded
        for the one product that gets created fresh. Coachbuilts return `None` rather than
        guessing between low-profile and over-cab, which the site never states: FMLV's own
        values for them are right and, being out of scope, are left untouched.
        """
        if not self.is_campervan:
            return None
        if self.mh_height_mm is None:
            return None
        return (
            BodyType.CAMPERVAN_HIGH_TOP
            if self.mh_height_mm > HIGH_TOP_ABOVE_MM
            else BodyType.CAMPERVAN
        )


def _reconciles(product: MotoTrekProduct) -> tuple[bool, str]:
    """Whether the masses are consistent enough to propose, and why not if they aren't.

    Two checks. The published payload identity fires only on the Leisure-Treka ELD, the one
    model giving all three figures — but it is the check that proved the whole column
    pairing, so it stays. `MRO < MTPLM` applies to everything and would catch a swap of the
    two, which the type check cannot see because both are `kg`.
    """
    mro, mtplm = product.mro_kilograms, product.mtplm_kilograms
    payload = product.mh_payload_kilograms_published

    if mro is not None and mtplm is not None and mro >= mtplm:
        return (False, f"mass in running order ({mro}kg) is not less than MTPLM ({mtplm}kg)")
    if None not in (mro, mtplm, payload) and abs((mtplm - mro) - payload) > 1:  # type: ignore[operator]
        return (
            False,
            f"published payload ({payload}kg) does not equal MTPLM ({mtplm}kg) - "
            f"MRO ({mro}kg)",
        )
    return (True, "")


def parse_vehicle_page(html: str, slug: str) -> tuple[MotoTrekProduct | None, SpecBlock | None]:
    """One vehicle, from its own page. `(None, block)` where the block cannot be trusted."""
    identity = VEHICLE_IDENTITIES.get(slug)
    if identity is None:
        return (None, None)
    manufacturer_range, model, is_campervan = identity

    block = parse_spec_block(html)
    if block is None or not surplus_is_expected(block):
        return (None, block)

    read: dict[str, int | None] = {}
    for label, value in block.pairs:
        field, kind = _FIELDS[label]
        if field is None or _value_kind(value) != kind:
            continue
        if kind == "metres":
            read[field] = _metres_to_mm(value)
        elif kind == "kg":
            read[field] = _kilograms(value)
        elif kind == "int":
            read[field] = _lower_int(value)

    price, is_poa = _headline_price(html)
    return (
        MotoTrekProduct(
            slug=slug,
            manufacturer_range=manufacturer_range,
            model=model,
            is_campervan=is_campervan,
            base_vehicle_manufacturer=_base_vehicle(html),
            berths=read.get("berths"),
            mh_length_mm=read.get("mh_length_mm"),
            mh_width_mm=read.get("mh_width_mm"),
            mh_height_mm=read.get("mh_height_mm"),
            mro_kilograms=read.get("mro_kilograms"),
            mtplm_kilograms=read.get("mtplm_kilograms"),
            mh_payload_kilograms_published=read.get("mh_payload_kilograms_published"),
            rrp_pounds=price,
            is_poa=is_poa,
        ),
        block,
    )


# --------------------------------------------------------------------------- #
# The roster, and the cards that cross-check it
# --------------------------------------------------------------------------- #

_NAV_VEHICLE_LINK = re.compile(r'href="(?:' + re.escape(BASE_URL) + r')?/vehicle/([a-z0-9-]+)/"')


def find_roster(html: str) -> list[str]:
    """Every `/vehicle/<slug>/` the page links, in document order, deduplicated.

    Read from the navigation mega-menu, which is on every page and is the only source that
    lists all 13 vehicles — `/motorhomes/` shows the 11 leisure ones and omits the Tornado
    and the Cyclone, which sit under its *Motorsport* and *Trailers* headings instead. A
    stated roster beats a heuristic, and it also means a fourteenth vehicle appearing gets
    reported rather than silently missed.
    """
    seen: dict[str, None] = {}
    for match in _NAV_VEHICLE_LINK.finditer(html):
        seen.setdefault(match.group(1), None)
    return list(seen)


@dataclass(frozen=True)
class IndexCard:
    """One vehicle's card on `/motorhomes/`: the cross-check, not the source."""

    slug: str
    berths: int | None
    mtplm_kilograms: int | None
    rrp_pounds: int | None


def parse_index_cards(html: str) -> dict[str, IndexCard]:
    """The `/motorhomes/` cards, keyed by slug.

    Each card republishes berths, gross weight and price — the only cross-document
    redundancy this manufacturer offers, and it covers 3 of the 13 in-scope fields. The two
    figures are identified by their own Font Awesome icons (`fa-bed`, `fa-weight-hanging`)
    rather than by position, so a card gaining a third icon-list cannot silently shift them.
    """
    cards: dict[str, IndexCard] = {}
    anchors = [
        (match.start(), match.group(1))
        for match in re.finditer(
            r'<h3[^>]*class="elementor-heading-title[^"]*"[^>]*>\s*<a href="'
            + re.escape(BASE_URL)
            + r'/vehicle/([a-z0-9-]+)/"',
            html,
        )
    ]
    for index, (start, slug) in enumerate(anchors):
        end = anchors[index + 1][0] if index + 1 < len(anchors) else len(html)
        card = html[start:end]

        def icon_value(icon: str, scope: str = card) -> str | None:
            match = re.search(
                rf'fa-{icon}"[^>]*>.*?<span class="elementor-icon-list-text">(.*?)</span>',
                scope,
                re.S,
            )
            return _text(match.group(1)) if match else None

        berths_raw, weight_raw = icon_value("bed"), icon_value("weight-hanging")
        price_match = re.search(
            r'<h4[^>]*class="elementor-heading-title[^"]*"[^>]*>(.*?)</h4>', card, re.S
        )
        price_text = _text(price_match.group(1)) if price_match else ""
        priced = re.fullmatch(r"(?:from\s*)?£\s*([\d,]+(?:\.\d+)?)", price_text, re.I)

        cards[slug] = IndexCard(
            slug=slug,
            berths=_lower_int(berths_raw) if berths_raw else None,
            mtplm_kilograms=_kilograms(weight_raw) if weight_raw else None,
            rrp_pounds=round(float(priced.group(1).replace(",", ""))) if priced else None,
        )
    return cards


def card_disagreements(product: MotoTrekProduct, card: IndexCard) -> list[str]:
    """Where a vehicle's page and its index card disagree on the three shared fields."""
    out: list[str] = []
    for name, page_value, card_value in (
        ("berths", product.berths, card.berths),
        ("MTPLM", product.mtplm_kilograms, card.mtplm_kilograms),
        ("price", product.rrp_pounds, card.rrp_pounds),
    ):
        if page_value is not None and card_value is not None and page_value != card_value:
            out.append(f"{name} (page {page_value}, card {card_value})")
    return out


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(
    product: MotoTrekProduct, source_url: str, block: SpecBlock
) -> ExtractedMotorhome:
    published = dict(block.pairs)
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
        berths=product.berths,
        body_type=product.body_type,
    )

    provenance: dict[str, Provenance] = {}

    def record(field: str, snippet: str) -> None:
        provenance[field] = Provenance(
            source_url=source_url, snippet=f"{product.label} — {snippet}"
        )

    def label_for(field: str) -> str | None:
        """The label whose value fed `field` on *this* page — the vocabulary varies."""
        for label, (mapped, _kind) in _FIELDS.items():
            if mapped == field and label in published:
                return label
        return None

    for field in ("mh_length_mm", "mh_width_mm", "mh_height_mm"):
        label = label_for(field)
        if label is not None and getattr(product, field) is not None:
            record(field, f"{label}: {published[label]}")
    for field in ("mro_kilograms", "mtplm_kilograms"):
        label = label_for(field)
        if label is not None and getattr(product, field) is not None:
            record(field, f"{label}: {published[label]}")
    if product.berths is not None:
        raw = published.get("Berths", str(product.berths))
        note = (
            f"Berths: {raw} — the lower figure of a range is recorded"
            if raw != str(product.berths)
            else f"Berths: {raw}"
        )
        record("berths", note)
    if product.mh_payload_kilograms_published is not None:
        record(
            "mh_payload_kilograms",
            f"Maximum User Payload: {published['Maximum User Payload']} "
            f"(and {product.mtplm_kilograms} - {product.mro_kilograms} agrees)",
        )
    elif product.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"derived: {product.mtplm_kilograms}kg MTPLM - {product.mro_kilograms}kg MRO "
            f"= {product.mh_payload_kilograms}kg. Moto-Trek publish a payload figure on the "
            f"Leisure-Treka ELD only",
        )
    if product.rrp_pounds is not None:
        record(
            "rrp_pounds",
            f"headline price on the vehicle's own page: £{product.rrp_pounds:,}. Ex works "
            f"plus VAT — the basis their withdrawn 2024 price list used, and the figure a "
            f"buyer sees on moto-trek.co.uk",
        )
    if product.base_vehicle_manufacturer is not None:
        record(
            "base_vehicle_manufacturer",
            f"first make named in the 'Cab and Body' list: {product.base_vehicle_manufacturer}",
        )
    if product.body_type is not None:
        record(
            "body_type",
            f"a van conversion by shape, and {product.mh_height_mm}mm is above the "
            f"{HIGH_TOP_ABOVE_MM}mm high-top threshold",
        )

    # Both halves of the identity, recorded together. `model` has no other route to a
    # reviewer: `compare_fields` walks only fields carrying provenance, and the in-scope
    # missing-field check fires only where nothing at all was found, so a model read but
    # left without provenance is neither compared nor reported.
    record(
        "manufacturer_range",
        f"'{product.manufacturer_range}', the range FMLV holds for this vehicle. The site "
        f"markets it under its own groupings — Slide-Outs, Camper, Motorsport — which cut "
        f"across FMLV's ranges. Paired with the model below; accept or reject both together",
    )
    record(
        "model",
        f"'{product.model}'. The site's own page title is not the model: it carries the "
        f"trim ('Elite') or omits the layout code entirely (the Pioneer never states 'IB'), "
        f"so this comes from the FMLV export. Paired with the range above",
    )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — plain HTML throughout; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect Moto-Trek's leisure vehicles: one index fetch, then one per vehicle.

    The index is fetched for two reasons — its navigation is the only complete roster, and
    its cards are the only cross-check on berths, gross weight and price. A vehicle page
    that cannot be fetched, or whose two spec columns no longer pair, is narrated and
    skipped rather than raised; only an unreachable index is fatal, since without it there
    is no roster.
    """
    wanted = {label for _slug, label in ranges}
    index_url = f"{BASE_URL}/motorhomes/"
    on_progress(f"fetching the roster from {index_url} ...")
    index = http.fetch(index_url)
    if index.status_code != 200:
        msg = f"{index_url} returned {index.status_code}, so the roster cannot be read"
        raise RuntimeError(msg)

    index_html = index.file_path.read_text(encoding="utf-8", errors="replace")
    roster = find_roster(index_html)
    cards = parse_index_cards(index_html)
    on_progress(
        f"{len(roster)} vehicle(s) in the site navigation, {len(cards)} card(s) on the index"
    )

    for slug in roster:
        if slug in IGNORED_SLUGS:
            on_progress(f"[{slug}] not collected: {IGNORED_SLUGS[slug]}")
        elif slug not in VEHICLE_IDENTITIES:
            on_progress(
                f"[{slug}] WARNING: in the site navigation but not in VEHICLE_IDENTITIES — "
                f"a new vehicle, or one renamed. Not collected; add it to the table after "
                f"checking what FMLV calls it"
            )
    for slug in VEHICLE_IDENTITIES:
        if slug not in roster:
            on_progress(
                f"[{slug}] WARNING: expected but no longer linked from the site navigation "
                f"— it may have been discontinued"
            )

    selected = [
        slug
        for slug in VEHICLE_IDENTITIES
        if slug in roster and VEHICLE_IDENTITIES[slug][0] in wanted
    ]
    results: list[ExtractedMotorhome] = []

    for slug in selected:
        url = f"{BASE_URL}/vehicle/{slug}/"
        page = http.fetch(url)
        if page.status_code != 200:
            on_progress(f"[{slug}] SKIPPED: {url} returned {page.status_code}")
            continue

        html = page.file_path.read_text(encoding="utf-8", errors="replace")
        product, block = parse_vehicle_page(html, slug)

        if product is None:
            if block is None:
                on_progress(
                    f"[{slug}] SKIPPED: no two-column spec block found on {url} — the "
                    f"page may have been rebuilt"
                )
            else:
                unexpected = [
                    label for label in block.surplus if label not in _ALWAYS_EMPTY_LABELS
                ]
                on_progress(
                    f"[{slug}] SKIPPED: {unexpected} carry no value, and they are labels "
                    f"that normally do. The two spec columns pair by position only, so a "
                    f"data-bearing label running past the end of the value column means "
                    f"nothing on this page can be trusted"
                )
            continue

        if len(block.mismatches) > 1:
            on_progress(
                f"[{product.label}] SKIPPED: {len(block.mismatches)} values are the wrong "
                f"type for their labels ("
                + "; ".join(f"{label}={value!r}, expected {kind}" for label, value, kind in block.mismatches)
                + f"), so the two columns have probably shifted on {url}"
            )
            continue
        for label, value, kind in block.mismatches:
            on_progress(
                f"[{product.label}] WARNING: '{label}' holds {value!r}, which is not a "
                f"{kind} — a data-entry error on Moto-Trek's own page. That field is left "
                f"blank; the rest of the page reconciles and is kept"
            )

        reconciled, why_not = _reconciles(product)
        if not reconciled:
            on_progress(f"[{product.label}] SKIPPED: {why_not}, so a figure may be misread from {url}")
            continue

        for disagreement in _imperial_disagreements(block.pairs):
            on_progress(
                f"[{product.label}] WARNING: metric and imperial halves disagree on "
                f"{disagreement} — Moto-Trek round the imperial figure loosely; the metric "
                f"half is the one recorded"
            )
        card = cards.get(slug)
        if card is not None:
            for disagreement in card_disagreements(product, card):
                on_progress(
                    f"[{product.label}] WARNING: the index card disagrees on {disagreement}; "
                    f"the vehicle's own page is recorded"
                )
        elif slug not in IGNORED_SLUGS:
            on_progress(
                f"[{product.label}] WARNING: no index card, so berths, gross weight and "
                f"price could not be cross-checked"
            )

        if product.is_poa:
            message = (
                f"[{product.label}] WARNING: price is POA, so none is proposed. FMLV's held "
                f"figure, if any, stays as it is"
            )
            last = LAST_PUBLISHED_PRICES.get(slug)
            if last is not None:
                amount, published = last
                message += (
                    f". Moto-Trek's last published price for it was £{amount:,}, from their "
                    f"{published} retail price list — ex works plus VAT, the same basis FMLV "
                    f"holds. Every price they still publish is unchanged from that list, so "
                    f"it is the best guide figure available; enter it by hand if you want one"
                )
            on_progress(message)
        elif product.rrp_pounds is None:
            on_progress(f"[{product.label}] WARNING: no headline price found, left blank")

        results.append(_build_extracted_motorhome(product, url, block))

    on_progress(
        "seats: Moto-Trek publish no seat or seatbelt count anywhere — not on the vehicle "
        "pages, not on the index cards, not in the one model handbook they publish — so "
        "mh_passenger_seats_inc_driver is left unset on every product"
    )
    on_progress(f"{len(results)} product(s) collected")
    return results
