"""The adapter interface: one module per manufacturer, snapshot in, `Motorhome`s out.

Per DESIGN.md §5.1, `adapters/` is "the only manufacturer-specific code" — everything
else in the pipeline (fetching, the canonical model, diffing, review) is generic.

Fetching and parsing are deliberately *not* split into separate interface methods.
For a JS-driven catalogue (Adria's is the first one surveyed — see `adria.py`),
discovering what to fetch next depends on content already fetched: the technical-data
PDF for one product is only reachable once its ID has been read out of an earlier
AJAX response. An adapter therefore owns its whole fetch-then-parse sequence, but
every request still goes through `Fetcher`/`BrowserFetcher`, so every request is still
snapshotted to disk regardless (DESIGN.md §6.6) and reproducible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..fetch.browser import BrowserFetcher
from ..fetch.http import Fetcher
from ..product_model.caravan import Caravan
from ..product_model.model import Motorhome


#: Every spelling a manufacturer's own site or document has been seen to use for a base
#: vehicle, mapped to the one string FMLV holds. Keyed on the lower-cased make so a
#: `.title()`-ed CSS class, an all-caps PDF heading and a full legal name all land on the
#: same value.
#:
#: **The naming protocol, from the requester, 27 August 2026.** Where one company is both a
#: base-vehicle supplier *and* a manufacturer of complete leisure vehicles, FMLV gives the
#: two roles **deliberately different names**: the abbreviated form is the base vehicle, the
#: full form is the manufacturer.
#:
#: | Company | Base vehicle | Manufacturer |
#: |---|---|---|
#: | Volkswagen | **`VW`** | `Volkswagen` |
#: | Mercedes-Benz | **`Mercedes`** | `Mercedes-Benz` |
#:
#: The reason is the customer-facing filters: "what we don't want is customers to be
#: confused whether to choose in the filters VW or Volkswagen. It should only be one base
#: vehicle name for that company who makes base vehicles, and only one name for the
#: manufacturer who actually makes entire vehicles." Volkswagen build campervans themselves,
#: so both roles are real and both are populated.
#:
#: **So `VW` here is correct and must not be "corrected" to `Volkswagen`.** The trap is that
#: the base-vehicle column of every export this project holds shows only eight spellings and
#: **`VW` is not among them** — Fiat 740, Mercedes 187, Ford 171, Peugeot 157, IVECO 142,
#: MAN 21, Citroën 19, Renault 5. That is a gap in our sample, not a fact about FMLV: none of
#: the fourteen manufacturers surveyed so far builds on a Crafter until Sunlight's VW IBEX.
#: FMLV holds **over a hundred** VW base vehicles. Reasoning from the exports alone very
#: nearly produced a wrong "correction" here, which is the roster lesson in
#: `docs/adapters/README.md` turned on FMLV's own data — an absence you cannot explain is a
#: gap in the search.
#:
#: One further rule:
#:
#: * **`Citroën` with the diaeresis, always** — for Chausson and every other brand.
#:   Chausson reads its make from a CSS class (`porteur picto citroen`), which cannot
#:   carry the accent, so without this the accent could never be recovered.
_FMLV_BASE_VEHICLE_MAKES: dict[str, str] = {
    "citroen": "Citroën",
    "citroën": "Citroën",
    "fiat": "Fiat",
    "ford": "Ford",
    "iveco": "IVECO",
    "man": "MAN",
    "mercedes": "Mercedes",
    "mercedes benz": "Mercedes",
    "mercedes-benz": "Mercedes",
    "peugeot": "Peugeot",
    "renault": "Renault",
    "vw": "VW",
}


def fmlv_base_vehicle(make: str | None) -> str | None:
    """One base-vehicle make as FMLV spells it, whatever spelling the source used.

    `base_vehicle_manufacturer` is compared against FMLV's own stored string, so the
    spelling decides whether a run *confirms* the field or proposes a rename. Every
    adapter routes its make through here so that decision is made in one place instead of
    thirteen — see `docs/adapters/README.md`.

    An unrecognised make is returned **unchanged rather than blanked**: it is far more
    likely to be a real chassis nobody has met yet than a parse error, and dropping it
    would lose a REQUIRED field. `tests/adapters/test_registry_wiring.py` is what stops a
    known-wrong spelling reaching a reviewer.

    Normalising here, on the adapter side only, is deliberate. Doing it on `Motorhome`
    itself would also rewrite the value read *out of* the FMLV baseline, so a row FMLV
    holds as `Citroen` would silently match `Citroën` and the correction would never be
    proposed. This way the adapter emits FMLV's spelling and a baseline that disagrees
    gets a proposed change, which is the point.
    """
    if make is None:
        return None
    cleaned = " ".join(make.split())
    if not cleaned:
        return None
    return _FMLV_BASE_VEHICLE_MAKES.get(cleaned.lower(), cleaned)


def model_without_range_prefix(manufacturer_range: str | None, model: str | None) -> str | None:
    """Drop a leading word from `model` that the range name already carries.

    FMLV renders a product as manufacturer + range + model, so Sunlight's range
    `CLIFF X` with model `CLIFF 602` reads back as "Sunlight CLIFF X CLIFF 602". The
    second CLIFF is noise: the range has already said it.

    Only ever drops a *leading* word, only when the range genuinely contains that word,
    and only when what is left still has letters or digits in it to name the layout —
    so `CLIFF X` + `CLIFF` keeps `CLIFF`, since the alternative is a product with no
    model at all. `CLIFF 540 V` in range `CLIFF Vanlife` becomes `540 V`, which stays
    distinct from `CLIFF Adventure`'s `540`.

    Deliberately *not* applied by every adapter. Bürstner's `Lyseo TD Harmony Line`
    holds models `TD 680 G` and `680 G` as separate FMLV rows, so the same rule there
    would collapse a distinction FMLV is currently making. Call it where a manufacturer's
    naming has been checked, rather than wiring it into `Motorhome`.
    """
    if not model or not manufacturer_range:
        return model
    words = model.split()
    if len(words) < 2:
        return model
    range_words = {word.lower() for word in manufacturer_range.split()}
    if words[0].lower() not in range_words:
        return model
    remainder = " ".join(words[1:])
    if not any(character.isalnum() for character in remainder):
        return model
    return remainder


@dataclass(frozen=True)
class Provenance:
    """Where one extracted field's value came from, shown next to it for the reviewer."""

    source_url: str
    snippet: str


@dataclass
class ExtractedMotorhome:
    """One product read from a manufacturer's site, with per-field provenance.

    `provenance` is keyed by `Motorhome` field name. Not every field needs an entry —
    a field the adapter couldn't find simply has none, and stays `None` on `motorhome`.
    """

    motorhome: Motorhome
    provenance: dict[str, Provenance] = field(default_factory=dict)

    @property
    def product(self) -> Motorhome:
        """The vehicle, under a name that does not assume the product area.

        `ExtractedCaravan` exposes the same property, so code that only needs "the thing
        this adapter found" can read it from either without branching.
        """
        return self.motorhome


@dataclass
class ExtractedCaravan:
    """One touring caravan read from a manufacturer's site, with per-field provenance.

    The caravan counterpart of `ExtractedMotorhome`. `provenance` is keyed by `Caravan`
    field name, and a field the adapter could not find simply has no entry.

    `product` is the name the pipeline should use when it does not care which product area
    it is looking at — both classes expose it, so `diff` and `store` can read the vehicle
    out of either without branching on type.
    """

    caravan: Caravan
    provenance: dict[str, Provenance] = field(default_factory=dict)

    @property
    def product(self) -> Caravan:
        return self.caravan


#: One extracted product of either area. Both classes expose `.product`, so code that
#: only needs "the vehicle this adapter found" can read it from either without branching
#: — `diff` and `store` annotate this.
ExtractedProduct = ExtractedMotorhome | ExtractedCaravan


class Adapter(Protocol):
    """Turns one manufacturer's website into canonical products.

    Two things every adapter also declares, which a `Protocol` cannot express because
    they are module-level constants rather than methods:

    * `MANUFACTURER` — half the key this adapter is registered under in `ADAPTERS`, and
      it must equal the registry row's `fmlv_manufacturer` exactly. Also
      `MANUFACTURER_DISPLAY_NAME` and `BASE_URL`.
    * `VEHICLE_CLASS: VehicleClass` — optional, the other half of that key. Absent means
      motorhomes and campervans, which is what every adapter written before touring
      caravans came into scope produces. A manufacturer that builds both gets **two
      adapter modules**, not one with a flag: they are different URLs, a different spec
      table and a differently-shaped product (DESIGN.md §3).
    * `DEFAULT_RANGES: tuple[tuple[str, str], ...]` — optional, `(path, label)` pairs.
      `cli.resolve_ranges` looks for it with `getattr` and treats its absence as "this
      adapter does not support `--range`", so it stays genuinely opt-in.
    """

    def collect(
        self,
        http: Fetcher,
        browser: BrowserFetcher,
        snapshot_dir: Path,
        *,
        on_progress: Callable[[str], None] = lambda message: None,
    ) -> list[ExtractedMotorhome]:
        """Fetch (via `http`/`browser`, snapshotting into `snapshot_dir`) and parse.

        `on_progress` takes one line of human-readable text and is how a run narrates
        itself to whoever is watching — the CLI prints it, the review app streams it
        onto the run page. `cli.execute_run` always passes it, so it is required in the
        signature even though it has a default, and an adapter that omits it fails on
        its first real run. Use it at each page/product boundary and, importantly,
        every time something is *skipped*: a product dropped for failing the adapter's
        own arithmetic self-check is invisible otherwise.
        """
        ...
