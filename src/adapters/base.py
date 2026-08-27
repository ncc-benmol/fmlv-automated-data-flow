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
from ..product_model.model import Motorhome


#: Every spelling a manufacturer's own site or document has been seen to use for a base
#: vehicle, mapped to the one string FMLV holds. Keyed on the lower-cased make so a
#: `.title()`-ed CSS class, an all-caps PDF heading and a full legal name all land on the
#: same value.
#:
#: Two rules from the requester, 27 August 2026:
#:
#: * **`Mercedes`, never `Mercedes-Benz`.** `Mercedes-Benz` *is* a manufacturer in FMLV
#:   (it has its own row in the manufacturer list), but as a **base vehicle** the value is
#:   always the short form. The two are different fields and the distinction is
#:   deliberate: "there is a manufacturer called Mercedes Benz and its base vehicle name
#:   that we use is Mercedes".
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


class Adapter(Protocol):
    """Turns one manufacturer's website into canonical products.

    Two things every adapter also declares, which a `Protocol` cannot express because
    they are module-level constants rather than methods:

    * `MANUFACTURER` — the key this adapter is registered under in `ADAPTERS`, and it
      must equal the registry row's `fmlv_manufacturer` exactly. Also
      `MANUFACTURER_DISPLAY_NAME` and `BASE_URL`.
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
