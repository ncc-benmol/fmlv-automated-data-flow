"""Manufacturer adapters, and the lookup from a registry row to the code that runs it.

Per DESIGN.md §5.1 this package is "the only manufacturer-specific code". `base.py`
defines what an adapter is; each sibling module is one. A module satisfies the
`Adapter` protocol structurally — `adria.collect` has the right shape — so an adapter
is a module here, not a class that has to be instantiated.

`ADAPTERS` is keyed by `Manufacturer.fmlv_manufacturer` rather than `manufacturer_id`.
That column is required to match the FMLV export's `manufacturer` value exactly, which
makes it the same string the baseline is filtered on, and it does not depend on the
still-open question of what `manufacturer_id` actually is or whether it is stable
(TODO.md, "For Ben").
"""

from __future__ import annotations

from . import (
    adria,
    auto_trail,
    bailey,
    burstner,
    chausson,
    coachman,
    elddis,
    etrusco,
    morelo,
    rimor,
    sunlight,
    swift,
)
from .base import Adapter, ExtractedMotorhome, Provenance

ADAPTERS: dict[str, Adapter] = {
    adria.MANUFACTURER: adria,
    auto_trail.MANUFACTURER: auto_trail,
    bailey.MANUFACTURER: bailey,
    burstner.MANUFACTURER: burstner,
    chausson.MANUFACTURER: chausson,
    coachman.MANUFACTURER: coachman,
    elddis.MANUFACTURER: elddis,
    etrusco.MANUFACTURER: etrusco,
    morelo.MANUFACTURER: morelo,
    rimor.MANUFACTURER: rimor,
    sunlight.MANUFACTURER: sunlight,
    swift.MANUFACTURER: swift,
}

__all__ = [
    "ADAPTERS",
    "Adapter",
    "ExtractedMotorhome",
    "Provenance",
    "adapter_for",
    "adria",
    "auto_trail",
    "bailey",
    "burstner",
    "chausson",
    "coachman",
    "elddis",
    "etrusco",
    "morelo",
    "rimor",
    "sunlight",
    "swift",
]


def adapter_for(fmlv_manufacturer: str) -> Adapter | None:
    """The adapter for one manufacturer, or `None` if nobody has written one yet.

    Returning `None` rather than raising keeps "we have no adapter for this brand" a
    normal, reportable state — a sweep across the whole registry has to skip most
    manufacturers for exactly this reason until Phase 4's remaining adapters land.
    """
    return ADAPTERS.get(fmlv_manufacturer)
