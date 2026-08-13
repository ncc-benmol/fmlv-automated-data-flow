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

Not extracted: price. Auto-Trail's price and options list is a rasterised image — the
whole of page 2 extracts to four text runs, none of them a price — so there is no
machine-readable price to propose, as for Swift and Rimor.
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
from .base import ExtractedMotorhome, Provenance

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
#: `body_type` is deliberately left unset rather than guessed — all four are 2680mm
#: high-roof conversions, but Adventure fits an elevating pop-top as standard and
#: whether FMLV counts that as `campervan_elevating_roof` or `campervan_high_top` is a
#: judgement for a reviewer, not for a parser.
_BODY_STYLES: tuple[tuple[str, BodyType], ...] = (
    ("a-class", BodyType.A_CLASS),
    # "Hi-Line ... with over cab bed area" is an over-cab bed; "Lo-Line ... with over
    # cab storage area" is not, despite also mentioning "over cab". Order matters:
    # check for the storage variant before the generic "over cab".
    ("over cab storage", BodyType.COACH_BUILT_LOW_PROFILE),
    ("low profile", BodyType.COACH_BUILT_LOW_PROFILE),
    ("over cab bed", BodyType.COACH_BUILT_OVER_CAB_BED),
)

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


def _leading_kilograms(value: str) -> int:
    """`'3500/3650/4400'` -> `3500`.

    Auto-Trail lists the standard build first and chassis upgrades after it — the Imala
    736 offers all three of 3500, 3650 and 4400 kg. FMLV carries one MTPLM, and it is
    the standard one.
    """
    return int(value.split("/")[0].replace(",", ""))


def _leading_int(value: str) -> int:
    """`'2-4'` -> `2`, the standard build.

    Used for seat belts. Auto-Trail writes `Seatbelts 2-4 (inc. driver)` where the
    upper figure needs optional belts — their own copy for the C73 calls it "a
    six-berth, and *optional* six-belt motorhome" — so the lower figure is what the
    vehicle has as built.
    """
    return int(value.split("-")[0])


def _trailing_int(value: str) -> int:
    """`'4-6'` -> `6`, the maximum.

    Used for berths, on evidence rather than preference: the six documents that publish
    a separate `Max. No. of berths` row agree with the trailing figure of `Sleeps` on
    all 21 models, with no disagreement. It is also the figure Auto-Trail markets — the
    `Sleeps 4-6` C73 is sold as "truly a six-berth". Taking the trailing figure keeps
    one rule for all 37 layouts, including the 16 campervans whose documents have no
    `Max. No. of berths` row to consult.
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

    The `mm` unit is required rather than optional. The F-Line F74 publishes
    `Height 2880m` — a typo for 2880mm — and accepting a bare `m` would mean reading a
    figure whose unit the document got wrong. It stays unread, and `parse_models`
    narrates it so the gap is visible rather than silent.
    """
    match = re.search(rf"^{label}[^\n]*?(\d[\d,]*)mm\s*$", block, re.MULTILINE)
    return int(match.group(1).replace(",", "")) if match else None


def _dimension_row_present(block: str, label: str) -> bool:
    """Whether a dimension row exists at all, regardless of whether its value parsed."""
    return re.search(rf"^{label}\b", block, re.MULTILINE) is not None


def _count(block: str, label: str, *, take: Callable[[str], int]) -> int | None:
    match = re.search(rf"^{label}\s+(\d+(?:-\d+)?)", block, re.MULTILINE)
    return take(match.group(1)) if match else None


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
    #: `Max. No. of berths`, published by the six motorhome documents but by none of the
    #: four campervan ones. Not written to FMLV — `berths` already carries it — but kept
    #: as an independent confirmation of the berth count. See `_reconciles`.
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

    # The berth count is published twice by the motorhome documents — as the upper bound
    # of `Sleeps` and again as `Max. No. of berths`. They agree on all 21 models that
    # state both, so a disagreement means the block boundaries slipped and two models'
    # figures have been mixed.
    if product.stated_max_berths is not None and product.berths != product.stated_max_berths:
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


def _body_type(block: str) -> BodyType | None:
    match = re.search(r"^BODY STYLES\s*\n(.+)$", block, re.MULTILINE)
    if match is None:
        return None
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

        products.append(
            AutoTrailProduct(
                range_label=range_label,
                model=model,
                berths=_count(block, "Sleeps", take=_trailing_int),
                mh_passenger_seats_inc_driver=_count(block, "Seatbelts", take=_leading_int),
                mh_length_mm=dimensions["Length"],
                mh_width_mm=dimensions["Width"],
                mh_height_mm=dimensions["Height"],
                mtplm_kilograms=_leading_kilograms(mtplm) if mtplm else None,
                mro_kilograms=_leading_kilograms(mro) if mro else None,
                mgtw_kilograms=_leading_kilograms(mgtw) if mgtw else None,
                towing_kilograms=_leading_kilograms(towing) if towing else None,
                body_type=_body_type(block),
                base_vehicle_manufacturer=chassis.group(1) if chassis else None,
                stated_max_berths=_count(block, r"Max\. No\. of berths", take=_trailing_int),
                parse_warnings=warnings,
            )
        )

    return products


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(product: AutoTrailProduct, spec_url: str) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        base_vehicle_manufacturer=product.base_vehicle_manufacturer,
        berths=product.berths,
        mh_passenger_seats_inc_driver=product.mh_passenger_seats_inc_driver,
        mro_kilograms=product.mro_kilograms,
        mtplm_kilograms=product.mtplm_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=product.mh_length_mm,
        mh_width_mm=product.mh_width_mm,
        mh_height_mm=product.mh_height_mm,
        body_type=product.body_type,
    )

    snippets = {
        "berths": ("Sleeps", product.berths),
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


def _spec_pdf_for_range(
    http: Fetcher,
    path: str,
    label: str,
    on_progress: Callable[[str], None],
) -> str | None:
    """Find a range's spec PDF: range page -> a model page -> the `Tech-Spec` link.

    Every model in a range links the same document, so the first model page that yields
    one is enough. Later ones are still tried if an early page has been rebuilt without
    the link, which costs a fetch only in the case that would otherwise lose the range.
    """
    range_url = f"{BASE_URL}/{path}/"
    range_page = http.fetch(range_url)
    if range_page.status_code != 200:
        on_progress(f"[{label}] SKIPPED: {range_url} returned {range_page.status_code}")
        return None

    model_urls = find_model_urls(range_page.file_path.read_text(encoding="utf-8", errors="replace"))
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
        spec_url = _spec_pdf_for_range(http, path, label, on_progress)
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
            if not _towing_identity_holds(product):
                on_progress(
                    f"[{label}] {product.label} — WARNING: "
                    f"{product.mgtw_kilograms}kg gross train - {product.mtplm_kilograms}kg "
                    f"max gross != {product.towing_kilograms}kg max towing. Auto-Trail's own "
                    f"figures disagree; the weights below are still as published"
                )
            results.append(_build_extracted_motorhome(product, spec_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
