"""Wingamm (wingamm.com) — the thirteenth adapter. Italian, fibreglass monocoque.

See `docs/adapters/wingamm.md` for the full write-up. Eight products in three ranges, and
the whole brand fits in five PDFs listed at `/en/download/`:

    External length MM 6.103
    External width MM 2.240
    External height MM 3.030
    Overall maximum weight KG 3.500
    Weight in running order KG 3.047
    Payload KG 453

One document per range, `label unit value` per line, no side-by-side columns anywhere —
so none of the column-alignment defences that dominate `morelo.py`, `swift.py` and
`sunlight.py` are needed. The risk here is entirely **which label is this**, the
Auto-Trail failure mode, and Wingamm make it worse than Auto-Trail do: five documents use
five different names for the maximum laden weight, three for the seat count, two for the
berths, and one of them omits the mass in running order altogether. See `_MTPLM_LABELS`.

Three things come from the website rather than the PDFs, each for a stated reason:

* **The roster**, from the models index, so a new layout is noticed rather than silently
  missed. Identity itself cannot come from there — see `_DOCUMENTS`.
* **Seats and berths**, from each layout's own page, because the two 2023 catalogues
  (Brownie, City Pro) emit their second technical page as a block of labels followed by a
  block of values, which is exactly the positional misalignment
  `docs/adapters/README.md` forbids pairing up. The three Oasi catalogues state both
  inline, and those are used to check the page rather than replace it.
* **The base vehicle**, from each page's `Drive:` line.

**Dimensions come from the PDFs even though the website disagrees**, which inverts
`docs/adapters/README.md`'s "the website overrules the PDF". The test that rule sets is
not "which is newer" but "can I show one of them is wrong?", and here the website
contradicts *itself*: the index cards give every Oasi 2248 x 3020, the 540.1 and 610 ST
pages 2248 x 2961, the 610 GL and 610 M pages 2240 x 3030, and both 690 pages omit width
and height entirely — for six vehicles sharing one monocoque cross-section. All three
catalogues say 2240 x 3030, and so does every Oasi row already in FMLV. See the survey.

**No price is collected**, though Wingamm publish one. The Oasi catalogues price each
layout in euro *ex works, VAT excluded*, and the Brownie and City Pro price lists exist
only in Italian and quote *VAT included* — so the five documents do not even share a
basis. FMLV holds pound prices from a UK importer list that is not on the website, which
price the three 610 layouts differently where every Wingamm document prices them
identically. Proposing the euro figure would overwrite eight good UK prices with
something well short of what a buyer pays, on a brand where right-hand drive is itself a
EUR 3.000 option. The euro figure is narrated through `on_progress` so it reaches the run
log, and deliberately never reaches a `Motorhome`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from ..fetch.http import Fetcher
from ..fetch.pdf import extract_text
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.wingamm.com"
MANUFACTURER = "Wingamm"
MANUFACTURER_DISPLAY_NAME = "Wingamm"

#: The English download area, and the only roster of Wingamm's documents anywhere. Read
#: every run: the `?wpdmdl=` ids move when a document is replaced (the 690 catalogue is
#: already on its second), so nothing here is hardcoded but the page itself.
DOWNLOAD_AREA_URL = f"{BASE_URL}/en/download/"

#: The models index. Note the Italian slug on the English path — the site is a
#: translation mirror, and `/en/` is a language, not a market.
MODELS_INDEX_URL = f"{BASE_URL}/en/camper-compatti-lusso-monoscocca-vetro-resina/"


@dataclass(frozen=True)
class _Document:
    """One catalogue, and the layouts FMLV holds against it.

    `layouts` maps a model page's slug to **FMLV's own `model` string**, which is why it
    is declared rather than derived. Two independent reasons:

    * The strings are not reconstructible from anything Wingamm publish. FMLV holds
      `610GL` unspaced, `690 TWINS` spaced and capitalised, and `690G` unspaced, against a
      site that writes "Oasi 610 GL" and a catalogue that writes "OASI 690 G". Emitting a
      derived form would cost a weaker fuzzy match on every product and then propose a
      rename on each one that did match — see `docs/adapters/README.md`.
    * The index's card titles are wrong twice over. The 690 G card is titled "Oasis 690 G"
      (confirmed as a typo by the requester, 26 August 2026) and the 610 M card is titled
      "Oasi 610 GL", so the page appears to show the GL twice and the M not at all. Only
      the `href` identifies a card, and only the slug is stable.

    `fmlv_range` is separate from `label` because the three Oasi documents are three
    documents but one range. `label` is the `--range` selector and must stay unique;
    `cli.resolve_ranges` keys on it and would otherwise collapse the three into one.
    """

    #: Matched against a download-area title, squashed to alphanumerics.
    title_key: str
    #: The `--range` selector, and what `on_progress` calls this document.
    label: str
    #: What is emitted as `manufacturer_range`.
    fmlv_range: str
    #: `(model page slug, FMLV model string)` per layout in this document.
    layouts: tuple[tuple[str, str], ...]
    #: `body_type`, or `None` to leave FMLV's value alone. See `_BODY_TYPE_NOTE`.
    body_type: BodyType | None
    #: Set only where `fmlv_range` is a value known to be wrong that is emitted anyway,
    #: because correcting it would cost the product its history. See `_UNDELIVERABLE`.
    intended_range: str | None = None


#: Wingamm's own statement of what they build, from the models index: *"we immediately
#: chose the semi-integrated camper formula, excluding the solutions with attic, which by
#: sailing, reduce the vehicle's stability on the road"*. Semi-integrated is low profile,
#: and the bed above the dinette is a drop-down (`W - Longitudinal double drop-down-bed |
#: 350 Kg Patented`), not an over-cab bed. There is no over-cab bed in the range, so
#: FMLV's `type_coach_built_over_cab_bed` on the five larger Oasi layouts is wrong and
#: the correction is proposed.
#:
#: **City Pro is left alone deliberately**, which is why `body_type` is nullable. FMLV
#: holds `type_campervan_high_top`, and at 2770 mm it clears the shared 2300 mm high-top
#: threshold — but it is not a van conversion: its catalogue calls it *"the only camper
#: with a fibreglass monocoque bodyshell, heated floor, and large garage with the compact
#: dimensions of van"*, a coachbuilt body that happens to be 2050 mm wide. The requester
#: describes Wingamm as selling campervans as well as motorhomes, which fits FMLV's
#: classification, so the adapter proposes nothing rather than force a defensible value
#: to a differently defensible one. Revisit with the NCC side, not in code.
_BODY_TYPE_NOTE = "semi-integrated monocoque with a drop-down bed; Wingamm build no over-cab beds"

_DOCUMENTS: tuple[_Document, ...] = (
    _Document(
        title_key="OASI5401",
        label="Oasi 540.1",
        fmlv_range="Oasi",
        layouts=(("oasi-540", "540"),),
        body_type=BodyType.COACH_BUILT_LOW_PROFILE,
    ),
    _Document(
        title_key="OASI610",
        label="Oasi 610",
        fmlv_range="Oasi",
        layouts=(
            ("oasi-610-gl", "610GL"),
            ("oasi-610m", "610M"),
            ("oasi-610-st", "610ST"),
        ),
        body_type=BodyType.COACH_BUILT_LOW_PROFILE,
    ),
    _Document(
        title_key="OASI690",
        label="Oasi 690",
        fmlv_range="Oasi",
        layouts=(
            ("oasi-690-garage", "690G"),
            ("oasi-690-twins", "690 TWINS"),
        ),
        body_type=BodyType.COACH_BUILT_LOW_PROFILE,
    ),
    _Document(
        title_key="BROWNIE",
        label="Brownie",
        # Wrong, and emitted anyway — see `_UNDELIVERABLE`.
        fmlv_range="Coach Built low profile",
        intended_range="Brownie",
        layouts=(("brownie", "Brownie"),),
        body_type=BodyType.COACH_BUILT_LOW_PROFILE,
    ),
    _Document(
        title_key="CITYPRO",
        # FMLV holds range "Campervan" here, which is a body type rather than a range.
        # Unlike Brownie's, this correction survives matching: `{campervan, city, pro}`
        # against `{city, pro}` scores 0.667, comfortably over the 0.5 threshold, so the
        # rename is proposed normally.
        label="City Pro",
        fmlv_range="City Pro",
        layouts=(("city-pro", "City Pro"),),
        body_type=None,
    ),
)

#: Why Brownie keeps a range everyone agrees is wrong.
#:
#: FMLV files it under `manufacturer_range` "Coach Built low profile" — a body type in the
#: range column — and the requester confirmed on 26 August 2026 that the ranges are
#: Brownie, City Pro and Oasi. But `diff/matching.py` scores identity as a Jaccard
#: similarity on the range-plus-model word bag, and renaming the range to "Brownie" takes
#: `{coach, built, low, profile, brownie}` to `{brownie}` — **0.200 against a 0.5
#: threshold.** Run #30 proved it: the scraped Brownie was reported as a new product and
#: the real one, `product_id` 5855, as disappeared. A rename that orphans the product it
#: renames is worse than the wrong name, because an upload would then create a duplicate
#: and a reviewer would read a phantom discontinuation.
#:
#: So the wrong range is emitted, no provenance is attached to either half of the
#: identity, and nothing is proposed — the product matches at 1.000 and its weights and
#: dimensions update normally. The rename is a one-line manual edit on the FMLV side,
#: narrated on every run until someone makes it. Afterwards, drop `intended_range` here.
#:
#: City Pro is the same class of error and *is* proposed, because its correction happens
#: to keep enough tokens to match. The asymmetry is the matcher's, not Wingamm's.
_UNDELIVERABLE = (
    "cannot be proposed: renaming the range drops this product's identity score to 0.20, "
    "below the 0.5 matching threshold, so it would orphan its FMLV product_id and report "
    "a discontinuation that has not happened. Fix it directly on the FMLV site"
)

DEFAULT_RANGES: tuple[tuple[str, str], ...] = tuple(
    (document.title_key, document.label) for document in _DOCUMENTS
)

#: Model-index slugs that are known and deliberately not collected, so the roster check
#: reports only genuinely new vehicles.
#:
#: * `rookie`, `rookie-l` — **caravans**, out of scope for this review (requester,
#:   26 August 2026). The site files them in the same `camper-caravan` taxonomy as the
#:   motorhomes, and their own pages give the tell: length quoted "with drawbar" and a
#:   total mass of 750-1200 kg.
#: * `oasi-540-preview` — a leftover preview page carrying the 540.1's figures verbatim.
#:   Linked from the English home page but in no index. Not a ninth vehicle.
_IGNORED_SLUGS = frozenset({"rookie", "rookie-l", "oasi-540-preview"})

#: One row of the download area's table: `<strong>` title, then the download link. The
#: `(?:(?!</tr>).)*?` guards cannot cross a row boundary, so a row missing either half
#: yields no match rather than pairing a title with the next row's document.
_DOWNLOAD_ROW = re.compile(
    r'<tr class="__dt_row">'
    r"(?:(?!</tr>).)*?<strong>(?P<title>[^<]+)</strong>"
    r"(?:(?!</tr>).)*?wpdm-download-link[^>]*?href=['\"](?P<url>[^'\"]+)['\"]",
    re.S,
)

#: A model page link, used for the roster. Both the card image and the "find out" button
#: carry it, so hits are deduplicated by slug.
_MODEL_HREF = re.compile(rf"{re.escape(BASE_URL)}/en/camper-caravan/(?P<slug>[a-z0-9-]+)/")

#: A labelled figure on a "Technical info" list. The site renders these two ways, and an
#: adapter that knows only one collects nothing:
#:
#:     <li class="elementor-icon-list-item"><span ...>Travel seats: 4</span></li>  <- model page
#:     <strong>Travel seats:</strong> 4<br />                                      <- index card
#:
#: So the colon may sit inside the label's own tag or after it. The City Pro page adds a
#: third form, where the value sits outside the span that holds the label:
#:
#:     <span class="...-text"><span class="...-text">Mass in running order:&nbsp;</span></span>2.888 kg
#:
#: Only **closing** tags and whitespace may be skipped between the colon and the value.
#: That is what stops a genuinely empty row from reaching forward and reading the next
#: list item's number, since reaching the next row means crossing an opening `<li>`.
_PAGE_FIGURE = r"(?:>|<strong>)\s*{label}\s*:(?:</[a-z]+>|\s|&nbsp;| )*([^<]*)"

#: A layout's starting price on a catalogue's floorplan page. Two forms, because the
#: three documents disagree: the 610 and 690 catalogues print `OASI 610ST  106.300 €`,
#: while the 540.1 catalogue glues the price to the running header as
#: `OASI 540.1TECHNICAL DETAILS € 99.800`. Parsed only to narrate it — see the module
#: docstring on why no price reaches a `Motorhome`.
_PRICE_TRAILING = re.compile(r"^(?P<model>OASI[ 0-9A-Z.]+?)\s+(?P<euros>\d[\d.]*)\s*€\s*$", re.M)
_PRICE_LEADING = re.compile(r"^(?P<model>OASI[ 0-9A-Z.]*?)\s*TECHNICAL DETAILS\s*€\s*(?P<euros>\d[\d.]*)", re.M)

#: Every name the five documents give the maximum laden weight. Auto-Trail's lesson, and
#: worse here: matching only the first of these would lose the 690s and City Pro while
#: looking exactly like "those documents publish no weights".
_MTPLM_LABELS = (
    r"Overall maximum weight",
    r"Maximum authorized mass",
    r"Maximum authorised mass",
    r"Maximum permissible weight",
)

#: Mass in running order. The 540.1 catalogue publishes neither of these — see
#: `WingammSpec.mro_kilograms` for what happens then.
_MRO_LABELS = (r"Weight in running order", r"Mass in running order")

#: Payload. The `\*?` is City Pro's footnote marker (`Payload* KG 612`). Anchoring at the
#: start of the line is what keeps the three decoys out: `Garage payload KG 200`,
#: `External rear motorbike rack payload (OPT) KG 150` and `Towbar payload (OPT) KG
#: 2.000` all sit in the same block, and the 610 catalogue prints `PAYLOAD 350KG` as
#: marketing copy on a feature page — which is the *690's* payload, not the 610's.
_PAYLOAD_LABELS = (r"Payload\*?",)

#: Seats, inclusive of the driver. All five documents state it at least twice and the
#: statements agree, so the first match wins.
_SEAT_LABELS = (
    r"3 points seatbelts",
    r"Three-point seatbelts",
    r"Approved number of places",
    r"Approved seats",
)

#: Berths. `Sleeping capacity` is the 690 catalogue alone.
_BERTH_LABELS = (r"Number of beds", r"Sleeping capacity")

#: How far a model page's length may sit from its catalogue's before it is worth saying
#: so. The 610 GL and 610 M pages carry both `6,100 mm` and `6.103 mm`, the catalogue
#: 6.103 — marketing rounding, not a misparse, so it is narrated rather than fatal.
LENGTH_TOLERANCE_MM = 10

#: Bounds on a plausible payload, in kg. Wingamm's real payloads run 350-753 across the
#: eight layouts, all on a 3500 kg Ducato. Wide enough not to reject a genuine outlier,
#: tight enough to catch a mass read out of the wrong row — `Towbar payload KG 2.000`
#: would produce a payload of 2000 and a nonsense vehicle.
MIN_PAYLOAD_KG = 100
MAX_PAYLOAD_KG = 1500


def _squash(value: str) -> str:
    """Uppercase alphanumerics only, for comparing a document title with a key."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _integer(value: str) -> int | None:
    """`'3.500'` -> `3500`, `'2240'` -> `2240`, `'3,500'` -> `3500`.

    Wingamm mix the Italian thousands dot with the bare form inside one corpus and
    sometimes inside one document — the 690 catalogue writes `External width MM 2240` two
    lines above `Maximum authorized mass KG 3.500`. The separator is only removed where it
    genuinely separates a group of three digits, so a decimal like `13,9` or a model name
    like `540.1` is never silently multiplied by a thousand.
    """
    cleaned = re.sub(r"[.,](?=\d{3}(?:\D|$))", "", value.strip())
    return int(cleaned) if re.fullmatch(r"\d+", cleaned) else None


def _leading_int(value: str) -> int | None:
    """`'3+1'` -> `3`, `'3 + 1'` -> `3`, `'4'` -> `4`.

    The base-vehicle rule in `docs/adapters/README.md`: where a manufacturer publishes a
    range, FMLV records what the vehicle sleeps as standard. The 540.1's `3+1` is a
    drop-down double, a dinette single, and an optional fourth that the price list sells
    separately as `NIGHT DOUBLE (4° Letto) € 980` — so 3, which is what FMLV holds. The
    published wording is carried into the provenance snippet, because one integer cannot
    tell a reviewer that `3` was read out of `3+1`.
    """
    match = re.match(r"\s*(\d+)", value)
    return int(match.group(1)) if match else None


def _row(text: str, labels: Sequence[str], unit: str) -> str | None:
    """The figure on the first line that starts with one of `labels` and carries `unit`.

    Anchored at the start of the line, which is the whole defence against the payload and
    weight decoys in the same block: `Garage payload` starts with `Garage`, and
    `Max. gross`-style near-misses do not exist here because each label is matched in
    full. The unit is required, so a label whose value moved to another page (Brownie's
    and City Pro's second technical page) reads as absent rather than picking up a
    neighbour's number.
    """
    for label in labels:
        match = re.search(
            rf"^{label}\s*(?:\([^)]*\))?\s*{unit}\.?\s+(\d[\d.,]*)", text, re.MULTILINE | re.IGNORECASE
        )
        if match:
            return match.group(1)
    return None


def _published(text: str, labels: Sequence[str]) -> str | None:
    """The raw figure on a counted row: `'3+1'` from `Number of beds N. 3+1`."""
    for label in labels:
        match = re.search(rf"^{label}\s+N\.\s*(\d+(?:\s*\+\s*\d+)?)", text, re.MULTILINE | re.IGNORECASE)
        if match:
            return match.group(1).replace(" ", "")
    return None


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def parse_download_area(html: str) -> dict[str, str]:
    """Every document in the download area, as `{squashed title: url}`.

    The `refresh` query parameter is dropped. It is a per-render cache-buster, so keeping
    it would change the URL on every run — defeating the content-hash gating that keeps a
    13 MB catalogue from being re-fetched when nothing changed, and putting a
    single-use URL in front of a reviewer in the provenance snippet.
    """
    documents: dict[str, str] = {}
    for match in _DOWNLOAD_ROW.finditer(html):
        url = unescape(match.group("url")).split("&refresh=")[0]
        documents.setdefault(_squash(unescape(match.group("title"))), url)
    return documents


def count_download_rows(html: str) -> int:
    """How many rows the download area's table has, however few of them parsed.

    Compared against `parse_download_area` so a row whose download button is built
    differently is reported rather than silently dropped. One already is: the
    "Wingamm Logo and Media Kit" row carries no `wpdm-download-link`. Nothing in scope
    depends on it, which is exactly why the count has to be said out loud — the day a
    catalogue row changes shape, the symptom is a missing range and nothing else.
    """
    return len(re.findall(r'<tr class="__dt_row">', html))


def document_url(documents: dict[str, str], title_key: str) -> tuple[str | None, list[str]]:
    """The URL for one document, plus every title that matched.

    Returns the match only when it is unambiguous. `OASI610` would match both
    `2. OASI 610 CATALOG AND PRICE LIST` and a future `OASI 610 XL CATALOG`, and guessing
    between them would attach one range's weights to another's layouts — the exact
    silent failure `docs/adapters/README.md` opens with. The caller narrates and skips.
    """
    matched = sorted(title for title in documents if title_key in title)
    if len(matched) != 1:
        return None, matched
    return documents[matched[0]], matched


def parse_roster(index_html: str) -> list[str]:
    """Every model-page slug linked from the models index, deduplicated, in page order.

    This is the roster, and it is the only reason the index is fetched at all. Its card
    *titles* are unusable (see `_Document`) and its dimension figures disagree with the
    catalogues (see the module docstring), but a card exists for every vehicle on sale,
    which makes a newly added layout visible instead of silently absent.
    """
    seen: dict[str, None] = {}
    for match in _MODEL_HREF.finditer(index_html):
        seen.setdefault(match.group("slug"), None)
    return list(seen)


def baseline_in_scope(motorhome: Motorhome, labels: set[str]) -> bool:
    """Which baseline rows a `--range` run should diff against — `cli.baseline_scope`'s hook.

    The default there matches the selector against `manufacturer_range`, and Wingamm
    breaks that twice over. The selectors are *documents* (`Oasi 690`), not FMLV ranges
    (`Oasi`), so the default scoped a two-product run to zero baseline rows and proposed
    both as new — run #32, before this existed. And matching on the range column would be
    wrong even with the right labels, because two of the three ranges are being renamed:
    a `--range "City Pro"` run would miss the baseline row still filed under `Campervan`
    and propose a duplicate of a product FMLV already holds.

    So scope is decided by `model`, which is stable across the renames and unique across
    all eight layouts. The archived 2024 `690 GC` row belongs to no current layout and is
    excluded here; `cli._is_current_model_year` drops it from a full run anyway.
    """
    models = {
        model
        for document in _DOCUMENTS
        if document.label in labels
        for _slug, model in document.layouts
    }
    return motorhome.model in models


def unmapped_slugs(roster: Sequence[str]) -> list[str]:
    """Roster entries that are neither collected nor deliberately ignored."""
    mapped = {slug for document in _DOCUMENTS for slug, _model in document.layouts}
    return [slug for slug in roster if slug not in mapped and slug not in _IGNORED_SLUGS]


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WingammSpec:
    """The technical block of one catalogue — shared by every layout in that document.

    Shared is correct, not a shortcut: the 610 ST, GL and M are one monocoque with
    different furniture, the two 690s likewise, and FMLV already holds identical
    dimensions and weights across each set.
    """

    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    #: `None` where the document publishes no mass in running order, which is the 540.1
    #: catalogue: its block goes straight from `Overall maximum weight KG 3.500` to
    #: `Payload KG 655`. `mro_derived` says which happened, because a figure computed
    #: from the other two must not be presented as a published one — and must not then
    #: be used to check them, which is why `reconciles` degrades for that document.
    mro_kilograms: int | None = None
    mro_derived: bool = False
    mh_payload_kilograms: int | None = None
    #: Seats and berths as the document states them, where it states them on one line.
    #: Used to check the model page, not to replace it — the two 2023 catalogues put
    #: their berth count on a page whose labels and values are separate blocks.
    seats: int | None = None
    berths_published: str | None = None
    #: The chassis, read from the document because two of the eight model pages omit the
    #: `Drive:` row: Brownie's and City Pro's Technical info blocks start at `Length`.
    #: Every Wingamm is a Fiat Ducato and every document says so, so the catalogue is the
    #: reliable half of this pair even though the page is the more specific one.
    base_vehicle_manufacturer: str | None = None

    @property
    def berths(self) -> int | None:
        return _leading_int(self.berths_published) if self.berths_published else None


def parse_spec(text: str) -> WingammSpec:
    """The technical block of one catalogue.

    `text` is the whole document. The block is found by label rather than by page, since
    the three Oasi catalogues put it on pages 42-47 and the two older ones on page 13,
    and every label is unique within a document.
    """
    mtplm = _row(text, _MTPLM_LABELS, "KG")
    mro = _row(text, _MRO_LABELS, "KG")
    payload = _row(text, _PAYLOAD_LABELS, "KG")

    mtplm_kg = _integer(mtplm) if mtplm else None
    mro_kg = _integer(mro) if mro else None
    payload_kg = _integer(payload) if payload else None

    # The 540.1 catalogue omits the mass in running order. Deriving it from the two
    # figures it does publish is legitimate — both are published, and FMLV's own 2845
    # is exactly this subtraction — but it is flagged so the provenance can say so.
    derived = False
    if mro_kg is None and mtplm_kg is not None and payload_kg is not None:
        mro_kg = mtplm_kg - payload_kg
        derived = True

    return WingammSpec(
        mh_length_mm=_integer(length) if (length := _row(text, (r"External length",), "MM")) else None,
        mh_width_mm=_integer(width) if (width := _row(text, (r"External width",), "MM")) else None,
        mh_height_mm=_integer(height) if (height := _row(text, (r"External height",), "MM")) else None,
        mtplm_kilograms=mtplm_kg,
        mro_kilograms=mro_kg,
        mro_derived=derived,
        mh_payload_kilograms=payload_kg,
        seats=_leading_int(seats) if (seats := _published(text, _SEAT_LABELS)) else None,
        berths_published=_published(text, _BERTH_LABELS),
        base_vehicle_manufacturer="Fiat" if re.search(r"FIAT\s*DUCATO", text, re.I) else None,
    )


def parse_layout_prices(text: str) -> dict[str, int]:
    """Each layout's starting price in euro, keyed by squashed model name.

    Narrated, never emitted — see the module docstring. Missing prices are not an error:
    the Brownie and City Pro catalogues carry none at all, their price lists being
    Italian-only.
    """
    prices: dict[str, int] = {}
    for pattern in (_PRICE_TRAILING, _PRICE_LEADING):
        for match in pattern.finditer(text):
            euros = _integer(match.group("euros"))
            key = _squash(match.group("model"))
            if euros is not None and key:
                prices.setdefault(key, euros)
    return prices


def price_for(model: str, prices: dict[str, int]) -> int | None:
    """One layout's euro price, matched by prefix on the squashed name.

    Prefix rather than equality, because the document and FMLV do not name the vehicle
    identically: the catalogue's page reads `OASI 540.1` where FMLV's model is `540`. An
    ambiguous match yields `None` rather than a guess — though since this figure is only
    ever narrated, the cost of a miss is a less informative log line, not bad data.
    """
    wanted = f"OASI{_squash(model)}"
    matched = [euros for key, euros in prices.items() if key.startswith(wanted)]
    return matched[0] if len(matched) == 1 else None


#: The chassis row. Six pages call it `Drive`, Brownie's and City Pro's call it `Tractor`
#: — the Italian *motrice* translated a second way. Knowing only the first loses the base
#: vehicle on exactly the two products whose catalogue never spells out `FIAT DUCATO`.
_PAGE_DRIVE_LABELS = ("Drive", "Tractor")

#: The mass row, and which catalogue figure it checks. Seven pages publish `Total mass`,
#: which is the maximum laden weight; City Pro's publishes `Mass in running order`
#: instead. Reading only the first leaves City Pro with no cross-document check at all,
#: which matters because a mass is the one figure here worth checking twice.
_PAGE_MASS_LABELS = ("Total mass", "Mass in running order")


@dataclass(frozen=True)
class WingammPage:
    """What one layout's own page contributes: its identity-independent counts."""

    seats: int | None = None
    berths_published: str | None = None
    length_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    base_vehicle_manufacturer: str | None = None

    @property
    def berths(self) -> int | None:
        return _leading_int(self.berths_published) if self.berths_published else None


def _page_figure(html: str, label: str) -> str | None:
    """The value of one labelled row of a Technical info list, in either rendering.

    The first match wins, which matters on the 610 GL and 610 M pages: both carry the
    block twice, once giving `Length: 6,100 mm` and once `Length: 6.103 mm`. Either is
    within `LENGTH_TOLERANCE_MM` of the catalogue's 6103, and length is only ever a
    cross-check here, so taking the first is safe rather than merely convenient.
    """
    match = re.search(_PAGE_FIGURE.format(label=re.escape(label)), html, re.IGNORECASE)
    return unescape(match.group(1)).strip() if match else None


def parse_model_page(html: str) -> WingammPage:
    """Seats, berths, length, total mass and base vehicle from one layout's page.

    Seats and berths are taken from here for **every** layout rather than from the
    catalogue, so that all eight are read the same way. The catalogues' own inline
    figures then check this rather than substitute for it. The alternative — reading
    Brownie's and City Pro's berths from their catalogue's second technical page — means
    pairing a block of 22 labels with a block of 21 values by position, which is the
    silent misalignment `docs/adapters/README.md` forbids.

    Length and total mass are read only as the cross-document check. Width and height are
    deliberately *not*, because the site's figures for those are wrong — module docstring.
    """
    # `Drive: FIAT DUCATO EURO 6D Final` -> `Fiat`, which is what FMLV holds in
    # `base_vehicle_manufacturer` for all eight products. Every Wingamm is a Ducato, and
    # `DUCATO` is required rather than `FIAT` alone: the City Pro catalogue's only
    # mention of Fiat is `Body-coloured FIAT front bumper`, which is a bumper.
    drive = next((value for label in _PAGE_DRIVE_LABELS if (value := _page_figure(html, label))), None)
    mass_label = next((label for label in _PAGE_MASS_LABELS if _page_figure(html, label)), None)
    mass = _integer(re.sub(r"\s*k?g\b.*", "", _page_figure(html, mass_label) or "", flags=re.I)) if mass_label else None

    return WingammPage(
        seats=_leading_int(seats) if (seats := _page_figure(html, "Travel seats")) else None,
        berths_published=(
            re.sub(r"\s+", "", sleeps) if (sleeps := _page_figure(html, "Sleeps")) else None
        ),
        length_mm=_integer(re.sub(r"\s*mm\b.*", "", length, flags=re.I))
        if (length := _page_figure(html, "Length"))
        else None,
        mtplm_kilograms=mass if mass_label == "Total mass" else None,
        mro_kilograms=mass if mass_label == "Mass in running order" else None,
        base_vehicle_manufacturer="Fiat" if drive and "DUCATO" in drive.upper() else None,
    )


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WingammProduct:
    """One layout: its declared identity, its catalogue's numbers, and its page's counts."""

    fmlv_range: str
    model: str
    slug: str
    document_label: str
    spec: WingammSpec
    page: WingammPage
    body_type: BodyType | None
    #: The range this vehicle should be filed under, where that differs from
    #: `fmlv_range` and cannot be proposed. See `_UNDELIVERABLE`.
    intended_range: str | None = None

    @property
    def label(self) -> str:
        return f"{self.fmlv_range} {self.model}"

    @property
    def berths(self) -> int | None:
        return self.page.berths

    @property
    def seats(self) -> int | None:
        return self.page.seats

    @property
    def base_vehicle_manufacturer(self) -> str | None:
        """The chassis, from the layout's page if it names one, else its catalogue.

        Brownie's and City Pro's pages omit the `Drive:` row that the six Oasi pages
        carry, so page-only would leave two of eight products without a base vehicle FMLV
        already holds — and a blank there reads as "Wingamm stopped saying", not "this
        page never said".
        """
        return self.page.base_vehicle_manufacturer or self.spec.base_vehicle_manufacturer


def reconciles(product: WingammProduct) -> tuple[bool, str | None]:
    """Whether a layout's figures are consistent enough to propose, and why not if not.

    Wingamm publish the arithmetic against themselves — maximum laden weight, mass in
    running order *and* payload — so the identity `payload == MTPLM - MRO` is a free check
    on the parse, and it holds exactly on the 610, 690, Brownie and City Pro documents.
    That is the check that matters: it is what catches a mass read out of the wrong row,
    which is the one failure here that would otherwise produce a plausible vehicle.

    **The 540.1 catalogue publishes no MRO**, so its MRO is derived from the other two and
    the identity becomes vacuous. For that document the check falls back to the
    cross-document form — the layout's own page republishes total mass, seats and berths,
    and those are compared with the catalogue instead. `docs/adapters/README.md` sets the
    precedent with Rimor: where a document has no internal arithmetic, find a second that
    says the same thing twice.

    Both halves are applied to every product, not just the 540.1. The cross-document
    check is cheap and it is the only thing that would catch a document being paired with
    the wrong range's layouts.
    """
    spec, page = product.spec, product.page

    for what, from_catalogue, from_page in (
        ("maximum laden weight", spec.mtplm_kilograms, page.mtplm_kilograms),
        ("mass in running order", spec.mro_kilograms, page.mro_kilograms),
    ):
        if None not in (from_catalogue, from_page) and from_catalogue != from_page:
            return False, (
                f"catalogue says {from_catalogue}kg {what} but the model page says {from_page}kg"
            )

    if spec.seats is not None and page.seats is not None and spec.seats != page.seats:
        return False, (
            f"catalogue says {spec.seats} seats but the model page says {page.seats}"
        )

    if spec.berths is not None and page.berths is not None and spec.berths != page.berths:
        return False, (
            f"catalogue says {spec.berths_published} berths but the model page says "
            f"{page.berths_published}"
        )

    mtplm, mro, payload = spec.mtplm_kilograms, spec.mro_kilograms, spec.mh_payload_kilograms
    if mtplm is not None and mro is not None:
        if mtplm <= mro:
            return False, f"maximum laden weight {mtplm}kg is not above the {mro}kg running order"
        if not MIN_PAYLOAD_KG <= mtplm - mro <= MAX_PAYLOAD_KG:
            return False, f"implied payload {mtplm - mro}kg is outside {MIN_PAYLOAD_KG}-{MAX_PAYLOAD_KG}kg"
    if (
        not spec.mro_derived
        and None not in (mtplm, mro, payload)
        and mtplm - mro != payload  # type: ignore[operator]
    ):
        return False, (
            f"{mtplm}kg - {mro}kg = {mtplm - mro}kg does not match the published "  # type: ignore[operator]
            f"{payload}kg payload"
        )
    return True, None


def length_warning(product: WingammProduct) -> str | None:
    """A note where page and catalogue disagree on length by more than a rounding.

    Not a reason to drop anything: the 610 GL and 610 M pages carry `6,100 mm` and
    `6.103 mm` in two different blocks against the catalogue's 6.103, which is marketing
    rounding of the same vehicle.
    """
    spec_length, page_length = product.spec.mh_length_mm, product.page.length_mm
    if spec_length is None or page_length is None:
        return None
    if abs(spec_length - page_length) <= LENGTH_TOLERANCE_MM:
        return None
    return (
        f"length disagrees: catalogue {spec_length}mm against {page_length}mm on the "
        f"model page — taking the catalogue's"
    )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(
    product: WingammProduct, document_url_: str, page_url: str
) -> ExtractedMotorhome:
    spec, page = product.spec, product.page
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.fmlv_range,
        model=product.model,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        berths=product.berths,
        mh_passenger_seats_inc_driver=product.seats,
        mro_kilograms=spec.mro_kilograms,
        mtplm_kilograms=spec.mtplm_kilograms,
        mh_payload_kilograms=spec.mh_payload_kilograms,
        mh_length_mm=spec.mh_length_mm,
        mh_width_mm=spec.mh_width_mm,
        mh_height_mm=spec.mh_height_mm,
        body_type=product.body_type,
    )

    catalogue = f"{product.document_label} catalogue"
    provenance: dict[str, Provenance] = {}

    def record(field: str, url: str, snippet: str) -> None:
        provenance[field] = Provenance(source_url=url, snippet=f"{product.label} — {snippet}")

    # Both halves of the identity, together. FMLV files City Pro under range "Campervan"
    # and Brownie under range "Coach Built low profile" — a body type in the range column
    # — and the requester confirmed on 26 August 2026 that the ranges are Brownie, City
    # Pro and Oasi. `docs/adapters/README.md`: propose both halves or neither, because
    # accepting a range rename alone leaves the other column behind and corrupts the name.
    #
    # Where the correction cannot be delivered at all, *neither* half gets provenance, so
    # neither is compared and nothing is proposed — the emitted range is FMLV's own and
    # the product matches its row untouched. See `_UNDELIVERABLE`.
    if product.intended_range is None:
        identity = (
            f"range {product.fmlv_range!r} + model {product.model!r}. These two belong "
            f"together — accept both or neither. Wingamm publish this vehicle as "
            f"'{product.slug}' in the {catalogue}"
        )
        record("manufacturer_range", MODELS_INDEX_URL, identity)
        record("model", MODELS_INDEX_URL, identity)

    if (chassis := product.base_vehicle_manufacturer) is not None:
        record(
            "base_vehicle_manufacturer",
            page_url if page.base_vehicle_manufacturer else document_url_,
            f"FIAT DUCATO -> {chassis}"
            + ("" if page.base_vehicle_manufacturer else f", from the {catalogue} (this page states no Drive row)"),
        )
    if product.seats is not None:
        record("mh_passenger_seats_inc_driver", page_url, f"Travel seats: {product.seats}")
    if product.berths is not None:
        # The published wording, not the parsed integer: a reviewer seeing `3` needs to
        # know Wingamm printed `3+1`, and that the fourth berth is the optional dinette
        # conversion sold separately in the price list.
        record(
            "berths",
            page_url,
            f"Sleeps: {page.berths_published} -> {product.berths} as standard"
            + (" (the +1 is the optional dinette bed)" if "+" in (page.berths_published or "") else ""),
        )

    for field, row, value in (
        ("mh_length_mm", "External length", spec.mh_length_mm),
        ("mh_width_mm", "External width", spec.mh_width_mm),
        ("mh_height_mm", "External height", spec.mh_height_mm),
        ("mtplm_kilograms", "maximum laden weight", spec.mtplm_kilograms),
        ("mh_payload_kilograms", "Payload", spec.mh_payload_kilograms),
    ):
        if value is not None:
            record(field, document_url_, f"{catalogue}, {row}: {value}")

    # Width and height say out loud that they come from the PDF against the website,
    # because that inverts the house rule and a reviewer should see the reason.
    for field in ("mh_width_mm", "mh_height_mm"):
        if field in provenance:
            provenance[field] = Provenance(
                source_url=document_url_,
                snippet=(
                    f"{provenance[field].snippet}. Taken from the catalogue rather than "
                    f"the website, which contradicts itself here — the index cards say "
                    f"2248x3020 for every Oasi, the 540.1 and 610 ST pages 2248x2961, the "
                    f"610 GL and 610 M pages 2240x3030, and the 690 pages omit both"
                ),
            )

    if spec.mro_kilograms is not None:
        record(
            "mro_kilograms",
            document_url_,
            f"derived: {spec.mtplm_kilograms}kg maximum laden weight - "
            f"{spec.mh_payload_kilograms}kg payload = {spec.mro_kilograms}kg, because the "
            f"{catalogue} publishes no mass in running order for this range"
            if spec.mro_derived
            else f"{catalogue}, mass in running order: {spec.mro_kilograms}kg",
        )

    if product.body_type is not None:
        record("body_type", MODELS_INDEX_URL, f"{product.body_type.value} — {_BODY_TYPE_NOTE}")

    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def _fetch_text(http: Fetcher, url: str, label: str, on_progress: Callable[[str], None]) -> str | None:
    result = http.fetch(url)
    if result.status_code != 200:
        on_progress(f"[{label}] SKIPPED: {url} returned {result.status_code}")
        return None
    return result.file_path.read_text(encoding="utf-8", errors="replace")


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Wingamm's data is in plain PDFs; see the docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect every Wingamm layout from the current per-range catalogues.

    A document that cannot be read is narrated and skipped rather than raised, so one
    replaced PDF does not cost the other four ranges. Only a download area that yields no
    documents at all is fatal, since without it nothing can be found.
    """
    results: list[ExtractedMotorhome] = []
    wanted = [label for _key, label in ranges]
    by_label = {document.label: document for document in _DOCUMENTS}

    on_progress(f"reading the download area at {DOWNLOAD_AREA_URL} ...")
    area_html = _fetch_text(http, DOWNLOAD_AREA_URL, "download area", on_progress)
    if area_html is None:
        msg = f"Wingamm's download area at {DOWNLOAD_AREA_URL} could not be fetched"
        raise RuntimeError(msg)
    documents = parse_download_area(area_html)
    if not documents:
        msg = (
            f"no documents found in Wingamm's download area at {DOWNLOAD_AREA_URL} — the "
            f"page structure has changed"
        )
        raise RuntimeError(msg)
    rows = count_download_rows(area_html)
    on_progress(f"download area lists {rows} documents, {len(documents)} of them readable")
    if rows != len(documents):
        on_progress(
            f"WARNING: {rows - len(documents)} download-area row(s) have a title but no "
            f"readable download link. One is expected (the logo and media kit); more than "
            f"that means the table's markup has changed"
        )

    # The roster check, gated on a full run. On a `--range` run it would report every
    # layout of every other range as missing, and a check that fires on correct runs
    # trains a reviewer to ignore it (Elddis, `docs/adapters/README.md`).
    if len(wanted) == len(_DOCUMENTS):
        index_html = _fetch_text(http, MODELS_INDEX_URL, "models index", on_progress)
        if index_html is None:
            on_progress("WARNING: the models index could not be read, so the roster is unchecked")
        else:
            roster = parse_roster(index_html)
            unmapped = unmapped_slugs(roster)
            on_progress(
                f"models index lists {len(roster)} model pages; "
                f"{len(roster) - len(unmapped)} known, {len(unmapped)} unrecognised"
            )
            for slug in unmapped:
                on_progress(
                    f"WARNING: the models index links /en/camper-caravan/{slug}/, which is "
                    f"neither collected nor a known exclusion — a new layout needs adding "
                    f"to _DOCUMENTS with the model string FMLV holds for it. No product "
                    f"proposed for it."
                )

    for _key, label in ranges:
        document = by_label[label]
        url, matched = document_url(documents, document.title_key)
        if url is None:
            on_progress(
                f"[{label}] SKIPPED: {'no' if not matched else len(matched)} download-area "
                f"titles match {document.title_key!r}"
                + (f" ({', '.join(matched)})" if matched else "")
            )
            continue

        on_progress(f"[{label}] downloading {url} ...")
        pdf = http.fetch(url)
        if pdf.status_code != 200:
            on_progress(f"[{label}] SKIPPED: the catalogue returned {pdf.status_code}")
            continue

        extracted = extract_text(pdf.file_path)
        if extracted.is_empty():
            on_progress(f"[{label}] SKIPPED: {url} has no extractable text")
            continue

        spec = parse_spec(extracted.text)
        if spec.mtplm_kilograms is None:
            on_progress(
                f"[{label}] SKIPPED: no maximum laden weight row found in the catalogue — "
                f"the technical block has moved or been relabelled"
            )
            continue
        if spec.mro_derived:
            on_progress(
                f"[{label}] the catalogue publishes no mass in running order; deriving it "
                f"as {spec.mtplm_kilograms} - {spec.mh_payload_kilograms} = "
                f"{spec.mro_kilograms}kg, so this range is checked against its model pages "
                f"instead of its own arithmetic"
            )

        prices = parse_layout_prices(extracted.text)

        for slug, model in document.layouts:
            page_url = f"{BASE_URL}/en/camper-caravan/{slug}/"
            page_html = _fetch_text(http, page_url, f"{label} {model}", on_progress)
            if page_html is None:
                continue
            page = parse_model_page(page_html)
            if page.seats is None and page.berths is None:
                on_progress(
                    f"[{label} {model}] SKIPPED: no Technical info block on {page_url} — "
                    f"seats and berths are both unreadable"
                )
                continue

            product = WingammProduct(
                fmlv_range=document.fmlv_range,
                model=model,
                slug=slug,
                document_label=label,
                spec=spec,
                page=page,
                body_type=document.body_type,
                intended_range=document.intended_range,
            )
            if document.intended_range is not None:
                on_progress(
                    f"[{product.label}] FMLV files this under range "
                    f"{document.fmlv_range!r}, which is a body type, not a range. It "
                    f"should be {document.intended_range!r}, but that {_UNDELIVERABLE}"
                )

            if product.base_vehicle_manufacturer is None:
                # City Pro is the one product where neither source names the chassis: its
                # page has no `Drive:` row and its catalogue says only `FIAT front
                # bumper`, which is a bumper. Matching that loosely would call a bumper a
                # base vehicle, so the field is left unproposed — FMLV's `Fiat` stands —
                # and the gap is said out loud rather than left to look like a parse miss.
                on_progress(
                    f"[{document.fmlv_range} {model}] no base vehicle stated on the page or "
                    f"in the catalogue; leaving FMLV's value alone"
                )

            ok, why = reconciles(product)
            if not ok:
                on_progress(f"[{product.label}] DROPPED: {why}")
                continue
            if (warning := length_warning(product)) is not None:
                on_progress(f"[{product.label}] WARNING: {warning}")

            euros = price_for(model, prices)
            on_progress(
                f"[{product.label}] collected: "
                f"{spec.mh_length_mm}x{spec.mh_width_mm}x{spec.mh_height_mm}mm, "
                f"{spec.mtplm_kilograms}kg, {product.berths} berths, {product.seats} seats"
                + (
                    f". Price NOT collected: the catalogue says € {euros:,} ex works, VAT "
                    f"excluded, and FMLV holds a UK importer price in pounds"
                    if euros is not None
                    else ". Price NOT collected: none published in English"
                )
            )
            results.append(_build_extracted_motorhome(product, url, page_url))

    return results
