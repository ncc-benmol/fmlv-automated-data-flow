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
