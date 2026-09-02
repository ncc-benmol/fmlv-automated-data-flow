"""Etrusco (etrusco.com/gb/en) — the ninth adapter, an Erwin Hymer Group brand.

See `docs/adapters/etrusco.md` for the full write-up. Etrusco build motorhomes and campervans
only, so there is no caravan line to exclude.

**One source: the eight model family pages under `/gb/en/models/`.** Each carries everything
FMLV needs — price, berths, travelling seats, dimensions, chassis, both masses — in plain
server-rendered HTML. No JavaScript, no PDF, no login.

**Take the roster from the sitemap, because neither menu holds all eight.** `sitemap.xml`
lists every family page. The model overview at `/gb/en/modeloverview` lists seven of them and
omits `semi-integrated-ford`; the page navigation omits it too. The other two —
`CV-Model Plus` and `T-Model Base` — sit under a longer `/models/model-overview/` path and
would be missed by anything that assumed one URL shape. Between them that is twelve of the
twenty-eight layouts, so a roster taken from any single menu is short.

**The website deliberately overrules the downloadable price lists**, per the rule in
`docs/adapters/README.md`. Etrusco publish two UK price lists whose filenames read
`pricelist_2027_uk.pdf` and whose own footers say `ENG - 2027`, but the download page labels
them **2026** — the 2027 is an internal PIM asset code. They are a model year behind the
site: they lack the four Ford T-models it lists, and their weights are last season's.

**Etrusco is a "non-core" brand**: only a selection of the full European range is sold in the
UK, and the `/gb/en/` path *is* that selection. A short UK roster is the point, not a parse
failure, so it is never reconciled against a European one.

The one structural quirk: a family page renders its specifications as **paired tables** —
even-indexed tables hold the labels, odd-indexed ones the values, aligned by row. See
`parse_layouts`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from html import unescape
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance, fmlv_base_vehicle

BASE_URL = "https://www.etrusco.com"
MANUFACTURER = "Etrusco"
MANUFACTURER_DISPLAY_NAME = "Etrusco"

#: (path under `/gb/en/models/`, range label). All eight UK families, in the overview's order.
#:
#: Two path shapes, both real: six families sit directly under `/models/`, and `CV-Model Plus`
#: and `T-Model Base` under `/models/model-overview/` with a German-spelt slug. The list is
#: hardcoded from the sitemap rather than scraped from a menu because no menu carries all
#: eight — see the module docstring.
#:
#: The labels follow Etrusco's own convention, taken from the model overview cards: the range
#: is named for the layout prefix and the chassis or trim. `T-Model Ford` is the one label
#: Etrusco have not published themselves — that family appears in no menu — so it is named
#: consistently with `V-Model Ford` rather than invented freely.
#:
#: The page `<h1>`s are marketing lines ("Your semi-integrated Ford", "Your Ford-based Van")
#: and deliberately not used as range names.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("campervans-fiat", "CV-Model Fiat"),
    ("model-overview/cv-modelle-fiat_plus", "CV-Model Plus"),
    ("vans-ford", "V-Model Ford"),
    ("semi-integrated-fiat", "T-Model Fiat"),
    ("model-overview/t-modelle-fiat_base", "T-Model Base"),
    ("semi-integrated-ford", "T-Model Ford"),
    ("overcab-fiat", "A-Model Base"),
    ("integrated-fiat", "I-Model Fiat"),
)

#: The layout names, in the order the page renders their spec tables.
#:
#: `o-floorplan__subline` and not the slider's `o-floorplan__headline`: both carry the same
#: names, but the subline sits inside each layout's own content item, immediately beside the
#: `o-floorplan__data` block holding its tables. Anchoring on the subline is what keeps the
#: names in the same sequence as the tables they pair with.
#: Either quote style, because the site uses both: the `model-overview/` pages single-quote
#: their head attributes where the others double-quote them.
_LAYOUT_NAME = re.compile(
    r"""class=['"]o-floorplan__subline['"][^>]*>(?P<name>.*?)</h4>""", re.S
)

_TABLE = re.compile(r"<table.*?</table>", re.S)
_CELL = re.compile(r"<td[^>]*>(?P<cell>.*?)</td>", re.S)

#: Spec labels exactly as the page writes them, asterisks and all.
LABEL_PRICE = "Pricea)"
LABEL_DIMENSIONS = "Length | Width | Height (cm)"
LABEL_CHASSIS = "Chassis"
LABEL_MRO = "Mass in running order* (kg)"
LABEL_MTPLM = "Technically permissible maximum laden mass* (kg)"
LABEL_SEATS = "Permitted number of seats (including driver)*"
LABEL_BERTHS = "Sleeping places"

#: `Manufacturer-specified mass for optional equipment` sits between the two masses and is
#: **not** payload — it caps factory-fitted extras. Named here so the mistake is documented
#: rather than merely avoided; Sunlight's document carries the same field and the same hazard.
LABEL_NOT_PAYLOAD = "Manufacturer-specified mass for optional equipment* (kg)"

#: Body type from the range's model letter, which is Etrusco's own taxonomy: `I` integrated,
#: `T` semi-integrated, `A` alcove — and every layout carries the same letter as its range
#: (`I 6900 SB`, `T 7.3 SCF`, `A 6.9 DB`), so the letter is the manufacturer's own statement of
#: the body type rather than an inference from it.
#:
#: The letter, and not the URL path, because the paths disagree with each other about how to
#: name the same thing: `overcab-fiat` and `model-overview/t-modelle-fiat_base` are both real,
#: and a segment-based rule that worked on one shape returned nothing on the other.
_BODY_TYPES: dict[str, BodyType] = {
    "I": BodyType.A_CLASS,
    "T": BodyType.COACH_BUILT_LOW_PROFILE,
    "A": BodyType.COACH_BUILT_OVER_CAB_BED,
}

#: The model letters whose body type comes from the roof instead: `CV` campervans and `V` vans.
#: A campervan's type turns on its roof, per the rule in `docs/adapters/README.md` — see
#: `EtruscoLayout.body_type`.
CAMPERVAN_PREFIXES = ("CV", "V")

#: A campervan taller than this is a high top. Same threshold as `auto_trail` and `chausson`,
#: set by the NCC side from FMLV's own data: the tallest standard-height campervan is 2050mm.
HIGH_TOP_ABOVE_MM = 2300

#: Bounds on a plausible payload, in kg. Etrusco's real spread is 421–749 kg across the 28
#: layouts, every one on a 3500 kg chassis.
MIN_PAYLOAD_KG = 100
MAX_PAYLOAD_KG = 2000

#: How much the printed tolerance band may differ from the recomputed one. The band is the
#: mass ±5% rounded to whole kilograms, so a kilogram or two of slack is rounding, not error.
BAND_TOLERANCE_KG = 3


def _clean(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", unescape(markup))).strip()


def _pounds(value: str) -> int | None:
    """`'£67,100'` -> `67100`."""
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def _centimetres_to_mm(value: str) -> int | None:
    """`'698'` -> `6980`. Etrusco quote every dimension in whole centimetres."""
    match = re.search(r"\d+", value)
    return int(match.group(0)) * 10 if match else None


def _kilograms(value: str) -> int | None:
    """`'2799 (2659 - 2939)*'` -> `2799`, the nominal mass before its tolerance band."""
    match = re.search(r"\d[\d\s]*", value)
    return int(re.sub(r"\D", "", match.group(0))) if match else None


def _band(value: str) -> tuple[int, int] | None:
    """`'2799 (2659 - 2939)*'` -> `(2659, 2939)`, the legally permissible ±5% range."""
    match = re.search(r"\(\s*(\d+)\s*-\s*(\d+)\s*\)", value)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _standard_count(value: str) -> int | None:
    """The standard figure of a published count.

    Etrusco write berths as `2 - 5 OPT`, meaning two as built and up to five with optional
    equipment. Per the data rules in `docs/adapters/README.md` the lower figure is recorded and
    the published string is carried into the provenance.
    """
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


@dataclass(frozen=True)
class EtruscoLayout:
    """One layout, as read from its family page.

    `range_label` is the family Etrusco market it under — `CV-Model Plus`, `T-Model Ford` — and
    `model` is the name as published, `CV 640 SB+`. **Neither is what goes into FMLV**: see
    `fmlv_range` and `fmlv_model`.
    """

    family: str
    range_label: str
    model: str
    rrp_pounds: int | None = None
    berths_published: str | None = None
    seats_published: str | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None
    mro_band: tuple[int, int] | None = None
    base_vehicle_manufacturer: str | None = None

    @property
    def label(self) -> str:
        return f"{self.range_label} {self.model}".strip()

    @property
    def model_letter(self) -> str:
        """`CV` from `CV 640 SB+` — Etrusco's own taxonomy, carried in the vehicle's own name."""
        return self.model.split(" ", 1)[0].strip()

    @property
    def fmlv_range(self) -> str:
        """The range as FMLV records it: the bare model letter.

        Checked against the real FMLV export for id 45 (54 products, 19 August 2026), which
        stores `manufacturer_range` as `CV`, `V`, `T`, `A` or `I` — not as the marketing family
        name. The join back to existing product IDs is a fuzzy match on range plus model, so
        proposing `CV-Model Plus` here would both weaken every match and propose renaming the
        range on all 27 of the 2026 products.

        The family is not lost: it is in the provenance of every field, and the chassis it
        encodes is in `base_vehicle_manufacturer`.
        """
        return self.model_letter

    @property
    def fmlv_model(self) -> str:
        """The model as FMLV records it: the published name without its range letter.

        `CV 640 SB+` -> `640 SB+`, matching the export's `640 SB +` closely enough for the
        matcher, which compares word bags and ignores punctuation.
        """
        parts = self.model.split(" ", 1)
        return parts[1].strip() if len(parts) > 1 else self.model

    @property
    def berths(self) -> int | None:
        return _standard_count(self.berths_published) if self.berths_published else None

    @property
    def mh_passenger_seats_inc_driver(self) -> int | None:
        return _standard_count(self.seats_published) if self.seats_published else None

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload, which Etrusco do not publish, as `MTPLM - MRO`.

        This is the presentation FMLV wants, confirmed by the NCC side on 19 August 2026 in
        the knowledge that other derivations exist. In particular Etrusco's own table offers
        two tempting alternatives that are **not** payload: the manufacturer-specified mass for
        optional equipment, and the mass of the passengers their notes describe deducting.
        """
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms

    @property
    def body_type(self) -> BodyType | None:
        """From the range's model letter, except the campervans, which come from the roof.

        `I-Model` -> A class, `T-Model` -> coach built low profile, `A-Model` -> coach built
        over cab bed. The `CV-` and `V-Model` ranges instead use the roof-height rule, since a
        campervan's type is a property of its roof and not of the range it sits in. Etrusco's
        campervans are 270cm and its Ford vans 287cm, both well above the high-top threshold.

        A range letter that is not one of the five is a blank, not the nearest known type.
        """
        prefix = self.model_letter
        if prefix in CAMPERVAN_PREFIXES:
            if self.mh_height_mm is None:
                return None
            if self.mh_height_mm > HIGH_TOP_ABOVE_MM:
                return BodyType.CAMPERVAN_HIGH_TOP
            return BodyType.CAMPERVAN
        return _BODY_TYPES.get(prefix)


def _band_reconciles(layout: EtruscoLayout) -> bool:
    """Whether the printed tolerance band matches the mass it belongs to.

    Etrusco print the mass in running order with its legally permissible ±5% range in
    brackets: `2799 (2659 - 2939)`. The band is a **function of the mass**, so the pair must be
    self-consistent — which makes it a free test that both were read from the same column. A
    slipped column pairs one layout's mass with another's band and fails.

    The same device Sunlight uses, and the only arithmetic self-check available here, since
    Etrusco publish no payload. A few kilograms of slack is allowed because the band is
    printed rounded to whole kilograms.
    """
    if layout.mro_kilograms is None or layout.mro_band is None:
        return True  # nothing to contradict
    low, high = layout.mro_band
    expected_low = Decimal(layout.mro_kilograms) * Decimal("0.95")
    expected_high = Decimal(layout.mro_kilograms) * Decimal("1.05")
    return (
        abs(Decimal(low) - expected_low) <= BAND_TOLERANCE_KG
        and abs(Decimal(high) - expected_high) <= BAND_TOLERANCE_KG
    )


def _reconciles(layout: EtruscoLayout) -> bool:
    """Whether a layout is consistent enough to propose."""
    if not _band_reconciles(layout):
        return False
    mtplm, mro = layout.mtplm_kilograms, layout.mro_kilograms
    if mtplm is None or mro is None:
        return True
    if mtplm <= mro:
        return False
    return MIN_PAYLOAD_KG <= mtplm - mro <= MAX_PAYLOAD_KG


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_layout_names(family_html: str) -> list[str]:
    """The layout names in the order the page renders their spec tables.

    Order matters: it is what pairs a name with a table, so this must not be sorted or
    de-duplicated into a different sequence.
    """
    seen: dict[str, None] = {}
    for match in _LAYOUT_NAME.finditer(family_html):
        seen.setdefault(re.sub(r"\s+", " ", _clean(match.group("name"))), None)
    return [name for name in seen if name]


def parse_spec_tables(family_html: str) -> list[dict[str, str]]:
    """One `{label: value}` mapping per layout, from the page's paired tables.

    A family page renders each layout's specification as **two** tables: the first holds the
    labels, one `<td>` per row, and the second the values in the same order. So tables pair up
    even-with-odd, and within a pair the two cell lists are zipped by position.

    Zipping *within* a pair is safe in a way that zipping across the whole page would not be:
    each pair is one layout's own table, and the two halves are generated from the same row
    list, so they cannot drift. A missing table would drop a layout rather than shift every
    subsequent one, and `collect` reconciles the count against the layout names.
    """
    tables = _TABLE.findall(family_html)
    specs: list[dict[str, str]] = []
    for index in range(0, len(tables) - 1, 2):
        labels = [_clean(c) for c in _CELL.findall(tables[index])]
        values = [_clean(c) for c in _CELL.findall(tables[index + 1])]
        if not labels or not values:
            continue
        specs.append({label: value for label, value in zip(labels, values) if label})
    return specs


def parse_layouts(family: str, range_label: str, family_html: str) -> list[EtruscoLayout]:
    """Every layout on one family page, names paired with spec tables by position."""
    names = parse_layout_names(family_html)
    specs = parse_spec_tables(family_html)

    layouts: list[EtruscoLayout] = []
    for name, spec in zip(names, specs):
        dimensions = spec.get(LABEL_DIMENSIONS, "").split("|")
        chassis = spec.get(LABEL_CHASSIS, "")
        mro_raw = spec.get(LABEL_MRO, "")
        layouts.append(
            EtruscoLayout(
                family=family,
                range_label=range_label,
                model=name,
                rrp_pounds=_pounds(spec.get(LABEL_PRICE, "")),
                berths_published=spec.get(LABEL_BERTHS) or None,
                seats_published=spec.get(LABEL_SEATS) or None,
                mh_length_mm=_centimetres_to_mm(dimensions[0]) if len(dimensions) > 0 else None,
                mh_width_mm=_centimetres_to_mm(dimensions[1]) if len(dimensions) > 1 else None,
                mh_height_mm=_centimetres_to_mm(dimensions[2]) if len(dimensions) > 2 else None,
                mtplm_kilograms=_kilograms(spec.get(LABEL_MTPLM, "")),
                mro_kilograms=_kilograms(mro_raw),
                mro_band=_band(mro_raw),
                base_vehicle_manufacturer=fmlv_base_vehicle(chassis.split()[0]) if chassis else None,
            )
        )
    return layouts


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(layout: EtruscoLayout, family_url: str) -> ExtractedMotorhome:
    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=layout.fmlv_range,
        model=layout.fmlv_model,
        base_vehicle_manufacturer=layout.base_vehicle_manufacturer,
        berths=layout.berths,
        mh_passenger_seats_inc_driver=layout.mh_passenger_seats_inc_driver,
        rrp_pounds=layout.rrp_pounds,
        mtplm_kilograms=layout.mtplm_kilograms,
        mro_kilograms=layout.mro_kilograms,
        mh_payload_kilograms=layout.mh_payload_kilograms,
        mh_length_mm=layout.mh_length_mm,
        mh_width_mm=layout.mh_width_mm,
        mh_height_mm=layout.mh_height_mm,
        body_type=layout.body_type,
    )

    provenance: dict[str, Provenance] = {}

    def record(field: str, snippet: str) -> None:
        provenance[field] = Provenance(source_url=family_url, snippet=f"{layout.label} — {snippet}")

    if layout.rrp_pounds is not None:
        record(
            "rrp_pounds",
            f"£{layout.rrp_pounds:,}, shown against this layout alone in its own "
            f"specification table. A price against one specific model is usable as the FMLV "
            f"guide price; the range-level 'Price from' figures on the model overview are not",
        )
    if layout.berths is not None:
        record("berths", f"Sleeping places '{layout.berths_published}', standard figure {layout.berths}")
    if layout.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            f"Permitted number of seats (including driver): {layout.seats_published}",
        )
    for field, value, name in (
        ("mh_length_mm", layout.mh_length_mm, "Length"),
        ("mh_width_mm", layout.mh_width_mm, "Width"),
        ("mh_height_mm", layout.mh_height_mm, "Height"),
    ):
        if value is not None:
            record(field, f"{name} {value / 10:.0f}cm from 'Length | Width | Height (cm)'")
    if layout.mtplm_kilograms is not None:
        record("mtplm_kilograms", f"Technically permissible maximum laden mass: {layout.mtplm_kilograms}kg")
    if layout.mro_kilograms is not None:
        band = f" (permissible range {layout.mro_band[0]} - {layout.mro_band[1]}kg, ±5%)" if layout.mro_band else ""
        record("mro_kilograms", f"Mass in running order: {layout.mro_kilograms}kg{band}")
    if layout.base_vehicle_manufacturer is not None:
        record("base_vehicle_manufacturer", f"Chassis: {layout.base_vehicle_manufacturer}")
    if layout.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            f"derived: {layout.mtplm_kilograms}kg maximum laden - {layout.mro_kilograms}kg "
            f"running order = {layout.mh_payload_kilograms}kg. Etrusco publish no payload, and "
            f"their 'manufacturer-specified mass for optional equipment' is not one",
        )
    if layout.body_type is not None:
        record(
            "body_type",
            f"from the '{layout.range_label}' model letter"
            + (
                f", with the {layout.mh_height_mm}mm roof deciding between a campervan and a "
                f"high top (the threshold is {HIGH_TOP_ABOVE_MM}mm)"
                if layout.model_letter in CAMPERVAN_PREFIXES
                else ""
            ),
        )
    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Etrusco needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect Etrusco's UK range from the six model family pages, one fetch each.

    A family that cannot be read is narrated and skipped rather than raised, so one rebuilt
    page does not cost the other five.
    """
    results: list[ExtractedMotorhome] = []

    for family, range_label in ranges:
        family_url = f"{BASE_URL}/gb/en/models/{family}"
        on_progress(f"[{range_label}] fetching {family_url} ...")
        page = http.fetch(family_url)
        if page.status_code != 200:
            on_progress(f"[{range_label}] SKIPPED: {family_url} returned {page.status_code}")
            continue

        family_html = page.file_path.read_text(encoding="utf-8", errors="replace")
        names = parse_layout_names(family_html)
        specs = parse_spec_tables(family_html)
        if not names or not specs:
            on_progress(f"[{range_label}] SKIPPED: no layouts or no specification tables found")
            continue

        # The names and the tables are paired by position, so a mismatch means the page has
        # changed shape and the pairing can no longer be trusted for any layout on it.
        if len(names) != len(specs):
            on_progress(
                f"[{range_label}] SKIPPED: {len(names)} layout name(s) but {len(specs)} "
                f"specification table(s), so names cannot be paired with specs by position"
            )
            continue

        layouts = parse_layouts(family, range_label, family_html)
        on_progress(f"[{range_label}] {len(layouts)} layout(s): {[l.model for l in layouts]}")

        for layout in layouts:
            if not _band_reconciles(layout):
                on_progress(
                    f"[{layout.label}] SKIPPED: the printed tolerance band "
                    f"{layout.mro_band} is not ±5% of the {layout.mro_kilograms}kg running "
                    f"order, so the two may have come from different columns"
                )
                continue
            if not _reconciles(layout):
                on_progress(
                    f"[{layout.label}] SKIPPED: masses don't reconcile (maximum laden "
                    f"{layout.mtplm_kilograms}kg, running order {layout.mro_kilograms}kg)"
                )
                continue
            for field, value in (
                ("price", layout.rrp_pounds),
                ("berths", layout.berths),
                ("length", layout.mh_length_mm),
                ("maximum laden mass", layout.mtplm_kilograms),
            ):
                if value is None:
                    on_progress(f"[{layout.label}] WARNING: no {field} published, left blank")
            results.append(_build_extracted_motorhome(layout, family_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
