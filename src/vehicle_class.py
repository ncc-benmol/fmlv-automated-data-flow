"""Which FMLV product area a run works in: motorhomes/campervans, or touring caravans.

FMLV keeps the two as **separate exports with separate schemas** — one NCC "Export
Products by Supplier" action returns both `motorhome-campervans.xlsx` (68 columns) and
`touring-caravans.xlsx` (62 columns). They share ~30 columns and all the layout flags,
but differ in body types, dimension names and payload structure, and there is no base
vehicle on a caravan (DESIGN.md §3).

So a run is always *for one product area*, and this enum is how that travels: through
`paths` (which field guide, which upload filename), the run store (`run.vehicle_class`,
`product.vehicle_class`), the review app, and the adapter registry key.

Why it matters beyond bookkeeping — eight of the sixteen manufacturers in the registry
build both. A Bailey caravan run and a Bailey motorhome run are two different runs over
two different baselines producing two differently-shaped CSVs, and the reviewer has to be
able to tell them apart at a glance. Before this existed they rendered as two identical
rows on the runs page.
"""

from __future__ import annotations

from enum import Enum


class VehicleClass(str, Enum):
    """One FMLV product area.

    A `str` enum so it round-trips through SQLite and query strings without conversion:
    the stored value is the member's value, and `VehicleClass(row["vehicle_class"])`
    reads it back.
    """

    MOTORHOME = "motorhome"
    CARAVAN = "caravan"

    @property
    def badge(self) -> str:
        """The short word for the runs-list badge, where space is tight."""
        return self.value

    @property
    def label(self) -> str:
        """The NCC's own wording, for headings and prose."""
        return {
            VehicleClass.MOTORHOME: "Motorhomes & campervans",
            VehicleClass.CARAVAN: "Touring caravans",
        }[self]

    @property
    def export_stem(self) -> str:
        """The NCC's filename for this area's export, without extension.

        Used for both halves of the downloaded zip (`fetch/ncc.py`) and for the generated
        upload CSV (`paths.upload_csv_path`). Keeping the generated file's name identical
        to the NCC's own is deliberate: the reviewer uploads it by hand, and the filename
        is the main cue for which importer it belongs to.
        """
        return {
            VehicleClass.MOTORHOME: "motorhome-campervans",
            VehicleClass.CARAVAN: "touring-caravans",
        }[self]

    @property
    def field_guide_stem(self) -> str:
        """The `config/field_guide_<stem>.csv` this area's in-scope fields come from."""
        return {
            VehicleClass.MOTORHOME: "field_guide_motorhome",
            VehicleClass.CARAVAN: "field_guide_caravan",
        }[self]

    @property
    def registry_category(self) -> str:
        """The value this area appears as in the registry's `categories` column.

        `Manufacturer.categories` predates this enum (DESIGN.md §3: "the registry carries
        a `categories` column from day one so caravans can be switched on without a schema
        change"), and already spells them this way.
        """
        return self.value


#: The default for everything that predates the caravan work: every run in the store, and
#: every registry row, was a motorhome run. Referenced rather than hard-coded at each call
#: site so the assumption is searchable.
DEFAULT = VehicleClass.MOTORHOME
