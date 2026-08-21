"""The canonical motorhome product.

One instance == one row of the FMLV motorhome/campervan export == one NCC product.

Fields are deliberately permissive (almost everything is optional). Real exports carry
gaps and the occasional inconsistency, and a reader that raises on those is useless for
the job. Instead the shape is enforced by `validation.check`, which reports problems as
data rather than exceptions so they can be shown to the reviewer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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


class AutomaticVariant(BaseModel):
    """Figures for the automatic-gearbox version, where the model offers one.

    Guide: "IF AUTOMATIC OPTION, COMPLETE THESE EXTRA COLUMNS TO FEATURE IN AUTOMATIC
    FILTER RESULTS (otherwise leave blank)". Effectively a second price and weight set.
    """

    model_config = ConfigDict(protected_namespaces=())

    mro_kilograms: int | None = None
    payload_kilograms: int | None = None
    rrp_pounds: int | None = None
    price_min_range_pounds: int | None = None

    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (
                self.mro_kilograms,
                self.payload_kilograms,
                self.rrp_pounds,
                self.price_min_range_pounds,
            )
        )


class Motorhome(BaseModel):
    """A single motorhome or campervan product."""

    model_config = ConfigDict(protected_namespaces=())

    # --- Carry-through: read from the export, written back untouched -----------
    # Guide marks all of these "PLEASE Leave as is!". product_id is blank for a
    # product the NCC site has not yet seen; the site mints one on upload.
    product_id: int | None = None
    year: int | None = None
    manufacturing_release_date: int | None = None
    latest_model_id: int | None = None
    images: list[str] = Field(default_factory=list)
    archived: bool = False

    #: Column names FMLV has set to `Yes` that this model cannot otherwise represent.
    #:
    #: The single-select groups (`refrigeration`, `bathroom_layout`, …) hold exactly one
    #: member each, because the FMLV guide says one should be set. Real rows disagree: 37
    #: Chausson products carry both `fridge` and `fridge_freezer`, or both
    #: `rear_shower_toilet` and `separate_shower_toilet`. Reading such a row keeps the first
    #: member and records the rest here, so writing it back re-asserts them instead of
    #: silently clearing a flag the NCC set deliberately.
    #:
    #: Adapters never populate this — a scraped product states its own layout — so it stays
    #: empty for everything except a product read back from an export.
    extra_column_flags: list[str] = Field(default_factory=list)

    # --- Identity -------------------------------------------------------------
    manufacturer: str | None = None
    base_vehicle_manufacturer: str | None = None
    manufacturer_display_name: str | None = None
    manufacturer_range: str | None = None
    model: str | None = None

    # --- Dealer-exclusive: blank unless the product is a dealer special --------
    dealer_specials_range: str | None = None
    dealer: str | None = None
    dealer_model_variant: str | None = None

    # --- Numerics: the fields that actually change between runs ---------------
    mh_passenger_seats_inc_driver: int | None = None
    berths: int | None = None
    rrp_pounds: int | None = None
    price_min_range_pounds: int | None = None
    price_max_range_pounds: int | None = None
    mro_kilograms: int | None = None
    mtplm_kilograms: int | None = None
    mh_payload_kilograms: int | None = None
    mh_length_mm: int | None = None
    mh_width_mm: int | None = None
    mh_height_mm: int | None = None

    # --- Layout: the ~40 Yes/No columns, collapsed into their real groups ------
    body_type: BodyType | None = None
    sleeping_area: SleepingArea | None = None
    bed_types: list[BedType] = Field(default_factory=list)
    kitchen_location: KitchenLocation | None = None
    bathroom_layout: BathroomLayout | None = None
    lounge_location: LoungeLocation | None = None
    heating: Heating | None = None
    refrigeration: Refrigeration | None = None
    rear_garage: bool = False
    microwave: bool = False

    automatic: AutomaticVariant | None = None

    @property
    def key(self) -> str:
        """Human-readable identity for logs and the review UI."""
        parts = [
            self.manufacturer_display_name or self.manufacturer or "?",
            self.manufacturer_range or "",
            self.model or "?",
        ]
        return " ".join(part for part in parts if part)

    @property
    def is_new(self) -> bool:
        """True when this product has no NCC-assigned ID yet."""
        return self.product_id is None

    @property
    def derived_payload_kilograms(self) -> int | None:
        """Payload implied by the two masses.

        In the sample export this matches ``mh_payload_kilograms`` exactly for every
        row, automatic figures included, so it doubles as a check on an extraction.
        """
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms
