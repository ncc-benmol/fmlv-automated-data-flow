"""The FMLV motorhome/campervan export schema.

Column order here is taken verbatim from a real NCC export
(`csv-examples/.../motorhome-campervans.xlsx`) and must be preserved on upload.

The field guide splits these columns into classes that behave very differently, and
the pipeline treats them differently as a result:

* ``CARRY_THROUGH`` — marked "PLEASE Leave as is!". Read from the current export and
  written back untouched. Never extracted, never diffed.
* ``REQUIRED`` — must be present for a row to be valid on upload.
* ``LAYOUT`` — the ~40 Yes/No columns, modelled internally as the enums in `enums.py`.
* ``DEALER_ONLY`` — "LEAVE BLANK UNLESS DEALER EXCLUSIVE". Not available from
  manufacturer sites, so out of scope for scraping.
"""

from __future__ import annotations

from .enums import (
    BathroomLayout,
    BedType,
    BodyType,
    Heating,
    KitchenLocation,
    LoungeLocation,
    Refrigeration,
    SleepingArea,
)

#: Exact column order of the motorhome/campervan export. Do not reorder.
COLUMNS: tuple[str, ...] = (
    "product_id",
    "year",
    "manufacturing_release_date",
    "manufacturer",
    "base_vehicle_manufacturer",
    "manufacturer_display_name",
    "manufacturer_range",
    "dealer_specials_range",
    "dealer",
    "model",
    "dealer_model_variant",
    *BodyType.columns(),
    "mh_passenger_seats_inc_driver",
    "berths",
    "rrp_pounds",
    "price_min_range_pounds",
    "price_max_range_pounds",
    "mro_kilograms",
    "mtplm_kilograms",
    "mh_payload_kilograms",
    "mh_length_mm",
    "mh_width_mm",
    "mh_height_mm",
    *SleepingArea.columns(),
    *BedType.columns(),
    *KitchenLocation.columns(),
    *BathroomLayout.columns(),
    *LoungeLocation.columns(),
    *Heating.columns(),
    "rear_garage",
    *Refrigeration.columns(),
    "microwave",
    "automatic_mro_kilograms",
    "automatic_mh_payload_kilograms",
    "automatic_rrp_pounds",
    "automatic_price_min_range_pounds",
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

#: Guide: "REQUIRED FIELD".
REQUIRED: frozenset[str] = frozenset(
    {
        "manufacturer",
        "base_vehicle_manufacturer",
        "manufacturer_display_name",
        "manufacturer_range",
        "model",
        "mh_passenger_seats_inc_driver",
        "berths",
        "rrp_pounds",
        "mro_kilograms",
        "mtplm_kilograms",
        "mh_payload_kilograms",
        "mh_length_mm",
        "mh_width_mm",
        "mh_height_mm",
    }
)

#: Guide: "LEAVE BLANK UNLESS DEALER EXCLUSIVE". Not scraped.
DEALER_ONLY: frozenset[str] = frozenset(
    {"dealer_specials_range", "dealer", "dealer_model_variant"}
)

#: The Yes/No layout columns, all of which map into an enum group.
LAYOUT: frozenset[str] = frozenset(
    [
        *BodyType.columns(),
        *SleepingArea.columns(),
        *BedType.columns(),
        *KitchenLocation.columns(),
        *BathroomLayout.columns(),
        *LoungeLocation.columns(),
        *Heating.columns(),
        *Refrigeration.columns(),
        "rear_garage",
        "microwave",
    ]
)

#: All-or-nothing group describing the automatic-gearbox variant, where one exists.
AUTOMATIC: tuple[str, ...] = (
    "automatic_mro_kilograms",
    "automatic_mh_payload_kilograms",
    "automatic_rrp_pounds",
    "automatic_price_min_range_pounds",
)

#: Numeric columns that change often — the fields a run actually chases.
TRACKED_NUMERIC: tuple[str, ...] = (
    "rrp_pounds",
    "price_min_range_pounds",
    "price_max_range_pounds",
    "mro_kilograms",
    "mtplm_kilograms",
    "mh_payload_kilograms",
    "mh_length_mm",
    "mh_width_mm",
    "mh_height_mm",
    "berths",
    "mh_passenger_seats_inc_driver",
    *AUTOMATIC,
)

YES = "Yes"
NO = "No"
IMAGE_SEPARATOR = ", "
