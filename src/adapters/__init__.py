"""Manufacturer adapters, and the lookup from a registry row to the code that runs it.

Per DESIGN.md §5.1 this package is "the only manufacturer-specific code". `base.py`
defines what an adapter is; each sibling module is one. A module satisfies the
`Adapter` protocol structurally — `adria.collect` has the right shape — so an adapter
is a module here, not a class that has to be instantiated.

`ADAPTERS` is keyed by `(Manufacturer.fmlv_manufacturer, VehicleClass)` rather than by
`manufacturer_id`. The name column is required to match the FMLV export's `manufacturer`
value exactly, which makes it the same string the baseline is filtered on, and it does not
depend on the still-open question of what `manufacturer_id` actually is or whether it is
stable (TODO.md, "For Ben").

The product area is in the key because a manufacturer can need **two adapters**. FMLV keeps
motorhomes and touring caravans as separate exports with separate schemas (DESIGN.md §3),
and eight of the registered manufacturers build both — Bailey's caravans live on the same
site as its motorhomes, under different URLs, with a different spec table and a different
set of columns to fill. Those are two different collect() implementations producing two
differently-shaped products, not one adapter with a flag.

An adapter says which area it serves with a module-level `VEHICLE_CLASS`. Omitting it means
motorhomes, so the seventeen adapters written before caravans existed need no edit — the
same `getattr` opt-in `DEFAULT_RANGES` and `baseline_in_scope` use.
"""

from __future__ import annotations

from . import (
    adria,
    auto_trail,
    bailey,
    bailey_caravan,
    burstner,
    chausson,
    coachman,
    dethleffs,
    elddis,
    etrusco,
    knaus,
    morelo,
    moto_trek,
    rimor,
    sunlight,
    swift,
    swift_caravan,
    weinsberg,
    wingamm,
)
from ..vehicle_class import DEFAULT as DEFAULT_VEHICLE_CLASS
from ..vehicle_class import VehicleClass
from .base import Adapter, ExtractedMotorhome, Provenance

#: Every adapter module, in the order they were written. `ADAPTERS` is derived from
#: this rather than spelled out as a dict literal, so registering one is a single edit
#: and the (manufacturer, class) key can never drift from what the module declares.
_MODULES: tuple[Adapter, ...] = (
    adria,
    auto_trail,
    bailey,
    bailey_caravan,
    burstner,
    chausson,
    coachman,
    dethleffs,
    elddis,
    etrusco,
    knaus,
    morelo,
    moto_trek,
    rimor,
    sunlight,
    swift,
    swift_caravan,
    weinsberg,
    wingamm,
)


def adapter_vehicle_class(adapter: Adapter) -> VehicleClass:
    """Which FMLV product area an adapter produces, defaulting to motorhomes.

    Read with `getattr` so an adapter written before caravans existed — every one of
    the seventeen — needs no edit to keep working.
    """
    return VehicleClass(getattr(adapter, "VEHICLE_CLASS", DEFAULT_VEHICLE_CLASS))


ADAPTERS: dict[tuple[str, VehicleClass], Adapter] = {
    (module.MANUFACTURER, adapter_vehicle_class(module)): module for module in _MODULES
}

__all__ = [
    "ADAPTERS",
    "Adapter",
    "ExtractedMotorhome",
    "Provenance",
    "adapter_for",
    "adapter_vehicle_class",
    "adapters_for",
    "adria",
    "auto_trail",
    "bailey",
    "bailey_caravan",
    "burstner",
    "chausson",
    "coachman",
    "dethleffs",
    "elddis",
    "etrusco",
    "knaus",
    "morelo",
    "moto_trek",
    "rimor",
    "sunlight",
    "swift",
    "swift_caravan",
    "weinsberg",
    "wingamm",
]


def adapter_for(
    fmlv_manufacturer: str, vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS
) -> Adapter | None:
    """The adapter for one manufacturer's product area, or `None` if nobody wrote one.

    Returning `None` rather than raising keeps "we have no adapter for this brand" a
    normal, reportable state — a sweep across the whole registry has to skip most
    manufacturers for exactly this reason until Phase 4's remaining adapters land. It is
    now also the normal answer for "Bailey, but caravans" until that adapter exists, which
    is why `vehicle_class` defaults rather than being required: every existing caller asks
    the question it always asked, and gets the answer it always got.
    """
    return ADAPTERS.get((fmlv_manufacturer, VehicleClass(vehicle_class)))


def adapters_for(fmlv_manufacturer: str) -> dict[VehicleClass, Adapter]:
    """Every product area this manufacturer has an adapter for.

    For the review app's trigger page, which has to offer "Bailey motorhomes" and "Bailey
    caravans" as separate choices rather than one "Bailey" that silently means whichever
    adapter was registered.
    """
    return {
        registered_class: adapter
        for (manufacturer, registered_class), adapter in ADAPTERS.items()
        if manufacturer == fmlv_manufacturer
    }
