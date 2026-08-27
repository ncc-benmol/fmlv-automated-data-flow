"""Auto-Trail (auto-trail.co.uk) — the sixth adapter, motorhomes and campervans.

See `docs/adapters/auto-trail.md` for the full write-up. Auto-Trail is the cleanest
source surveyed. Every range publishes a "Website Tech Spec" PDF that gives each model a
run of whole pages to itself, with the model name repeated as a running header:

    EXPEDITION COACHBUILT C63
    Sleeps 4
    Total seats 4
    Seatbelts 4 (inc. driver)
    Length 6338mm
    Width (excl. door mirrors) 2373mm
    Height 3060mm
    ...
    Max. gross weight (with 3650kgs no cost option) 3500/3650kg
    Max. gross train weight (with 3650kg upgrade MGTW increases to 4900kg) 4750/4900kg
    Mass in running order 2960kg
    Max. towing weight 1250kg

There are no side-by-side columns anywhere, so the column-misalignment failure that
dominates `morelo.py`, `swift.py` and `sunlight.py` — and that defeated Rimor's
catalogue outright — does not arise. Attribution is free: a number is inside exactly one
model's block or it is nowhere.

Two ranges are both called **Expedition** — a coachbuilt motorhome range and a campervan
range — and nothing in a model's own name separates `EXPEDITION 68` from
`EXPEDITION COACHBUILT C73`. The range therefore always comes from *which document the
model was read out of*, never from the model name. See `DEFAULT_RANGES`.

Price comes from a second source, and is the one join this adapter makes. Auto-Trail's
price and options list PDF is a rasterised image — the whole of page 2 extracts to four
text runs, none of them a price — but each **range page** carries a `Price from` figure
per model in plain HTML. Rendering the price list as images and reading it confirmed that
this website figure is exactly the price list's `ON THE ROAD PRICE` column, on ten of ten
models across two ranges, which is the basis FMLV's guide price records.

The two sources name the same vehicle differently and in a different order — the document
says `V-Line 610 Sport` where the page says `V-Line Sport 610`, and the page says
`Expedition Van 54` where the document says `54` — so the join is on a key with the
range's own words removed, never on position. See `_match_key` and `price_for`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from html import unescape
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://www.auto-trail.co.uk"
MANUFACTURER = "Auto-Trail"
MANUFACTURER_DISPLAY_NAME = "Auto-Trail"

#: (range page path, range label). The label is what reviewers see as
#: `manufacturer_range`, and it is also the `--range` selector, so the two Expeditions
#: must stay distinguishable here: "Expedition Coachbuilt" (4 coachbuilt motorhomes)
#: against "Expedition" (7 campervans). Their spec PDFs are
#: `...Tech-Spec-Expedition-Coach.pdf` and `...Tech-Spec-Expedition-Van.pdf`, but
#: "Expedition Van" is a document-internal name that appears nowhere on the website, so
#: it is deliberately not used as the range label.
#:
#: Campervans are included on the same basis as Swift's and Adria's: FMLV treats them as
#: motorhomes and the export carries both under one manufacturer.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhomes-range/expedition-coachbuilt", "Expedition Coachbuilt"),
    ("motorhomes-range/excel", "Excel"),
    ("motorhomes-range/f-line", "F-Line"),
    ("motorhomes-range/imala", "Imala"),
    ("motorhomes-range/frontier", "Frontier"),
    ("motorhomes-range/grande-frontier", "Grande Frontier"),
    ("campervans-range/adventure", "Adventure"),
    ("campervans-range/expedition", "Expedition"),
    ("campervans-range/v-line-se", "V-Line SE"),
    ("campervans-range/v-line-sport", "V-Line Sport"),
)

#: A model page linked from a range page. Slugs are not derivable from model names — the
#: F-Line F67 lives at `/motorhomes/f67/` and the campervan Expedition 54 at
#: `/campervans/54-2/` — so links are read, never constructed.
_MODEL_HREF = re.compile(
    r"""["'](https://www\.auto-trail\.co\.uk/(?:motorhomes|campervans)/[a-z0-9\-]+/)["']"""
)

#: The technical specification PDF linked from a model page. The trailing digits are a
#: WordPress upload counter (`Tech-Spec-Excel-4.pdf`, `Tech-Spec-F-Line-8.pdf`) that
#: increments whenever Auto-Trail re-uploads, so this is rediscovered every run.
_SPEC_HREF = re.compile(
    r"""["'](https://www\.auto-trail\.co\.uk/wp-content/uploads/[^"']*Tech-Spec[^"']*\.pdf)["']""",
    re.IGNORECASE,
)

#: One model card on a range page: its link, its title and its "from" price.
#:
#: The three are captured in a single pattern that cannot cross a card boundary — the
#: `(?:(?!</a>).)*?` guards stop at the end of the enclosing anchor — so a card with no
#: price yields no match rather than silently borrowing the next card's.
_CARD = re.compile(
    r'<a\s+href="(?P<url>[^"]+)"\s+class="card">'
    r"(?:(?!</a>).)*?"
    r'<h4 class="card-title">(?P<name>[^<]*)</h4>'
    r"(?:(?!</a>).)*?"
    r'<div class="card-price">\s*Price from\s*£\s*(?P<price>[\d,]+(?:\.\d{2})?)',
    re.S,
)

#: The roster each document states about itself, e.g.
#: `Applicable to Expedition Coachbuilt C63, C71, C72, C73`. This is the manufacturer's
#: own claim about how many models the document holds, and it is what makes a silently
#: dropped model detectable.
_APPLICABLE_TO = re.compile(r"Applicable to ([^\n]+)")

#: An all-caps line that might be a model's running header. Section headings (`POWER`,
#: `INSULATION & STRENGTH`) match this too and are filtered out by the roster.
_HEADING = re.compile(r"^([A-Z0-9][A-Z0-9 \-&'./]{2,})\s*$", re.MULTILINE)

#: The kerning artefact. The PDF renders `T` followed by a lowercase letter with a
#: spurious space — `T otal seats`, `T yre`, `T ruma`, `Max. T orque`, `Auto-T rail`.
#: Restricted to `T` on the evidence: across all ten documents every genuine occurrence
#: of this pattern starts with `T`, and the other single-capital-then-space matches
#: (`A compliance`, `C and`) are real word boundaries that a broader rule would corrupt.
#: Without this, `Total seats` never matches and every seat count comes back empty.
_KERNING = re.compile(r"\bT (?=[a-z])")

#: Auto-Trail mixes hyphen and em-dash as the same separator, sometimes within one
#: document (both `- 3,500kg/3,650kg manual` and `— 3,500kg/3,650kg manual` appear in
#: the Expedition Coachbuilt PDF).
_DASHES = re.compile(r"[‐-―−]")

#: Body styles, as the documents state them. Only the coachbuilt and A-class ranges
#: publish a `BODY STYLES` section; the four campervan ranges have none, so their
#: `body_type` is worked out from the roof instead — see `_campervan_body_type`.
_BODY_STYLES: tuple[tuple[str, BodyType], ...] = (
    ("a-class", BodyType.A_CLASS),
    # "Hi-Line ... with over cab bed area" is an over-cab bed; "Lo-Line ... with over
    # cab storage area" is not, despite also mentioning "over cab". Order matters:
    # check for the storage variant before the generic "over cab".
    ("over cab storage", BodyType.COACH_BUILT_LOW_PROFILE),
    ("low profile", BodyType.COACH_BUILT_LOW_PROFILE),
    ("over cab bed", BodyType.COACH_BUILT_OVER_CAB_BED),
)

#: Figures that exist only in the price list, which is a rasterised image no parser can
#: read. Transcribed by a human reading the rendered pages, and applied **only where the
#: specification document publishes nothing** — a parsed value always wins.
#:
#: There is exactly one. Expedition Coachbuilt C71's block omits `Max. gross weight`
#: entirely (see `_reconciles`), but the price list gives it as `3,500/3,650/4,400kg`,
#: matching its three siblings. The transcription was checked against Auto-Trail's own
#: arithmetic across all 37 rows before being trusted: ex works excl. VAT + VAT + £635 of
#: on-the-road charges reproduces the on-the-road price on every one.
#:
#: **This does not refresh itself.** If Auto-Trail reissue the price list with different
#: weights, nothing here will notice, so every use is narrated with the date it was read
#: and the reviewer sees the same in the provenance snippet. Re-verify at each model-year
#: rollover — `docs/adapters/README.md` covers when those fall. Prefer leaving a field
#: blank to adding to this table: a visible gap is safer than a stale figure, which is why
#: it holds one entry and not a copy of the price list.
_PRICE_LIST_SOURCE = "Price and Options List, 1st June 2026 (read from the page image)"
_PRICE_LIST_READ_ON = "16 August 2026"
_MANUALLY_SOURCED_MTPLM_KG: dict[tuple[str, str], int] = {
    ("Expedition Coachbuilt", "C71"): 3500,
}

#: An elevating pop-top fitted **as standard**, which is what distinguishes
#: `campervan_high_top_elevating_roof` from `campervan_high_top`. The trailing `Included`
#: is the whole point: the same row reads `Cost option` on the Expedition Van, and an
#: option does not change what the base vehicle is.
_ELEVATING_ROOF_STANDARD = re.compile(
    r"^[^\n]*elevating pop-top roof[^\n]*\bIncluded\s*$", re.MULTILINE | re.IGNORECASE
)

#: A campervan taller than this is a high top — the roof line materially above the side
#: windows. Threshold set by the NCC side on 16 August 2026 from the live data: FMLV
#: currently carries six standard-height campervans and **the tallest is 2050mm**, so
#: 2300mm leaves a clear 250mm margin above every known standard roof while sitting far
#: below the 2680mm that all sixteen Auto-Trail campervans share.
HIGH_TOP_ABOVE_MM = 2300

#: Bounds on a plausible payload, in kg. Auto-Trail's real payloads run 355–965 kg
#: across the 37 layouts. These are wide enough not to reject a genuine outlier and
#: tight enough to catch the failure that matters: reading `Max. gross train weight` as
#: the MTPLM, which inflates the payload by the towing allowance (1250–2500 kg).
MIN_PAYLOAD_KG = 100
MAX_PAYLOAD_KG = 2000


def normalise(text: str) -> str:
    """Undo the two rendering artefacts that stop labels matching."""
    return _DASHES.sub("-", _KERNING.sub("T", text)).replace("’", "'")


def _squash(value: str) -> str:
    """Uppercase alphanumerics only, for comparing a heading with a roster entry."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _pounds(value: str) -> int:
    """`'69,005.00'` -> `69005`, the whole pounds `rrp_pounds` carries."""
    return round(Decimal(value.replace(",", "")))


def _match_key(name: str, range_label: str) -> str:
    """A model's identity with the range's own words removed, for joining page to PDF.

    The range page and the specification document name the same vehicle differently, and
    not merely by prefix — the range words move around the number. The roster says
    `V-Line 610 Sport` where the card says `V-Line Sport 610`, so neither is a prefix of
    the other and no amount of head-trimming aligns them. Dropping *every* word that
    belongs to the range label, wherever it sits, leaves `610` on both sides.

    Compared on alphanumerics only, so the card's `GF-80` and the roster's `GF-80` agree
    regardless of punctuation, and the run of whitespace WordPress leaves inside
    `F-Line         F60` is irrelevant.
    """
    range_words = {_squash(word) for word in range_label.split()}
    return "".join(
        squashed
        for word in name.split()
        if (squashed := _squash(word)) and squashed not in range_words
    )


def _leading_kilograms(value: str) -> int:
    """`'3500/3650/4400'` -> `3500`.

    Auto-Trail lists the standard build first and chassis upgrades after it — the Imala
    736 offers all three of 3500, 3650 and 4400 kg. FMLV carries one MTPLM, and it is
    the standard one.
    """
    return int(value.split("/")[0].replace(",", ""))


def _leading_int(value: str) -> int:
    """`'2-4'` -> `2`, the standard build.

    Used for **both** berths and seat belts, per the base-vehicle rule in
    `docs/adapters/README.md`: where a manufacturer publishes a range, FMLV records what
    the vehicle has as standard, because the upper figure is generally reached only with
    options. Auto-Trail's own copy for the C73 calls it "a six-berth, and *optional*
    six-belt motorhome", which is the same distinction in their words.

    The upper figure is not discarded — `_trailing_int` still reads it for the
    reconciliation check, which is the only thing it was ever load-bearing for.
    """
    return int(value.split("-")[0])


def _trailing_int(value: str) -> int:
    """`'4-6'` -> `6`, the maximum.

    Used only for the two figures that *are* maxima: the separately published
    `Max. No. of berths` row, and the upper bound of `Sleeps` that it is checked
    against. The six motorhome documents publish both, and they agree on all 21 models
    with no disagreement, which is what makes a slipped block boundary detectable — see
    `_reconciles`.

    Deliberately **not** used for `berths`. That the maximum is real is a different
    question from what the vehicle sleeps as standard, and FMLV records the latter.
    """
    return int(value.split("-")[-1])


def _row(block: str, label: str) -> str | None:
    """The figure at the *end* of a labelled row, or `None` if the row is absent.

    Anchored on the end of the line and never on the parenthetical, because
    `Max. gross weight (with 3650kgs no cost option)` is boilerplate that Auto-Trail
    reproduces even on rows whose real value is 4500 or 5000 kg. Reading the
    parenthetical yields 3650 kg for a 5000 kg motorhome.
    """
    match = re.search(rf"^{label}[^\n]*?([\d,]+(?:/[\d,]+)*)kg\s*$", block, re.MULTILINE)
    return match.group(1) if match else None


def _millimetres(block: str, label: str) -> int | None:
    """A dimension in mm, or `None` if the row is absent or malformed.

    Takes the **first** figure where a row gives several, matching `_leading_kilograms`
    and the base-vehicle rule in `docs/adapters/README.md`. The Frontier ranges publish
    `Height 3030/3106mm`, where the extra 76 mm is the roof-mounted satellite dome in the
    optional Media+ pack — an accessory, not the vehicle. Capturing the whole
    slash-separated group rather than letting the pattern run to the last number is what
    makes this deliberate: the earlier form ended up reading 3106 simply because it
    anchored on `mm`.

    The `mm` unit is required rather than optional. The F-Line F74 publishes
    `Height 2880m` — a typo for 2880mm — and accepting a bare `m` would mean reading a
    figure whose unit the document got wrong. It stays unread, and `parse_models`
    narrates it so the gap is visible rather than silent.
    """
    match = re.search(rf"^{label}[^\n]*?([\d,]+(?:/[\d,]+)*)mm\s*$", block, re.MULTILINE)
    return int(match.group(1).split("/")[0].replace(",", "")) if match else None


def _dimension_row_present(block: str, label: str) -> bool:
    """Whether a dimension row exists at all, regardless of whether its value parsed."""
    return re.search(rf"^{label}\b", block, re.MULTILINE) is not None


def _figure(block: str, label: str) -> str | None:
    """The raw figure on a labelled row: `'4-6'` from `Sleeps 4-6`, or `'4'` from `Sleeps 4`.

    Kept as the published string rather than an int, because a range carries information
    a single number cannot. `docs/adapters/README.md` requires the manufacturer's own
    wording to reach the reviewer through the provenance snippet, so `berths` recording
    `4` is visibly a reading of `4-6` rather than a claim that Auto-Trail printed `4`.
    """
    match = re.search(rf"^{label}\s+(\d+(?:-\d+)?)", block, re.MULTILINE)
    return match.group(1) if match else None


def _count(block: str, label: str, *, take: Callable[[str], int]) -> int | None:
    figure = _figure(block, label)
    return take(figure) if figure is not None else None


@dataclass(frozen=True)
class AutoTrailProduct:
    """One model, as read from its block of a range's technical specification."""

    range_label: str
    model: str
    berths: int | None = None
    mh_passenger_seats_inc_driver: int | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    mgtw_kilograms: int | None = None
    towing_kilograms: int | None = None
    body_type: BodyType | None = None
    base_vehicle_manufacturer: str | None = None
    rrp_pounds: int | None = None
    #: True when `mtplm_kilograms` came from `_MANUALLY_SOURCED_MTPLM_KG` rather than from
    #: the specification document, so `collect` can narrate it and the reviewer can see it.
    mtplm_manually_sourced: bool = False
    #: The `Sleeps` row exactly as published — `'4-6'`, or `'4'` where there is no range.
    #: Carried into the provenance snippet so a reviewer seeing `berths = 4` can tell it
    #: was read from `4-6` rather than printed as `4`.
    sleeps_published: str | None = None
    #: The upper bound of `Sleeps`. Never written to FMLV — `berths` records the standard
    #: figure — but retained because it is one half of the berth cross-check.
    sleeps_max: int | None = None
    #: `Max. No. of berths`, published by the six motorhome documents but by none of the
    #: four campervan ones. Not written to FMLV either; it is the other half of that
    #: check, and the two must agree. See `_reconciles`.
    stated_max_berths: int | None = None
    #: Rows that exist in the document but could not be read, for `collect` to narrate.
    parse_warnings: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.range_label} {self.model}"

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload, which Auto-Trail does not publish, derived from the two masses."""
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms


def _reconciles(product: AutoTrailProduct) -> bool:
    """Whether the weights are internally consistent enough to propose.

    Auto-Trail publishes no payload, so there is no `payload == MTPLM - MRO` identity to
    lean on the way Morelo and Swift allow. What it does publish is a strict ordering —
    gross train weight above maximum laden weight above mass in running order — and that
    is enough to catch the failure that actually threatens this document.

    That failure is concrete: **Expedition Coachbuilt C71 has no `Max. gross weight` row
    at all**, going straight from axle loadings to `Max. gross train weight`. A parser
    that matches `Max. gross` loosely reads C71's MTPLM as 4750 kg, and the result — a
    7.26 m motorhome with a 1670 kg payload — is plausible enough that nothing
    downstream would question it. Both the ordering test and the payload bounds reject
    it.

    A product with no MTPLM or no MRO passes, having nothing to contradict; it simply
    proposes no change to the fields it lacks.
    """
    mtplm, mro, mgtw = product.mtplm_kilograms, product.mro_kilograms, product.mgtw_kilograms

    # The berth *maximum* is published twice by the motorhome documents — as the upper
    # bound of `Sleeps` and again as `Max. No. of berths`. They agree on all 21 models
    # that state both, so a disagreement means the block boundaries slipped and two
    # models' figures have been mixed.
    #
    # Note this compares the two published maxima with each other, not with `berths`.
    # `berths` records the *standard* figure (the lower bound of `Sleeps`, per the
    # base-vehicle rule in `docs/adapters/README.md`), so comparing it against
    # `Max. No. of berths` would reject every model whose `Sleeps` is a range — which is
    # 17 of the 37 — while catching nothing. The check keeps its full strength here: it
    # still fails if either figure comes out of the wrong block.
    if (
        product.stated_max_berths is not None
        and product.sleeps_max is not None
        and product.sleeps_max != product.stated_max_berths
    ):
        return False

    if mgtw is not None and mtplm is not None and mgtw <= mtplm:
        return False
    if mtplm is None or mro is None:
        return True
    if mtplm <= mro:
        return False
    payload = mtplm - mro
    return MIN_PAYLOAD_KG <= payload <= MAX_PAYLOAD_KG


def _towing_identity_holds(product: AutoTrailProduct) -> bool:
    """Whether `MGTW - MTPLM == max towing weight`, the stronger check where available.

    Published on the six motorhome ranges and holds on 17 of the 18 rows that carry all
    three figures. The exception is **Frontier Comanche**, a 5000 kg tri-axle that has
    kept the 1500 kg towing figure belonging to the 4500 kg Delaware and Scout:
    6000 - 5000 = 1000, not 1500.

    That is Auto-Trail's own inconsistency, not a misparse — Comanche's MTPLM, MRO and
    payload are all correct and mutually consistent. So this is narrated as a warning
    rather than used as the drop criterion: dropping the product would discard good
    weights over a bad figure in a field FMLV does not even carry. `_reconciles` remains
    the thing that decides.
    """
    mtplm, mgtw, towing = (
        product.mtplm_kilograms,
        product.mgtw_kilograms,
        product.towing_kilograms,
    )
    if mtplm is None or mgtw is None or towing is None:
        return True
    return mgtw - mtplm == towing


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def find_model_urls(range_html: str) -> list[str]:
    """Every model page linked from a range page, in document order, deduplicated.

    Read rather than constructed, and taken from the range pages rather than
    `/sitemap.html`: the sitemap is stale and still lists `excel-675b`, `excel-690l`,
    `f-line-f68` and `grande-frontier-gf88`, all of which 404.
    """
    seen: dict[str, None] = {}
    for match in _MODEL_HREF.finditer(range_html):
        seen.setdefault(match.group(1), None)
    return list(seen)


def find_spec_pdf_url(model_html: str) -> str | None:
    """The technical specification PDF linked from a model page.

    `None` rather than a guess: the upload counter in the filename cannot be
    reconstructed, so a missing link means the page changed and is worth reporting.
    """
    match = _SPEC_HREF.search(model_html)
    return match.group(1) if match else None


def parse_prices(range_html: str, range_label: str) -> dict[str, int]:
    """Every model's "from" price on a range page, keyed by `_match_key`.

    **This is the on-the-road price**, which is what FMLV's guide price records. Verified
    against Auto-Trail's own price list, which prints four columns — ex works excluding
    VAT, VAT, ex works including VAT, and on the road — and the website figure is the
    last of them exactly, on ten of ten models checked across two ranges. The difference
    is a flat £635 of number plates, twelve months' VED, delivery and first registration.

    The price list PDF itself is a rasterised image and yields no text, so the range page
    is the only machine-readable source for it. See `docs/adapters/auto-trail.md`.
    """
    prices: dict[str, int] = {}
    for match in _CARD.finditer(range_html):
        name = re.sub(r"\s+", " ", unescape(match.group("name"))).strip()
        key = _match_key(name, range_label)
        if key:
            prices.setdefault(key, _pounds(match.group("price")))
    return prices


def price_for(model: str, range_label: str, prices: dict[str, int]) -> int | None:
    """One model's price, matched by suffix on the range-stripped key.

    Suffix rather than equality, because the campervan Expedition cards carry a word the
    document does not: the page says `Expedition Van 54` where the roster says `54`.
    ("Expedition Van" is the document-internal name; the range is called "Expedition"
    everywhere on the website, so neither side can simply be renamed to match.)

    Suffix matching is safe against the overlapping campervan names for the same reason
    it is safe when slicing the PDF into blocks — the variants extend the tail. `68` does
    not take `68 XL`'s price, because `VAN68XL` does not end with `68`.

    An ambiguous match yields `None` rather than a guess. Prices are the one field here
    with no arithmetic check behind them, so a wrong one would be invisible.
    """
    key = _match_key(model, range_label)
    if not key:
        return None
    matched = [price for card_key, price in prices.items() if card_key.endswith(key)]
    return matched[0] if len(matched) == 1 else None


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_roster(text: str) -> list[str]:
    """The models a document says it covers, from its own `Applicable to` line.

    The line is repeated as a running footer on every page; they are identical, so the
    first is taken.
    """
    match = _APPLICABLE_TO.search(text)
    if match is None:
        return []
    return [entry.strip() for entry in match.group(1).split(",") if entry.strip()]


def _model_name(entry: str, range_label: str) -> str:
    """A roster entry with its range prefix removed: `'Excel 620S'` -> `'620S'`.

    Auto-Trail is inconsistent about whether the roster repeats the range name, and only
    ever does so on the first entry: `Applicable to Excel 620S, 620G, 690T`. Leading
    words are dropped for as long as they keep spelling out the start of the range
    label, so that `620S` and `620G` come out alike.

    Matching on squashed text is what makes this work across the site's punctuation:
    the roster writes `F-LINE F60` against a `F-Line` range label, and `V-Line 540 SE`
    against `V-Line SE` — where only the first word is a prefix, leaving `540 SE`.
    Entries carrying no range name at all — Frontier's `Delaware, Scout, Comanche` —
    are left untouched.
    """
    target = _squash(range_label)
    words = entry.split()
    consumed = ""
    while len(words) > 1 and target.startswith(consumed + _squash(words[0])):
        consumed += _squash(words[0])
        words = words[1:]
    return " ".join(words)


def _find_blocks(text: str, roster: list[str], range_label: str) -> list[tuple[str, str]]:
    """Slice the document into one `(model name, block)` pair per roster entry.

    Model blocks are found by matching the document's all-caps running headers against
    the roster, rather than by treating every all-caps line as a model: `POWER`,
    `SAFETY` and `INSULATION & STRENGTH` are indistinguishable from `EXCEL 690T` by case
    alone, and a roster-free approach picks all of them up.

    A heading matches an entry when it *ends* with it, which is what lets the bare
    `C71` find `EXPEDITION COACHBUILT C71`. Comparison is on alphanumerics only, so
    `GF-80` matches `GRANDE FRONTIER GF-80`. Suffix matching is safe against the
    Expedition campervans' overlapping names because the variants extend the tail rather
    than the head — `EXPEDITION 68 XL` does not end with `68`.
    """
    headings = [(match.start(), match.group(1).strip()) for match in _HEADING.finditer(text)]

    starts: list[tuple[int, str]] = []
    for entry in roster:
        squashed = _squash(entry)
        position = next(
            (pos for pos, heading in headings if _squash(heading).endswith(squashed)),
            None,
        )
        if position is not None:
            starts.append((position, _model_name(entry, range_label)))

    starts.sort()
    blocks: list[tuple[str, str]] = []
    for index, (start, model) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        blocks.append((model, text[start:end]))
    return blocks


def _campervan_body_type(block: str) -> BodyType | None:
    """A campervan's body type, from its roof — see the body-type rule in `README.md`.

    Two independent questions. **Is the roof a high top?** — the roof line materially above
    the side windows, which shows up as a published height far beyond a standard panel van;
    all sixteen Auto-Trail campervans are 2680mm. **Does it have an elevating roof?** — and
    critically, *as standard*, because the base-vehicle rule governs here as everywhere.

    Auto-Trail state it in a way that makes the distinction readable:

        Colour coded elevating pop-top roof (including bathroom window)  Included    <- Adventure
        Colour coded elevating pop-top roof (bathroom window included)   Cost option <- Expedition

    So the Adventure is a high top *with* an elevating roof, and the Expedition Van is a
    high top whose pop-top is an extra the buyer may not have. The word at the end of the
    row decides it, not the presence of the feature.

    The two questions are independent, so between them they settle all four campervan body
    types — no case is left to judgement:

    ==================  ====================  ==============================
    Height              No elevating roof     Elevating roof as standard
    ==================  ====================  ==============================
    > 2300mm            high top              high top + elevating roof
    <= 2300mm           campervan             campervan + elevating roof
    ==================  ====================  ==============================

    A missing height is the one thing that yields `None`, because then neither question can
    be answered.
    """
    height = _millimetres(block, "Height")
    if height is None:
        return None
    elevating = _ELEVATING_ROOF_STANDARD.search(block) is not None
    if height > HIGH_TOP_ABOVE_MM:
        return (
            BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF
            if elevating
            else BodyType.CAMPERVAN_HIGH_TOP
        )
    return BodyType.CAMPERVAN_ELEVATING_ROOF if elevating else BodyType.CAMPERVAN


def _body_type(block: str) -> BodyType | None:
    match = re.search(r"^BODY STYLES\s*\n(.+)$", block, re.MULTILINE)
    if match is None:
        # No `BODY STYLES` section means a campervan document — the four campervan ranges
        # publish none, the six motorhome ranges all do.
        return _campervan_body_type(block)
    described = match.group(1).lower()
    return next((body for token, body in _BODY_STYLES if token in described), None)


def parse_models(text: str, range_label: str) -> list[AutoTrailProduct]:
    """Every model in one range's technical specification document.

    `text` must already have been through `normalise`.
    """
    roster = parse_roster(text)
    products: list[AutoTrailProduct] = []

    for model, block in _find_blocks(text, roster, range_label):
        # Campervans label the maximum laden weight differently — `Max. authorised
        # weight` rather than `Max. gross weight`. Matching only the motorhome label
        # loses all 16 campervan weights while looking like "campervans publish none".
        mtplm = _row(block, r"Max\. gross weight") or _row(block, r"Max\. authorised weight")
        # `Max. gross train weight` is the towing-combination figure and runs 1250-2500 kg
        # above the MTPLM. It is matched in full precisely so it is never mistaken for one.
        mgtw = _row(block, r"Max\. gross train weight")
        mro = _row(block, r"Mass in running order")
        towing = _row(block, r"Max\. towing weight")
        chassis = re.search(r"^Chassis type\s+(\S+)", block, re.MULTILINE)

        # (display name, row pattern) for the three dimension rows, so a row that is
        # present but unreadable can be named in a warning rather than silently missing.
        dimension_rows = (
            ("Length", "Length"),
            ("Width", r"Width \(excl\. door mirrors\)"),
            ("Height", "Height"),
        )
        dimensions = {name: _millimetres(block, pattern) for name, pattern in dimension_rows}
        warnings = tuple(
            f"{name} row is present but its value could not be read"
            for name, pattern in dimension_rows
            if dimensions[name] is None and _dimension_row_present(block, pattern)
        )

        # `Sleeps` yields three things: the standard figure FMLV records, the maximum
        # that `Max. No. of berths` is checked against, and the published wording that
        # the reviewer needs in order to see that `4` came out of `4-6`.
        sleeps = _figure(block, "Sleeps")

        # The document always wins; the manual figure only fills a hole it leaves.
        parsed_mtplm = _leading_kilograms(mtplm) if mtplm else None
        manual_mtplm = _MANUALLY_SOURCED_MTPLM_KG.get((range_label, model))
        mtplm_kilograms = parsed_mtplm if parsed_mtplm is not None else manual_mtplm

        products.append(
            AutoTrailProduct(
                range_label=range_label,
                model=model,
                berths=_leading_int(sleeps) if sleeps is not None else None,
                sleeps_published=sleeps,
                sleeps_max=_trailing_int(sleeps) if sleeps is not None else None,
                mh_passenger_seats_inc_driver=_count(block, "Seatbelts", take=_leading_int),
                mh_length_mm=dimensions["Length"],
                mh_width_mm=dimensions["Width"],
                mh_height_mm=dimensions["Height"],
                mtplm_kilograms=mtplm_kilograms,
                mtplm_manually_sourced=parsed_mtplm is None and manual_mtplm is not None,
                mro_kilograms=_leading_kilograms(mro) if mro else None,
                mgtw_kilograms=_leading_kilograms(mgtw) if mgtw else None,
                towing_kilograms=_leading_kilograms(towing) if towing else None,
                body_type=_body_type(block),
                base_vehicle_manufacturer=fmlv_base_vehicle(chassis.group(1)) if chassis else None,
                stated_max_berths=_count(block, r"Max\. No\. of berths", take=_trailing_int),
                parse_warnings=warnings,
            )
        )

    return products


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(
    product: AutoTrailProduct, spec_url: str, range_url: str
) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        berths=product.berths,
        mh_passenger_seats_inc_driver=product.mh_passenger_seats_inc_driver,
        rrp_pounds=product.rrp_pounds,
        mro_kilograms=product.mro_kilograms,
        mtplm_kilograms=product.mtplm_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=product.mh_length_mm,
        mh_width_mm=product.mh_width_mm,
        mh_height_mm=product.mh_height_mm,
        body_type=product.body_type,
    )

    # `berths` records the standard figure, so the snippet carries Auto-Trail's own
    # wording rather than the parsed number — a reviewer seeing `4` needs to know the
    # document said `4-6`, which one integer cannot tell them.
    snippets = {
        "berths": ("Sleeps", product.sleeps_published),
        "mh_passenger_seats_inc_driver": ("Seatbelts (inc. driver)", product.mh_passenger_seats_inc_driver),
        "mh_length_mm": ("Length", product.mh_length_mm),
        "mh_width_mm": ("Width (excl. door mirrors)", product.mh_width_mm),
        "mh_height_mm": ("Height", product.mh_height_mm),
        "mtplm_kilograms": ("Max. gross weight", product.mtplm_kilograms),
        "mro_kilograms": ("Mass in running order", product.mro_kilograms),
        "base_vehicle_manufacturer": ("Chassis type", product.base_vehicle_manufacturer),
    }
    provenance = {
        field: Provenance(
            source_url=spec_url,
            snippet=f"{product.label} — Technical Specification, {row}: {value}",
        )
        for field, (row, value) in snippets.items()
        if value is not None
    }
    # Overwrite the spec-document provenance where the figure did not come from there,
    # so the reviewer is told it was read off an image by a person and when.
    if product.mtplm_manually_sourced and product.mtplm_kilograms is not None:
        provenance["mtplm_kilograms"] = Provenance(
            source_url=f"{BASE_URL}/price-list/",
            snippet=(
                f"{product.label} — {product.mtplm_kilograms}kg, MANUALLY SOURCED from the "
                f"{_PRICE_LIST_SOURCE} on {_PRICE_LIST_READ_ON}, because the technical "
                f"specification omits the Max. gross weight row for this model. Not "
                f"machine-readable and not refreshed by later runs — re-verify at the next "
                f"model-year changeover"
            ),
        )

    if product.rrp_pounds is not None:
        provenance["rrp_pounds"] = Provenance(
            source_url=range_url,
            snippet=(
                f"{product.label} — Price from £{product.rrp_pounds:,}. This is the "
                f"on-the-road price, which Auto-Trail's price list defines as the "
                f"ex-works price including VAT plus £635 of number plates, twelve "
                f"months' vehicle excise duty, delivery and first registration fee"
            ),
        )
    if product.mh_payload_kilograms is not None:
        provenance["mh_payload_kilograms"] = Provenance(
            source_url=spec_url,
            snippet=(
                f"{product.label} — derived: {product.mtplm_kilograms}kg max. gross weight "
                f"- {product.mro_kilograms}kg mass in running order "
                f"= {product.mh_payload_kilograms}kg (Auto-Trail publishes no payload)"
            ),
        )

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def _fetch_range_page(
    http: Fetcher,
    range_url: str,
    label: str,
    on_progress: Callable[[str], None],
) -> str | None:
    """A range page's HTML, which carries both the model links and the "from" prices."""
    page = http.fetch(range_url)
    if page.status_code != 200:
        on_progress(f"[{label}] SKIPPED: {range_url} returned {page.status_code}")
        return None
    return page.file_path.read_text(encoding="utf-8", errors="replace")


def _spec_pdf_for_range(
    http: Fetcher,
    range_html: str,
    range_url: str,
    label: str,
    on_progress: Callable[[str], None],
) -> str | None:
    """Find a range's spec PDF: a model page linked from the range page -> `Tech-Spec`.

    Every model in a range links the same document, so the first model page that yields
    one is enough. Later ones are still tried if an early page has been rebuilt without
    the link, which costs a fetch only in the case that would otherwise lose the range.
    """
    model_urls = find_model_urls(range_html)
    if not model_urls:
        on_progress(f"[{label}] SKIPPED: no model pages linked from {range_url}")
        return None

    for model_url in model_urls:
        model_page = http.fetch(model_url)
        if model_page.status_code != 200:
            on_progress(f"[{label}] {model_url} returned {model_page.status_code}, trying the next model")
            continue
        spec_url = find_spec_pdf_url(
            model_page.file_path.read_text(encoding="utf-8", errors="replace")
        )
        if spec_url is not None:
            return spec_url
        on_progress(f"[{label}] no Tech-Spec link on {model_url}, trying the next model")

    on_progress(f"[{label}] SKIPPED: no technical specification PDF found on any model page")
    return None


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Auto-Trail needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every Auto-Trail layout from the current per-range specification PDFs.

    A range that can't be read is narrated and skipped rather than raised, so one
    rebuilt page doesn't cost the other nine ranges.
    """
    results: list[ExtractedMotorhome] = []

    for path, label in ranges:
        on_progress(f"[{label}] finding the current technical specification...")
        range_url = f"{BASE_URL}/{path}/"
        range_html = _fetch_range_page(http, range_url, label, on_progress)
        if range_html is None:
            continue

        prices = parse_prices(range_html, label)
        if not prices:
            on_progress(
                f"[{label}] WARNING: no 'Price from' cards on {range_url}; "
                f"weights and dimensions will still be collected, but no price"
            )

        spec_url = _spec_pdf_for_range(http, range_html, range_url, label, on_progress)
        if spec_url is None:
            continue

        on_progress(f"[{label}] downloading {spec_url} ...")
        spec = http.fetch(spec_url)
        if spec.status_code != 200:
            on_progress(f"[{label}] SKIPPED: specification returned {spec.status_code}")
            continue

        document = extract_text(spec.file_path)
        if document.is_empty():
            on_progress(f"[{label}] SKIPPED: {spec_url} has no extractable text")
            continue

        text = normalise(document.text)
        roster = parse_roster(text)
        if not roster:
            on_progress(f"[{label}] SKIPPED: no 'Applicable to' roster in {spec_url}")
            continue

        products = parse_models(text, label)
        # The document's own roster is the completeness check. A model named there but
        # not found is a parse failure, and saying so is the difference between noticing
        # it and reading a dropped model as a discontinued one.
        if len(products) != len(roster):
            found = {product.model for product in products}
            missing = [
                entry for entry in roster if _model_name(entry, label) not in found
            ]
            on_progress(
                f"[{label}] WARNING: document lists {len(roster)} model(s) but "
                f"{len(products)} were parsed; missing {missing}"
            )
        on_progress(f"[{label}] {len(products)} model(s) found")

        for product in products:
            if not _reconciles(product):
                on_progress(
                    f"[{label}] {product.label} — SKIPPED: weights don't reconcile "
                    f"(max gross {product.mtplm_kilograms}kg, running order "
                    f"{product.mro_kilograms}kg, gross train {product.mgtw_kilograms}kg), "
                    f"so a weight row may have been misread"
                )
                continue
            for warning in product.parse_warnings:
                on_progress(f"[{label}] {product.label} — WARNING: {warning}")

            if product.mtplm_manually_sourced:
                on_progress(
                    f"[{label}] {product.label} — NOTE: the specification publishes no "
                    f"max. gross weight, so {product.mtplm_kilograms}kg was taken from the "
                    f"{_PRICE_LIST_SOURCE}, read on {_PRICE_LIST_READ_ON}. That figure does "
                    f"not refresh itself — re-verify at the next model-year changeover"
                )

            # The price lives on the range page, the specs in the PDF, so this is the one
            # join in the adapter. A model the page does not price is proposed without
            # one rather than dropped: the weights are still good, and a silently
            # missing price is exactly what the narration exists to prevent.
            price = price_for(product.model, label, prices)
            if price is None and prices:
                on_progress(
                    f"[{label}] {product.label} — WARNING: no 'Price from' card matched "
                    f"this model, so no price is proposed for it"
                )
            product = replace(product, rrp_pounds=price)

            if not _towing_identity_holds(product):
                on_progress(
                    f"[{label}] {product.label} — WARNING: "
                    f"{product.mgtw_kilograms}kg gross train - {product.mtplm_kilograms}kg "
                    f"max gross != {product.towing_kilograms}kg max towing. Auto-Trail's own "
                    f"figures disagree; the weights below are still as published"
                )
            results.append(_build_extracted_motorhome(product, spec_url, range_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
