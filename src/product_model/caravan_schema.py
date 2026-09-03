"""The FMLV touring-caravan export schema.

The sibling of `schema.py`. Column order is taken verbatim from a real NCC export
(`data/exports/28_Bailey/…_touring-caravans.xlsx`, 81 products, cross-checked against
Adria's 11) and must be preserved on upload.

**Where it differs from the motorhome schema** — 62 columns against 68, and the overlap
is less than the count suggests:

* **No base vehicle.** A caravan is towed, so `base_vehicle_manufacturer`,
  `mh_passenger_seats_inc_driver` and the four `automatic_*` gearbox columns have no
  caravan equivalent. `rear_garage` and `sleeping_area_separate_childrens_area` are gone
  too.
* **Different body types** — rigid/folding/pop-up/micro rather than the eight
  campervan and coachbuilt shapes (`enums.CaravanBodyType`).
* **Renamed dimensions.** `mh_length_mm`/`mh_width_mm`/`mh_height_mm` become
  `exterior_body_length_mm`/`overall_width_mm`/`height_mm`.
* **Four lengths, not one**, and telling them apart matters more than the names admit:
  `internal_length_mm` is the habitable space; `exterior_body_length_mm` is the body;
  `shipping_length_mm` adds the towing hitch, so it is always the larger of the two (by
  845-1500mm across Bailey's range); and `awning_length_mm` is the awning rail
  measurement rather than a vehicle dimension at all, running to 11557mm on a van less
  than half that long. Mapping shipping and exterior body the wrong way round would be
  quiet, plausible and wrong on every product at once.
* **Split payload.** There is no single payload column. `mtplm - mro` is
  `personal_effects_payload_kilograms` plus `optional_equipment_payload_kilograms`, and
  the latter is populated on **none** of the 92 real caravan products this project holds
  — so in practice the check is `mtplm - mro == personal_effects`.
* **Two extras with no motorhome counterpart**: `twin_axle` and `headroom_mm`.
"""

from __future__ import annotations

import csv

from .. import paths
from ..vehicle_class import VehicleClass
from .enums import (
    BathroomLayout,
    BedType,
    CaravanBodyType,
    CaravanSleepingArea,
    Heating,
    KitchenLocation,
    LoungeLocation,
    Refrigeration,
)

#: Bed types and kitchen locations in the order the *caravan* export lists them, which
#: is not the order the motorhome export uses — beds run make-up/fixed/bunks/separate/
#: island/transverse here against make-up/fixed/transverse/island/separate/bunks there,
#: and kitchens side/rear/corner against rear/side/corner.
#:
#: The members are identical, so the enums are shared; only the column *order* differs,
#: and that belongs to the schema rather than the enum. Spelled out rather than sorted
#: from the enum so the contract with the importer is visible, and checked below for
#: completeness so adding an enum member cannot silently drop a column.
_BED_TYPE_COLUMNS: tuple[str, ...] = (
    "make_up_beds",
    "fixed_bed",
    "fixed_bunks",
    "fixed_separate_beds",
    "island_bed",
    "transverse_bed",
    "drop_down_bed",
)

_KITCHEN_COLUMNS: tuple[str, ...] = ("side_kitchen", "rear_kitchen", "corner_kitchen")

assert set(_BED_TYPE_COLUMNS) == set(BedType.columns()), (
    "caravan bed-type columns have drifted from the BedType enum"
)
assert set(_KITCHEN_COLUMNS) == set(KitchenLocation.columns()), (
    "caravan kitchen columns have drifted from the KitchenLocation enum"
)

#: Exact column order of the touring-caravan export. Do not reorder.
#:
#: Note `mtplm_kilograms` precedes `mro_kilograms` here and follows it in the motorhome
#: export. Harmless while both are written by name, and exactly the sort of thing that
#: stops being harmless the moment anyone writes a row positionally.
COLUMNS: tuple[str, ...] = (
    "product_id",
    "year",
    "manufacturing_release_date",
    "manufacturer",
    "manufacturer_display_name",
    "manufacturer_range",
    "dealer_specials_range",
    "dealer",
    "model",
    "dealer_model_variant",
    *CaravanBodyType.columns(),
    "berths",
    "rrp_pounds",
    "price_min_range_pounds",
    "price_max_range_pounds",
    "mtplm_kilograms",
    "mro_kilograms",
    "optional_equipment_payload_kilograms",
    "personal_effects_payload_kilograms",
    "internal_length_mm",
    "overall_width_mm",
    "exterior_body_length_mm",
    "shipping_length_mm",
    "height_mm",
    "awning_length_mm",
    "twin_axle",
    "headroom_mm",
    *CaravanSleepingArea.columns(),
    *_BED_TYPE_COLUMNS,
    *_KITCHEN_COLUMNS,
    *BathroomLayout.columns(),
    *LoungeLocation.columns(),
    *Heating.columns(),
    *Refrigeration.columns(),
    "microwave",
    "latest_model_id",
    "images",
    "archived",
)

#: Written back exactly as read. Guide: "PLEASE Leave as is!"
CARRY_THROUGH: frozenset[str] = frozenset(
    {
        "product_id",
        "year",
        "manufacturing_release_date",
        "latest_model_id",
        "images",
        "archived",
    }
)

#: Guide: "REQUIRED FIELD". No `base_vehicle_manufacturer` and no passenger seats, and
#: `personal_effects_payload_kilograms` takes the place the motorhome payload held.
REQUIRED: frozenset[str] = frozenset(
    {
        "manufacturer",
        "manufacturer_display_name",
        "manufacturer_range",
        "model",
        "berths",
        "rrp_pounds",
        "mtplm_kilograms",
        "mro_kilograms",
        "personal_effects_payload_kilograms",
        "internal_length_mm",
        "overall_width_mm",
        "exterior_body_length_mm",
        "shipping_length_mm",
        "height_mm",
        "awning_length_mm",
        "headroom_mm",
    }
)

#: Guide: "LEAVE BLANK UNLESS DEALER EXCLUSIVE". Not scraped.
DEALER_ONLY: frozenset[str] = frozenset(
    {"dealer_specials_range", "dealer", "dealer_model_variant"}
)


def _load_in_scope() -> frozenset[str]:
    """Read `config/field_guide_caravan.csv`'s scope column, as `schema.py` does its own."""
    with paths.field_guide_path(VehicleClass.CARAVAN).open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        return frozenset(
            row["field_name"]
            for row in csv.DictReader(handle)
            if row.get("automated_collection_scope_flag", "").strip() == "in_scope"
        )


#: Every run must attempt these — see `schema.IN_SCOPE`.
IN_SCOPE: frozenset[str] = _load_in_scope()

#: The Yes/No layout columns, all of which map into an enum group or a plain bool.
#:
#: `twin_axle` sits here rather than with the dimensions despite being a chassis fact:
#: it is a Yes/No column, it is what `diff.compare` needs to treat as a layout-priority
#: change, and it behaves exactly like `microwave` does on the motorhome side.
LAYOUT: frozenset[str] = frozenset(
    [
        *CaravanBodyType.columns(),
        *CaravanSleepingArea.columns(),
        *BedType.columns(),
        *KitchenLocation.columns(),
        *BathroomLayout.columns(),
        *LoungeLocation.columns(),
        *Heating.columns(),
        *Refrigeration.columns(),
        "twin_axle",
        "microwave",
    ]
)

#: Numeric columns that change often — the fields a run actually chases.
#: `optional_equipment_payload_kilograms` is deliberately absent: it is out of scope in
#: the field guide and unpopulated on every real caravan product this project holds.
TRACKED_NUMERIC: tuple[str, ...] = (
    "rrp_pounds",
    "price_min_range_pounds",
    "price_max_range_pounds",
    "mtplm_kilograms",
    "mro_kilograms",
    "personal_effects_payload_kilograms",
    "internal_length_mm",
    "overall_width_mm",
    "exterior_body_length_mm",
    "shipping_length_mm",
    "height_mm",
    "awning_length_mm",
    "headroom_mm",
    "berths",
)
