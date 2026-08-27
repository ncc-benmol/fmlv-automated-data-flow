"""Coachman (coachman.co.uk) — the seventh adapter, motorhomes and campervans.

See `docs/adapters/coachman.md` for the full write-up. Coachman make caravans as well as
motorhomes, and the site separates the two completely — two WordPress post types, two
taxonomies, two sets of homepage sections — so the ~20 touring caravans are excluded by
simply never asking for them. See `DEFAULT_RANGES`.

**Identity and specification come from different systems and must be joined.** The two
pages a person would use are both useless to a parser: `/coachman-motorhomes/` renders no
products at all, and the per-model pages carry no numbers. Both are client-side rendered.
What works instead needs no browser:

* **Identity** — the open WordPress REST API. `/wp-json/wp/v2/motorhome` gives every
  product with its full title; `/wp-json/wp/v2/motorhome_model` gives the ranges, each
  with a `count` that doubles as a completeness check.
* **Specifications** — the **homepage**, which server-renders a card per product carrying
  price, berths, travelling seats, length, MTPLM and mass in running order.

The join is the trap. A motorhome card's heading is the **model number alone** — `545`,
`565`, `845` — and `545` belongs to both an Avventura (£110,725) and a Travel Master
(£133,030). Auto-Trail's two Expeditions at least differed in their numbering; here they
collide exactly, and Coachman's 2027 preview makes it worse by putting `565` on five
different vehicles. The range therefore comes from the **taxonomy term ID in the enclosing
section's class** (`listings--posts-2-motorhome-8` → term 8 → Travel Master), never from the
card, so the join key is the triple `(post type, term ID, model)`.

Not extracted, because Coachman publish them nowhere a run can reach: **width, height and
base vehicle manufacturer**. All three are in `schema.REQUIRED`, so they surface as
`missing_required` for a human rather than being guessed — see the missing-data rule in
`docs/adapters/README.md`. `body_type` is left unset for the same reason: the campervan rule
turns on roof height, and no height is published.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from html import unescape
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.coachman.co.uk"
MANUFACTURER = "Coachman"
MANUFACTURER_DISPLAY_NAME = "Coachman"

#: (WordPress post type, label). Unusually for this repo a "range" here is a *vehicle
#: family*, not a model range: Coachman's actual ranges (Avventura, Travel Master, Veloce…)
#: are discovered from the taxonomy at run time and must be, since Veloce appeared as a new
#: one between the survey and the build. What is stable enough to select on is the post
#: type, so `--range Campervans` runs the campervans and nothing else.
#:
#: **`caravan` is deliberately absent.** Coachman's ~20 touring caravans are a separate post
#: type and out of the prototype's scope; omitting it here is the whole of the exclusion.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("motorhome", "Motorhomes"),
    ("campervan", "Campervans"),
)

#: One product card on the homepage. Every product is rendered twice, so callers
#: deduplicate; the first occurrence wins.
_CARD = re.compile(r'<div class="listings--posts--grid[^"]*">(?P<body>.*?)</ul>', re.S)

#: A card's `<label><value>` pair. The values are `£110,725.00*`, `4`, `7996 mm`,
#: `4500 kg` — parsed per label below rather than by one shared pattern.
_FEATURE = re.compile(r"<span>(?P<label>[^<]+)</span>\s*<span>(?P<value>.*?)</span>", re.S)

#: The heading, which for a motorhome is the bare model number. Caravan headings also carry
#: a range logo `<img>`; stripping tags leaves the number either way.
_HEADING = re.compile(r"<h3[^>]*>(?P<text>.*?)</h3>", re.S)

#: The section a card sits in: `listings--posts-<n>-<post type>-<taxonomy term id>`. The
#: term ID is the only thing on the page that says which range a motorhome belongs to.
_SECTION = re.compile(
    r'class="listings--posts [^"]*listings--posts-\d+-(?P<kind>[a-z]+)-(?P<term>\d+)"'
)

#: Bounds on a plausible payload, in kg. Coachman's real spread is 480–1250 kg across the
#: six motorhomes. Wide enough not to reject a genuine outlier, tight enough to catch a
#: card's MTPLM having been paired with another card's running order.
MIN_PAYLOAD_KG = 100
MAX_PAYLOAD_KG = 2500

#: The base vehicle, which Coachman publish **nowhere a run can reach** — not on the cards,
#: not in the REST API, not on the model pages. It is in the 2027 preview spec sheet, a
#: document supplied by Coachman rather than fetched, so it is transcribed here.
#:
#: Keyed on the **range**, not the model, deliberately. That is the granularity Coachman
#: state it at, it is the safer assumption (a chassis belongs to a range, not a floorplan),
#: and it means the three models still unpublished — Sportivo 565 Compact, Sportivo 565
#: TRAQ, Travel Master 565 L — inherit the right chassis the moment they appear, with no
#: edit here. The Sportivo TRAQ keeps its range's Mercedes despite a different weight and a
#: 4x4 engine, which is the case that would have broken a per-model table.
#:
#: **This does not refresh itself.** If Coachman move a range to another chassis nothing
#: here will notice, so every use is narrated with the date it was read and the reviewer
#: sees the same in the provenance. Re-verify at each model-year changeover, and prefer
#: leaving the field blank to guessing at a range that is not listed.
_PREVIEW_SOURCE = "Coachman 2027 preview floorplan and spec sheet (v2.3), supplied by Coachman"
_PREVIEW_READ_ON = "17 August 2026"
_BASE_VEHICLE_BY_RANGE: dict[str, str] = {
    "Avventura": "Fiat",
    "Sportivo": "Mercedes",
    "Travel Master": "Mercedes",
    "Travel Master Imperial": "Mercedes",
    "Veloce": "Fiat",
}


def base_vehicle_for(range_label: str) -> str | None:
    """The base vehicle for a range, or `None` for a range not in the preview.

    `None` rather than a guess: an unlisted range is one Coachman have added since the
    preview was read, and inventing a chassis for it would be exactly the kind of
    plausible-but-unverified value the missing-data rule exists to prevent.
    """
    return _BASE_VEHICLE_BY_RANGE.get(range_label)


def _squash(value: str) -> str:
    """Uppercase alphanumerics only, for comparing a card heading with a model name."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _text(markup: str) -> str:
    """Tags stripped and whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(markup))).strip()


def _pounds(value: str) -> int | None:
    """`'£110,725.00*'` -> `110725`. The `*` footnotes the on-the-road basis."""
    match = re.search(r"([\d,]+(?:\.\d+)?)", value)
    return round(Decimal(match.group(1).replace(",", ""))) if match else None


def _kilograms(value: str) -> int | None:
    """`'4500 kg'` -> `4500`. Coachman are inconsistent about the space."""
    match = re.search(r"(\d[\d,]*)\s*kg", value, re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else None


def _millimetres(value: str) -> int | None:
    """`'7996 mm'` -> `7996`; `'6255mm / 20′ 6″'` -> `6255`.

    Anchored on the **first** figure, because caravan cards append the imperial equivalent
    and a pattern taking the last number would read a feet-and-inches digit as millimetres.
    """
    match = re.search(r"(\d[\d,]*)\s*mm", value, re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else None


def _count(value: str) -> int | None:
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


@dataclass(frozen=True)
class CoachmanCard:
    """One product's specifications, as rendered on the homepage."""

    kind: str  # the post type: "motorhome", "campervan", "caravan"
    term_id: int  # taxonomy term = the range
    model: str  # the heading, e.g. "545", "845", "VL 65"
    rrp_pounds: int | None = None
    berths: int | None = None
    mh_passenger_seats_inc_driver: int | None = None
    mh_length_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None

    @property
    def key(self) -> tuple[str, int, str]:
        """The join key — unique within a post type, unlike the model number alone."""
        return (self.kind, self.term_id, _squash(self.model))


@dataclass(frozen=True)
class CoachmanProduct:
    """One product from the REST API, once its homepage card has been attached."""

    kind: str
    term_id: int
    range_label: str
    model: str
    title: str
    slug: str
    card: CoachmanCard | None = None

    @property
    def label(self) -> str:
        return self.title

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.kind, self.term_id, _squash(self.model))

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload, which Coachman do not publish, derived from the two masses."""
        if self.card is None or self.card.mtplm_kilograms is None or self.card.mro_kilograms is None:
            return None
        return self.card.mtplm_kilograms - self.card.mro_kilograms


def _reconciles(product: CoachmanProduct) -> bool:
    """Whether the joined figures are consistent enough to propose.

    Coachman publish no payload, so there is no `payload == MTPLM - MRO` identity to lean
    on — the same position as Auto-Trail and Sunlight. What this catches is the failure the
    join actually threatens: a card's weights belonging to a different vehicle. Two
    motorhomes share the model number `545` and sit 400 kg and £22,000 apart, so a slipped
    term ID pairs one range's running order with another range's maximum weight.

    A product with no card at all does not reach here — `collect` skips it.
    """
    card = product.card
    if card is None:
        return False
    mtplm, mro = card.mtplm_kilograms, card.mro_kilograms
    if mtplm is None or mro is None:
        return True  # nothing to contradict; the gaps are reported as missing fields
    if mtplm <= mro:
        return False
    return MIN_PAYLOAD_KG <= mtplm - mro <= MAX_PAYLOAD_KG


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_ranges(payload: str) -> dict[int, str]:
    """Taxonomy term ID -> range name, from `/wp-json/wp/v2/<type>_model`.

    The name comes from the API rather than a mapping held here, so Coachman renaming or
    renumbering a range costs nothing — Veloce arrived as term 60 between the survey and
    the build and needed no code change.
    """
    return {int(term["id"]): str(term["name"]).strip() for term in json.loads(payload)}


def parse_range_counts(payload: str) -> dict[int, int]:
    """Taxonomy term ID -> the product count Coachman's own CMS reports for it.

    A completeness check the manufacturer maintains against themselves, per range, in a
    machine-readable field. See `collect`.
    """
    return {
        int(term["id"]): int(term["count"])
        for term in json.loads(payload)
        if term.get("count") is not None
    }


def _term_ids(entry: dict) -> list[int]:
    """A product's taxonomy term IDs, from the `<type>_model` key the endpoint provides."""
    for key, value in entry.items():
        if key.endswith("_model") and isinstance(value, list):
            return [int(term) for term in value]
    return []


def model_name(title: str, range_label: str) -> str:
    """`('Travel Master Imperial 845', 'Travel Master Imperial')` -> `'845'`.

    Coachman's titles are the range name followed by the model, so the range comes off as a
    whole prefix rather than word by word. That matters for the nested names: trimming
    `Travel Master` from `Travel Master Imperial 845` would leave `Imperial 845`, which
    then matches no card — the card is headed `845`. Longest match first, compared on
    alphanumerics so spacing and punctuation cannot spoil it.
    """
    squashed_range = _squash(range_label)
    words = title.split()
    for index in range(len(words), 0, -1):
        if _squash(" ".join(words[:index])) == squashed_range:
            remainder = " ".join(words[index:]).strip()
            return remainder or title.strip()
    return title.strip()


def parse_roster(payload: str, kind: str, ranges: dict[int, str]) -> list[CoachmanProduct]:
    """Every product of one post type, with its range resolved from the taxonomy.

    A product whose term is missing from `ranges` keeps an empty range label rather than
    being dropped, so `collect` can report it instead of the product silently vanishing.
    """
    products: list[CoachmanProduct] = []
    for entry in json.loads(payload):
        title = _text(str(entry.get("title", {}).get("rendered", "")))
        term_ids = _term_ids(entry)
        term_id = next((t for t in term_ids if t in ranges), term_ids[0] if term_ids else -1)
        range_label = ranges.get(term_id, "")
        products.append(
            CoachmanProduct(
                kind=kind,
                term_id=term_id,
                range_label=range_label,
                model=model_name(title, range_label) if range_label else title,
                title=title,
                slug=str(entry.get("slug", "")),
            )
        )
    return products


def parse_cards(homepage_html: str) -> dict[tuple[str, int, str], CoachmanCard]:
    """Every product card on the homepage, keyed by (post type, term ID, model).

    Each card's post type and range come from the enclosing section's class, which is the
    only place on the page identifying a motorhome's range — the heading is the bare model
    number. Cards are rendered twice per product; the first wins.
    """
    text = unescape(homepage_html)
    sections = [
        (match.start(), match.group("kind"), int(match.group("term")))
        for match in _SECTION.finditer(text)
    ]

    cards: dict[tuple[str, int, str], CoachmanCard] = {}
    for card in _CARD.finditer(text):
        preceding = [(kind, term) for pos, kind, term in sections if pos < card.start()]
        if not preceding:
            continue
        kind, term_id = preceding[-1]

        body = card.group("body")
        heading = _HEADING.search(body)
        model = _text(heading.group("text")) if heading else ""
        if not model:
            continue

        values = {
            _text(match.group("label")): _text(match.group("value"))
            for match in _FEATURE.finditer(body)
        }
        parsed = CoachmanCard(
            kind=kind,
            term_id=term_id,
            model=model,
            rrp_pounds=_pounds(values.get("Price", "")),
            berths=_count(values.get("Berths", "")),
            mh_passenger_seats_inc_driver=_count(values.get("Travelling seats", "")),
            mh_length_mm=_millimetres(values.get("Length", "")),
            mtplm_kilograms=_kilograms(values.get("MTPLM", "")),
            mro_kilograms=_kilograms(values.get("Mass In Running Order", "")),
        )
        cards.setdefault(parsed.key, parsed)
    return cards


def join_cards(
    products: list[CoachmanProduct], cards: dict[tuple[str, int, str], CoachmanCard]
) -> list[CoachmanProduct]:
    """Attach each product's card by exact key match on (post type, term ID, model).

    Equality, not a suffix or a fuzzy match: both sides come from Coachman's own data and
    the triple is unique within a post type. `565` alone is ambiguous across five vehicles
    in the 2027 range; `('motorhome', 8, '565')` is not.
    """
    return [replace(product, card=cards.get(product.key)) for product in products]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(
    product: CoachmanProduct, homepage_url: str, api_url: str
) -> ExtractedMotorhome:
    card = product.card
    assert card is not None  # `collect` skips products without one

    base_vehicle = base_vehicle_for(product.range_label)

    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        base_vehicle_manufacturer=base_vehicle,
        berths=card.berths,
        mh_passenger_seats_inc_driver=card.mh_passenger_seats_inc_driver,
        rrp_pounds=card.rrp_pounds,
        mtplm_kilograms=card.mtplm_kilograms,
        mro_kilograms=card.mro_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=card.mh_length_mm,
    )

    snippets = {
        "berths": ("Berths", card.berths),
        "mh_passenger_seats_inc_driver": ("Travelling seats", card.mh_passenger_seats_inc_driver),
        "mh_length_mm": ("Length", card.mh_length_mm),
        "mtplm_kilograms": ("MTPLM", card.mtplm_kilograms),
        "mro_kilograms": ("Mass In Running Order", card.mro_kilograms),
    }
    provenance = {
        field: Provenance(
            source_url=homepage_url,
            snippet=f"{product.title} — {row}: {value}",
        )
        for field, (row, value) in snippets.items()
        if value is not None
    }

    if card.rrp_pounds is not None:
        provenance["rrp_pounds"] = Provenance(
            source_url=homepage_url,
            snippet=(
                f"{product.title} — Price £{card.rrp_pounds:,}. Coachman's price list gives "
                f"this as the OTR Price (Inc. VAT), including First Registration, Vehicle "
                f"Excise Duty and Registration Plates, and excluding Northern Ireland"
            ),
        )
    if product.mh_payload_kilograms is not None:
        provenance["mh_payload_kilograms"] = Provenance(
            source_url=homepage_url,
            snippet=(
                f"{product.title} — derived: {card.mtplm_kilograms}kg MTPLM "
                f"- {card.mro_kilograms}kg mass in running order "
                f"= {product.mh_payload_kilograms}kg (Coachman publish no payload)"
            ),
        )
    if base_vehicle is not None:
        provenance["base_vehicle_manufacturer"] = Provenance(
            source_url=f"{BASE_URL}/",
            snippet=(
                f"{product.title} — {base_vehicle}, MANUALLY SOURCED from the "
                f"{_PREVIEW_SOURCE}, read on {_PREVIEW_READ_ON}, because Coachman publish "
                f"the base vehicle nowhere on the site. Recorded per range, not per model. "
                f"Not machine-readable and not refreshed by later runs — re-verify at the "
                f"next model-year changeover"
            ),
        )

    provenance["manufacturer_range"] = Provenance(
        source_url=api_url,
        snippet=(
            f"{product.title} — range '{product.range_label}' from taxonomy term "
            f"{product.term_id}. The homepage card is headed '{card.model}' alone, which is "
            f"not unique across ranges, so the range comes from the term, not the card"
        ),
    )
    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def _fetch_json(http: Fetcher, url: str, label: str, on_progress: Callable[[str], None]) -> str | None:
    result = http.fetch(url)
    if result.status_code != 200:
        on_progress(f"[{label}] SKIPPED: {url} returned {result.status_code}")
        return None
    return result.file_path.read_text(encoding="utf-8", errors="replace")


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Coachman needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect Coachman's motorhomes and campervans, excluding the touring caravans.

    One homepage fetch serves every product; the API is then two fetches per post type. A
    post type that cannot be read is narrated and skipped rather than raised, so the
    campervans failing does not cost the motorhomes.
    """
    homepage_url = f"{BASE_URL}/"
    on_progress(f"fetching {homepage_url} for the specification cards...")
    homepage = http.fetch(homepage_url)
    if homepage.status_code != 200:
        msg = f"Coachman homepage returned {homepage.status_code}; it is the only source of specifications"
        raise RuntimeError(msg)

    cards = parse_cards(homepage.file_path.read_text(encoding="utf-8", errors="replace"))
    on_progress(f"{len(cards)} specification card(s) found on the homepage")

    results: list[ExtractedMotorhome] = []

    for post_type, label in ranges:
        taxonomy_url = f"{BASE_URL}/wp-json/wp/v2/{post_type}_model?per_page=100"
        roster_url = f"{BASE_URL}/wp-json/wp/v2/{post_type}?per_page=100"

        on_progress(f"[{label}] reading the ranges from {taxonomy_url} ...")
        taxonomy = _fetch_json(http, taxonomy_url, label, on_progress)
        if taxonomy is None:
            continue
        ranges_by_id = parse_ranges(taxonomy)
        counts = parse_range_counts(taxonomy)
        on_progress(
            f"[{label}] {len(ranges_by_id)} range(s): "
            + ", ".join(f"{name} ({counts.get(term, '?')})" for term, name in ranges_by_id.items())
        )

        on_progress(f"[{label}] reading the roster from {roster_url} ...")
        roster = _fetch_json(http, roster_url, label, on_progress)
        if roster is None:
            continue
        products = join_cards(parse_roster(roster, post_type, ranges_by_id), cards)
        on_progress(f"[{label}] {len(products)} product(s) in the roster")

        # Say so every run: the base vehicle is transcribed from a document, not fetched,
        # so it cannot notice Coachman changing a chassis.
        named = {r for r in ranges_by_id.values() if base_vehicle_for(r) is not None}
        unnamed = {r for r in ranges_by_id.values() if base_vehicle_for(r) is None}
        if named:
            on_progress(
                f"[{label}] NOTE: base vehicle for {sorted(named)} taken from the "
                f"{_PREVIEW_SOURCE}, read on {_PREVIEW_READ_ON}. Coachman publish it nowhere "
                f"on the site, and that figure does not refresh itself — re-verify at the "
                f"next model-year changeover"
            )
        if unnamed:
            on_progress(
                f"[{label}] WARNING: no base vehicle known for {sorted(unnamed)}, so it is "
                f"left blank rather than guessed. Add the range to _BASE_VEHICLE_BY_RANGE "
                f"once Coachman state its chassis"
            )

        # Coachman's own CMS counts its products per range. A mismatch means the roster and
        # the taxonomy disagree, which is the manufacturer contradicting themselves rather
        # than a parse problem — but it is the only completeness check available, so say so.
        for term, expected in counts.items():
            found = sum(1 for product in products if product.term_id == term)
            if found != expected:
                on_progress(
                    f"[{label}] WARNING: taxonomy says {ranges_by_id.get(term, term)!r} has "
                    f"{expected} model(s) but {found} were found in the roster"
                )

        for product in products:
            if not product.range_label:
                on_progress(
                    f"[{label}] {product.title} — SKIPPED: its taxonomy term "
                    f"{product.term_id} is not a known range, so the range cannot be named"
                )
                continue
            if product.card is None:
                on_progress(
                    f"[{label}] {product.title} — SKIPPED: no specification card on the "
                    f"homepage for ({product.kind}, term {product.term_id}, "
                    f"'{product.model}'), so it has no price, weights or dimensions"
                )
                continue
            if not _reconciles(product):
                card = product.card
                on_progress(
                    f"[{label}] {product.title} — SKIPPED: weights don't reconcile "
                    f"(MTPLM {card.mtplm_kilograms}kg, running order {card.mro_kilograms}kg), "
                    f"so the card may belong to another vehicle"
                )
                continue
            results.append(_build_extracted_motorhome(product, homepage_url, roster_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
