"""Chausson (motorhomes-chausson.co.uk) — the eighth adapter, French-built, UK range.

See `docs/adapters/chausson.md` for the full write-up. Chausson are part of Trigano VDL and
build motorhomes only, so there is no caravan line to exclude.

**Two sources on the same site, joined per model.** Both are plain server-rendered HTML —
no JavaScript, no PDF, no login:

* **The listing cards** on `/ranges/` carry price, berths, travelling seats, overall length
  and the base vehicle, one card per model.
* **The model page** at `/model/<slug>/` carries overall width, both heights, wheelbase,
  maximum laden mass and mass in running order, as an accordion of label/value rows.

The **UK site is the source and the global `.com` is not**. They are different ranges rather
than one being a subset of the other: the `.com` carries 25 models across 6 lines including a
whole A-class line Chausson do not sell here, and lacks the X650 slot the UK site links.
Running the `.com` would proposeseven vehicles unavailable in the UK.

Four traps, all of which produce plausible wrong numbers rather than errors:

1. **Labels and values do not come in matching numbers.** `/model/650/` has 26
   `caracteristique-nom` and 21 `caracteristique-valeur` — some rows carry a label and no
   value. Pairing the two lists positionally drifts and silently mis-assigns; rows are
   therefore read one `<li>` at a time. See `parse_rows`.
2. **A card's details follow its title.** Associating a details block with the nearest
   *preceding* title attributes the previous model's figures. Cards are read forward from the
   title to their own `/model/<slug>/` link. See `parse_cards`.
3. **Cells can hold two vehicles' figures.** `/model/640/` publishes `2.35 / 2.05` for width
   and `3007 / 3085` for running order, the second column belonging to a van. The leading
   figure is taken, per the base-vehicle rule in `docs/adapters/README.md`.
4. **A model page can be a soft 404.** `/model/x650/` returns HTTP 200 with the `/ranges/`
   page's title and no accordion at all. A page without characteristics is treated as absent.

The displayed model name is **not** unique — `x550` and `x640` render as `550` and `640`, and
`640` is also a Low profile. The slug is the identity, and the range comes from the model
page's `<h1>`, which reads `Low profiles 650`, `Vans V594`, `X X550`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from html import unescape
from pathlib import Path

from ..fetch.http import Fetcher
from ..product_model.enums import BodyType
from ..product_model.model import Motorhome
from .base import ExtractedMotorhome, Provenance

BASE_URL = "https://www.motorhomes-chausson.co.uk"
MANUFACTURER = "Trigano VDL Chausson"
MANUFACTURER_DISPLAY_NAME = "Chausson"

#: (line slug, label). Chausson's five UK lines. The label is what a reviewer sees as
#: `manufacturer_range` and what `--range` selects on.
#:
#: Filtering happens **after** each model page is fetched, not before, because the site
#: offers no per-line listing: every `/line/<slug>/` page links all of the models, so the
#: only statement of a model's line is the `<h1>` on its own page. `--range` therefore saves
#: parsing rather than fetching.
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (
    ("low-profiles", "Low profiles"),
    ("s-low-profiles", "S Low Profiles"),
    ("overcab", "Overcab"),
    ("vans", "Vans"),
    ("x", "X"),
)

#: The page that lists every model card. `/ranges/` rather than the homepage: same cards,
#: and it is the page Chausson present as the model index.
RANGES_PATH = "/ranges/"

#: One listing card. Anchored on the title and read **forward** to the card's own model link,
#: because the details block follows the title — see the module docstring, trap 2.
_CARD = re.compile(
    r'titre-modele[^>]*>\s*(?P<name>[A-Za-z0-9&]+)\s*</span>'
    r'(?P<body>.*?)'
    r'href="[^"]*?/model/(?P<slug>[a-z0-9]+)/"',
    re.S,
)

#: `From 58 790 GBP`. The site writes **GBP**, not a pound sign — searching for `£` finds
#: only the nav block and misses every real price.
_PRICE = re.compile(r'<p class="prix">\s*From\s*(?P<amount>[\d\s ]+)\s*GBP', re.I)

#: A picto: the icon span, then the figure. `couchages` is berths, `places_route` travelling
#: seats, `places_repas` dining places, `porteur` the base vehicle **and** the overall length.
#:
#: The class attribute is matched to its closing quote rather than to `picto"`, because
#: `picto` is not always the last word: the counts are `class="couchages picto"` but the
#: length lives in `class="porteur picto ford"`. Anchoring on `picto"` silently matched the
#: counts and missed every length.
_PICTO = r'class="{cls}[^"]*"[^>]*>.*?<span>\s*(?P<value>[^<]*?)\s*</span>'

#: The overall length, inside the `porteur` picto alongside the chassis logo: `6.59m`. Its own
#: pattern rather than a derivative of `_PICTO`, since it needs the unit to anchor on.
_LENGTH = re.compile(r'class="porteur[^"]*"[^>]*>.*?<span>\s*(?P<value>[\d.,]+)\s*m', re.S)

#: The base vehicle, from the `porteur` picto's own class — `porteur picto ford`.
_PORTEUR = re.compile(r'class="porteur picto (?P<make>[a-z]+)"')

#: One accordion row, scoped to a single `<li>` so a label can never pair with another row's
#: value — see the module docstring, trap 1.
_ROW = re.compile(r"<li\b[^>]*>(?P<row>.*?)</li>", re.S)
_ROW_NAME = re.compile(r'class="caracteristique-nom"[^>]*>(?P<name>.*?)</span>', re.S)
_ROW_VALUE = re.compile(r'class="caracteristique-valeur"[^>]*>(?P<value>.*?)</span>', re.S)

#: `Low profiles 650` -> (`Low profiles`, `650`). The line is the prefix, and it is the only
#: reliable statement of a model's range.
_HEADING = re.compile(r"<h1[^>]*>(?P<text>.*?)</h1>", re.S)

#: Accordion labels, as the English site writes them. Some rows on the same site are still
#: French (`Portillon latéral côté droit`, `Capacité réservoir carburant`), so match the
#: English ones exactly rather than pattern-matching loosely across a bilingual page.
LABEL_WIDTH = "Overall width"
LABEL_HEIGHT = "Overall height"
LABEL_MTPLM = "Max technically permissible laden mass"
LABEL_MRO = "running order"

#: Chausson's lines map almost directly onto FMLV's body types, so the `<h1>` supplies the
#: body type as well as the range.
#:
#: `vans` is absent here because it is not a fixed answer: a campervan's type depends on its
#: roof, per the rule in `docs/adapters/README.md`, so it is worked out from the published
#: height instead. See `ChaussonProduct.body_type`.
#:
#: `x` is absent because it is a genuine judgement rather than a lookup. Chausson call the X
#: an "ultra compact motorhome" and its dimensions sit between the two candidates — 2.1 m
#: wide against a van's 2.05 and a coachbuilt's 2.35 — so whether FMLV counts an X550 as a
#: campervan or a low-profile coachbuilt is for a reviewer to decide, not a parser.
_BODY_TYPES: dict[str, BodyType] = {
    "low profiles": BodyType.COACH_BUILT_LOW_PROFILE,
    "s low profiles": BodyType.COACH_BUILT_LOW_PROFILE,
    "overcab": BodyType.COACH_BUILT_OVER_CAB_BED,
    "a-class": BodyType.A_CLASS,
}

#: The line whose body type comes from the roof rather than a lookup.
CAMPERVAN_LINE = "vans"

#: A campervan taller than this is a high top — the roof line materially above the side
#: windows. The same threshold as `auto_trail.HIGH_TOP_ABOVE_MM`, and set by the NCC side from
#: FMLV's own data: the tallest standard-height campervan on the site is 2050mm.
HIGH_TOP_ABOVE_MM = 2300

#: Bounds on a plausible payload, in kg. Chausson's real spread is 363–927 kg across the 18
#: models. Wide enough for a genuine outlier, tight enough to catch a mass read from the
#: wrong column of a two-vehicle cell.
MIN_PAYLOAD_KG = 100
MAX_PAYLOAD_KG = 2000


def _text(markup: str) -> str:
    """Tags stripped, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(markup))).strip()


def _leading(value: str) -> str:
    """`'2.35 / 2.05'` -> `'2.35'`; `'3007 / 3085'` -> `'3007'`.

    The base-vehicle rule in `docs/adapters/README.md`. Chausson's `/model/640/` publishes
    two vehicles' figures in one cell, the second belonging to a van, so the leading figure
    is the page's own model. Taking the last would put a van's dimensions on a coachbuilt.
    """
    return value.split("/")[0].strip()


def _pounds(value: str) -> int | None:
    """`'58 790'` -> `58790`. Chausson group thousands with spaces, sometimes non-breaking."""
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def _millimetres(value: str) -> int | None:
    """`'2.35'` -> `2350`; `'6.59'` -> `6590`. Chausson quote metres to two decimals."""
    match = re.search(r"(\d+(?:[.,]\d+)?)", _leading(value))
    if match is None:
        return None
    return int(round(Decimal(match.group(1).replace(",", ".")) * 1000))


def _kilograms(value: str) -> int | None:
    match = re.search(r"(\d[\d\s]*)", _leading(value))
    return int(re.sub(r"\D", "", match.group(1))) if match else None


def _standard_count(value: str) -> int | None:
    """The standard figure of a published count.

    Chausson write berths three ways — `4`, `2+1*`, `2/3*` — where the asterisk footnotes an
    optional extra. Per the data rules in `docs/adapters/README.md` the **lower** figure is
    recorded, because the rest need options, and the published string is carried into the
    provenance so the reviewer sees what was on the page.
    """
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


@dataclass(frozen=True)
class ChaussonCard:
    """One model as rendered on `/ranges/`: identity, price and the picto figures."""

    slug: str
    name: str
    rrp_pounds: int | None = None
    berths_published: str | None = None
    seats_published: str | None = None
    mh_length_mm: int | None = None
    base_vehicle_manufacturer: str | None = None

    @property
    def berths(self) -> int | None:
        return _standard_count(self.berths_published) if self.berths_published else None

    @property
    def mh_passenger_seats_inc_driver(self) -> int | None:
        return _standard_count(self.seats_published) if self.seats_published else None


@dataclass(frozen=True)
class ChaussonProduct:
    """One model, once its card and its own page have been read."""

    card: ChaussonCard
    range_label: str = ""
    model: str = ""
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None

    @property
    def label(self) -> str:
        return f"{self.range_label} {self.model}".strip() or self.card.slug

    @property
    def body_type(self) -> BodyType | None:
        """The body type, from the line — except for the vans, which come from the roof.

        A campervan's type is not a property of its range but of its roof height and whether
        it has an elevating roof, per the rule in `docs/adapters/README.md`. Chausson publish
        no pop-top on the V594 and an overall height of 2.65 m, comfortably above the
        high-top threshold, so it is a high top. Without a height nothing is claimed.
        """
        if self.range_label.lower() == CAMPERVAN_LINE:
            if self.mh_height_mm is None:
                return None
            if self.mh_height_mm > HIGH_TOP_ABOVE_MM:
                return BodyType.CAMPERVAN_HIGH_TOP
            return BodyType.CAMPERVAN
        return _BODY_TYPES.get(self.range_label.lower())

    @property
    def mh_payload_kilograms(self) -> int | None:
        """Payload, which Chausson do not publish, derived from the two masses."""
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms


def _reconciles(product: ChaussonProduct) -> bool:
    """Whether the masses are consistent enough to propose.

    Chausson publish no payload, so there is no `payload == MTPLM - MRO` identity to lean on,
    and the `(+/- 5%)` beside the running order is only a label — not a printed band like
    Sunlight's. What this catches is the failure the two-vehicle cells threaten: a mass taken
    from the wrong column. `/model/640/` offers `3007 / 3085`, and the neighbouring figures
    belong to a van several hundred kilograms apart.

    A product missing either mass passes, having nothing to contradict; the gap is reported
    as a missing field instead.
    """
    mtplm, mro = product.mtplm_kilograms, product.mro_kilograms
    if mtplm is None or mro is None:
        return True
    if mtplm <= mro:
        return False
    return MIN_PAYLOAD_KG <= mtplm - mro <= MAX_PAYLOAD_KG


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_cards(ranges_html: str) -> dict[str, ChaussonCard]:
    """Every model card on `/ranges/`, keyed by slug.

    Read **forward** from each title to that card's own `/model/<slug>/` link. Reading
    backwards from a details block to the nearest preceding title attributes the previous
    model's figures — it read S614's price, berths and length as S697's, which went unnoticed
    because the two cost the same and differ only in berths.

    The slug is the key, not the displayed name: `x550` and `x640` render as `550` and `640`,
    and `640` is also a Low profile.
    """
    text = unescape(ranges_html)
    cards: dict[str, ChaussonCard] = {}

    for match in _CARD.finditer(text):
        slug, body = match.group("slug"), match.group("body")
        if slug in cards:
            continue  # each model is rendered more than once; the first wins

        price = _PRICE.search(body)
        porteur = _PORTEUR.search(body)
        length = _LENGTH.search(body)

        def figure(cls: str) -> str | None:
            found = re.search(_PICTO.format(cls=cls), body, re.S)
            return found.group("value").strip() if found else None

        cards[slug] = ChaussonCard(
            slug=slug,
            name=_text(match.group("name")),
            rrp_pounds=_pounds(price.group("amount")) if price else None,
            berths_published=figure("couchages"),
            seats_published=figure("places_route"),
            mh_length_mm=_millimetres(length.group("value")) if length else None,
            base_vehicle_manufacturer=porteur.group("make").title() if porteur else None,
        )
    return cards


def parse_rows(model_html: str) -> dict[str, str]:
    """The model page's characteristics, read one `<li>` at a time.

    Scoped per row on purpose. The page carries more labels than values — 26 against 21 on
    `/model/650/`, because the chassis and option-price blocks have labels and no figures — so
    zipping the two lists drifts and silently mis-assigns. It paired `Overall width (m)` with
    `1845x605`, a side-locker aperture, and the laden mass with `100L`, the waste tank.

    Later rows win, which matters not at all today (no label repeats) and is stated so the
    behaviour is deliberate rather than incidental.
    """
    rows: dict[str, str] = {}
    for row in _ROW.finditer(unescape(model_html)):
        block = row.group("row")
        name = _ROW_NAME.search(block)
        value = _ROW_VALUE.search(block)
        if name is None or value is None:
            continue
        label, figure = _text(name.group("name")), _text(value.group("value"))
        if label and figure:
            rows[label] = figure
    return rows


def find_row(rows: dict[str, str], label: str) -> str | None:
    """The value of the row whose label contains `label`, or `None`.

    Substring rather than equality because Chausson's labels carry parenthetical detail that
    changes between models — `Overall height (excl. roof rack) (m)` and
    `Vehicle bodycoach weight in running order (+/- 5%) (kg)`.
    """
    for name, value in rows.items():
        if label.lower() in name.lower():
            return value
    return None


def parse_heading(model_html: str) -> tuple[str, str]:
    """`'Low profiles 650'` -> `('Low profiles', '650')`.

    The `<h1>` is the only reliable statement of a model's line, and the line is what keeps
    the Low profile `640` apart from the X `640`. The model is the last word; everything
    before it is the line.
    """
    match = _HEADING.search(model_html)
    if match is None:
        return "", ""
    words = _text(match.group("text")).split()
    if len(words) < 2:
        return "", " ".join(words)
    return " ".join(words[:-1]), words[-1]


def has_characteristics(model_html: str) -> bool:
    """Whether a model page is a real one.

    `/model/x650/` returns HTTP 200 with the `/ranges/` page's title, the heading "Find your
    ideal Chausson camper" and **no accordion at all** — a soft 404 behind a link Chausson
    have not removed. A page with no characteristics is absent, not a product with no data.
    """
    return "caracteristique-nom" in model_html


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _build_extracted_motorhome(
    product: ChaussonProduct, model_url: str, ranges_url: str
) -> ExtractedMotorhome:
    card = product.card

    motorhome = Motorhome(
        manufacturer=MANUFACTURER,
        manufacturer_display_name=MANUFACTURER_DISPLAY_NAME,
        manufacturer_range=product.range_label,
        model=product.model,
        base_vehicle_manufacturer=card.base_vehicle_manufacturer,
        berths=card.berths,
        mh_passenger_seats_inc_driver=card.mh_passenger_seats_inc_driver,
        rrp_pounds=card.rrp_pounds,
        mtplm_kilograms=product.mtplm_kilograms,
        mro_kilograms=product.mro_kilograms,
        mh_payload_kilograms=product.mh_payload_kilograms,
        mh_length_mm=card.mh_length_mm,
        mh_width_mm=product.mh_width_mm,
        mh_height_mm=product.mh_height_mm,
        body_type=product.body_type,
    )

    provenance: dict[str, Provenance] = {}

    def record(field: str, url: str, snippet: str) -> None:
        provenance[field] = Provenance(source_url=url, snippet=f"{product.label} — {snippet}")

    # From the model page.
    for field, value, label in (
        ("mh_width_mm", product.mh_width_mm, LABEL_WIDTH),
        ("mh_height_mm", product.mh_height_mm, "Overall height (excl. roof rack)"),
        ("mtplm_kilograms", product.mtplm_kilograms, LABEL_MTPLM),
        ("mro_kilograms", product.mro_kilograms, "Vehicle bodycoach weight in running order"),
    ):
        if value is not None:
            record(field, model_url, f"{label}: {value}")

    # From the listing card.
    if card.rrp_pounds is not None:
        record(
            "rrp_pounds",
            ranges_url,
            f"From {card.rrp_pounds:,} GBP, shown against this model alone on its listing "
            f"card. A 'from' price against one specific model is usable as the FMLV guide "
            f"price; the line-level 'from' figures in the page nav are not",
        )
    if card.berths is not None:
        record("berths", ranges_url, f"berths published as '{card.berths_published}', standard figure {card.berths}")
    if card.mh_passenger_seats_inc_driver is not None:
        record(
            "mh_passenger_seats_inc_driver",
            ranges_url,
            f"travelling seats published as '{card.seats_published}'",
        )
    if card.mh_length_mm is not None:
        record("mh_length_mm", ranges_url, f"overall length {card.mh_length_mm / 1000:.2f}m")
    if card.base_vehicle_manufacturer is not None:
        record("base_vehicle_manufacturer", ranges_url, f"base vehicle {card.base_vehicle_manufacturer}")

    if product.mh_payload_kilograms is not None:
        record(
            "mh_payload_kilograms",
            model_url,
            f"derived: {product.mtplm_kilograms}kg maximum laden - {product.mro_kilograms}kg "
            f"running order = {product.mh_payload_kilograms}kg (Chausson publish no payload)",
        )
    if product.body_type is not None:
        record("body_type", model_url, f"line '{product.range_label}' from the page heading")
    record(
        "manufacturer_range",
        model_url,
        f"line '{product.range_label}' from the heading '{product.range_label} {product.model}'. "
        f"The listing card shows '{card.name}' alone, which is not unique — the X 640 and the "
        f"Low profile 640 both render as '640' — so the range comes from the heading",
    )
    return ExtractedMotorhome(motorhome=motorhome, provenance=provenance)


def collect(
    http: Fetcher,
    browser: object,  # noqa: ARG001 — Chausson needs no JS; see the module docstring
    snapshot_dir: Path,  # noqa: ARG001 — `http` already snapshots into it
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
    """Collect Chausson's UK range: one `/ranges/` fetch, then one page per model.

    A model that cannot be read is narrated and skipped; only `/ranges/` being unreachable
    raises, since without it there are no models to visit.
    """
    ranges_url = f"{BASE_URL}{RANGES_PATH}"
    on_progress(f"fetching {ranges_url} for the model cards...")
    listing = http.fetch(ranges_url)
    if listing.status_code != 200:
        msg = f"Chausson {RANGES_PATH} returned {listing.status_code}; it is the model index"
        raise RuntimeError(msg)

    listing_html = listing.file_path.read_text(encoding="utf-8", errors="replace")
    cards = parse_cards(listing_html)
    slugs = list(dict.fromkeys(re.findall(r"/model/([a-z0-9]+)/", listing_html, re.IGNORECASE)))
    on_progress(f"{len(slugs)} model(s) linked, {len(cards)} with a listing card")

    wanted = {label.lower() for _slug, label in ranges}
    if wanted != {label.lower() for _s, label in DEFAULT_RANGES}:
        on_progress(f"restricted to {sorted(label for _s, label in ranges)}")

    results: list[ExtractedMotorhome] = []

    for slug in slugs:
        model_url = f"{BASE_URL}/model/{slug}/"
        page = http.fetch(model_url)
        if page.status_code != 200:
            on_progress(f"[{slug}] SKIPPED: {model_url} returned {page.status_code}")
            continue

        model_html = page.file_path.read_text(encoding="utf-8", errors="replace")
        if not has_characteristics(model_html):
            on_progress(
                f"[{slug}] SKIPPED: {model_url} has no characteristics accordion, so it is a "
                f"stale link rather than a model (it returns 200 with the /ranges/ page)"
            )
            continue

        range_label, model = parse_heading(model_html)
        if not range_label:
            on_progress(f"[{slug}] SKIPPED: could not read a line and model from the page heading")
            continue
        if range_label.lower() not in wanted:
            continue

        card = cards.get(slug)
        if card is None:
            on_progress(
                f"[{range_label} {model}] SKIPPED: no listing card, so no price, berths, "
                f"seats, length or base vehicle"
            )
            continue

        rows = parse_rows(model_html)
        product = ChaussonProduct(
            card=replace(card, slug=slug),
            range_label=range_label,
            model=model,
            mh_width_mm=_millimetres(find_row(rows, LABEL_WIDTH) or ""),
            mh_height_mm=_millimetres(find_row(rows, LABEL_HEIGHT) or ""),
            mtplm_kilograms=_kilograms(find_row(rows, LABEL_MTPLM) or ""),
            mro_kilograms=_kilograms(find_row(rows, LABEL_MRO) or ""),
        )

        if not _reconciles(product):
            on_progress(
                f"[{product.label}] SKIPPED: masses don't reconcile (maximum laden "
                f"{product.mtplm_kilograms}kg, running order {product.mro_kilograms}kg), so a "
                f"figure may have come from the wrong column of a two-vehicle cell"
            )
            continue

        for field, value in (
            ("price", card.rrp_pounds),
            ("overall length", card.mh_length_mm),
            ("overall width", product.mh_width_mm),
            ("overall height", product.mh_height_mm),
        ):
            if value is None:
                on_progress(f"[{product.label}] WARNING: no {field} published, left blank")

        if product.body_type is None:
            on_progress(
                f"[{product.label}] NOTE: no body type set for the '{range_label}' line. "
                f"Chausson call the X an 'ultra compact motorhome' and its 2.1m width sits "
                f"between a van's and a coachbuilt's, so the mapping is a reviewer's judgement"
            )

        results.append(_build_extracted_motorhome(product, model_url, ranges_url))

    on_progress(f"{len(results)} product(s) collected")
    return results
