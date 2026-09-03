"""The canonical touring caravan.

One instance == one row of the FMLV touring-caravan export == one NCC product. The
sibling of `model.Motorhome`, and deliberately a **separate class rather than a
generalisation of it**: the two exports differ in twenty columns, and a single model
covering both would carry a base vehicle that caravans never have, a rear garage they
cannot have, and four dimension fields whose meaning changes with the product area.

Fields are as permissive as `Motorhome`'s and for the same reason — real exports carry
gaps, and a reader that raises on those is useless for the job. `validation.check_caravan`
reports problems as data.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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


class Caravan(BaseModel):
    """A single touring caravan product."""

    model_config = ConfigDict(protected_namespaces=())

    # --- Carry-through: read from the export, written back untouched -----------
    product_id: int | None = None
    year: int | None = None
    manufacturing_release_date: int | None = None
    latest_model_id: int | None = None
    images: list[str] = Field(default_factory=list)
    archived: bool = False

    #: Column names FMLV has set to `Yes` that this model cannot otherwise represent.
    #: See `model.Motorhome.extra_column_flags` — same mechanism, same reason.
    extra_column_flags: list[str] = Field(default_factory=list)

    # --- Identity -------------------------------------------------------------
    # No `base_vehicle_manufacturer`: a caravan is towed, so there is no chassis to
    # name and the column does not exist in the export.
    manufacturer: str | None = None
    manufacturer_display_name: str | None = None
    manufacturer_range: str | None = None
    model: str | None = None

    # --- Dealer-exclusive: blank unless the product is a dealer special --------
    dealer_specials_range: str | None = None
    dealer: str | None = None
    dealer_model_variant: str | None = None

    # --- Numerics -------------------------------------------------------------
    berths: int | None = None
    rrp_pounds: int | None = None
    price_min_range_pounds: int | None = None
    price_max_range_pounds: int | None = None
    mtplm_kilograms: int | None = None
    mro_kilograms: int | None = None

    #: Payload is split in two here, where a motorhome has one column.
    #: `optional_equipment_payload_kilograms` is populated on none of the 92 real caravan
    #: products this project holds, so `personal_effects_payload_kilograms` carries the
    #: whole of `mtplm - mro` in practice — see `derived_payload_kilograms`.
    optional_equipment_payload_kilograms: int | None = None
    personal_effects_payload_kilograms: int | None = None

    #: Four different lengths, and they are not interchangeable. `internal` is the
    #: habitable space, `exterior_body` the body, `shipping` the body plus the towing
    #: hitch (always the larger of those two), and `awning` the awning rail measurement,
    #: which is not a vehicle dimension at all and routinely exceeds the body length.
    internal_length_mm: int | None = None
    exterior_body_length_mm: int | None = None
    shipping_length_mm: int | None = None
    awning_length_mm: int | None = None

    overall_width_mm: int | None = None
    height_mm: int | None = None
    headroom_mm: int | None = None

    # --- Layout ---------------------------------------------------------------
    body_type: CaravanBodyType | None = None
    sleeping_area: CaravanSleepingArea | None = None
    bed_types: list[BedType] = Field(default_factory=list)
    kitchen_location: KitchenLocation | None = None
    bathroom_layout: BathroomLayout | None = None
    lounge_location: LoungeLocation | None = None
    heating: Heating | None = None
    refrigeration: Refrigeration | None = None
    twin_axle: bool = False
    microwave: bool = False

    #: Whether a door or a firm partition divides the toilet from the shower.
    #:
    #: **Independent of where the washroom is**, which is the whole reason it is its own
    #: field. A washroom sits somewhere — on the side, or across the rear — and separately
    #: either does or does not divide the two. Bailey build seven caravans that are *both*
    #: side-mounted *and* separated, and FMLV's single `bathroom_layout` column can only
    #: record one of those facts: five of the seven are held as `side_shower_toilet` and two
    #: as `separate_shower_toilet`, which is one column being asked to answer two questions.
    #: The requester's words, 3 September 2026: "one is the location, and the other is the
    #: construction or the nature of the bathroom, whether it's separate or not."
    #:
    #: **Not yet an export column**, so it is deliberately absent from
    #: `caravan_schema.COLUMNS` and never written to an upload CSV — the NCC's importer
    #: takes 62 columns in a fixed order and a 63rd would at best be ignored. It is carried
    #: here so the habitation pack and any adapter can record it now, and so wiring it into
    #: the export is a one-line change once the NCC adds the column. See
    #: `caravan_schema.PROPOSED_COLUMNS`.
    #:
    #: `None` means nobody has assessed this product, which is different from `False`.
    shower_toilet_separated: bool | None = None

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
        """Payload implied by the two masses, i.e. what the two payload columns must sum to.

        On Bailey's 81 products this equals `personal_effects_payload_kilograms` exactly on
        75, with `optional_equipment_payload_kilograms` blank throughout. The six that
        disagree are all archived rows: two out by 1kg (rounding) and two by 21kg and 49kg,
        which are real discrepancies in FMLV's own data. That is why the check *reports*
        rather than rejects — see `validation.check_caravan`.
        """
        if self.mtplm_kilograms is None or self.mro_kilograms is None:
            return None
        return self.mtplm_kilograms - self.mro_kilograms

    @property
    def published_payload_kilograms(self) -> int | None:
        """The two payload columns added together, treating a blank as zero.

        Blank-as-zero is right here rather than sloppy: the columns are alternatives, and
        `optional_equipment` being empty is its normal state, not missing data. Returns
        `None` only when *both* are blank, which is genuinely nothing to check.
        """
        optional = self.optional_equipment_payload_kilograms
        personal = self.personal_effects_payload_kilograms
        if optional is None and personal is None:
            return None
        return (optional or 0) + (personal or 0)

    @property
    def hitch_length_mm(self) -> int | None:
        """How much longer the shipping length is than the body — the towing gear.

        845-1500mm across Bailey's range. A negative or zero result means the two length
        columns have been mapped the wrong way round, which is the single most plausible
        way to get a caravan adapter wrong: both numbers are lengths, both are in the spec
        table, and swapping them looks entirely reasonable on any one product.
        """
        if self.shipping_length_mm is None or self.exterior_body_length_mm is None:
            return None
        return self.shipping_length_mm - self.exterior_body_length_mm
