"""Selectable values for the single-select layout fields, for the review form.

`body_type`, `sleeping_area` and the rest are enums whose CSV serialisation is a column
name (`type_campervan_high_top`), not something anyone should be asked to type. Until
2026-08-29 the review form offered a free-text "corrected value" box for every field, so
correcting one of these meant reproducing the exact string — and getting it wrong meant
`output.build.apply_field` raising `ValueError` at upload time, well after the review.

So these fields get a `<select>` instead. The options come from the enum itself, and
`option_labels` gives the wording a reviewer actually recognises.

**Requested by the requester, 29 August 2026**, after the first Swift review found the 15
new products with no body type: "if a new model has no specific copy about the type other
than that it is a generic campervan or a generic motorhome, could we propose in the
reviews that the product is a campervan and we need to select the type of campervan".

The two halves of that are separate, and only this half needed new code:

* **Surfacing it.** Already supported — `store.changes.persist_diff` records a proposed
  change for *every* field an adapter puts in `provenance` on a new product, including
  one whose value is `None`. An adapter that knows the family but not the subtype says so
  by recording provenance with no value; see `swift._body_type_basis`.
* **Choosing it.** This module.
"""

from __future__ import annotations

from ..output.build import CARAVAN_UPLOAD, MOTORHOME_UPLOAD, upload_profile
from ..product_model import caravan_schema, schema
from ..product_model.enums import BodyType, CaravanBodyType
from ..vehicle_class import DEFAULT as DEFAULT_VEHICLE_CLASS
from ..vehicle_class import VehicleClass

#: Human wording per enum member, keyed by its CSV column name. FMLV's own column headings
#: are the source (`config/field_guide_motorhome.csv`), lightly expanded where the heading
#: alone is ambiguous out of context.
_LABELS: dict[str, str] = {
    "type_micro": "Micro",
    "type_campervan": "Campervan — standard roof",
    "type_campervan_elevating_roof": "Campervan — standard roof, elevating roof",
    "type_campervan_high_top": "Campervan — high top",
    "type_campervan_high_top_elevating_roof": "Campervan — high top, elevating roof",
    "type_coach_built_low_profile": "Coach built — low profile",
    "type_coach_built_over_cab_bed": "Coach built — over-cab bed",
    "type_a_class": "A class",
    # Touring caravans. `type_micro` is shared with the motorhome list above and means
    # something different here: a caravan is a micro only where the manufacturer calls it
    # one *and* its MTPLM is 1250kg or lower — it should be towable by a very small car.
    "type_rigid": "Rigid",
    "type_folding": "Folding",
    "type_pop_up": "Pop up",
}

#: Which group each body type belongs to, so the four campervan types and the three
#: coachbuilt ones are offered apart rather than as one list of eight. The requester
#: described exactly these two groups.
_BODY_TYPE_GROUPS: dict[str, str] = {
    "type_micro": "Campervan",
    "type_campervan": "Campervan",
    "type_campervan_elevating_roof": "Campervan",
    "type_campervan_high_top": "Campervan",
    "type_campervan_high_top_elevating_roof": "Campervan",
    "type_coach_built_low_profile": "Motorhome",
    "type_coach_built_over_cab_bed": "Motorhome",
    "type_a_class": "Motorhome",
}


def field_choices(
    field: str, vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Selectable `(group, [(value, label), ...])` pairs for `field`, or `[]`.

    An empty list means "not a single-select field", and the form falls back to the
    free-text box it has always shown — so every other field, and every other adapter, is
    unaffected.

    Body types are grouped; the other enums are returned under one unnamed group, which
    the template renders as a plain option list.
    """
    # Both areas call their layout fields the same things — `body_type`, `sleeping_area` —
    # while meaning different enums, so the area has to be stated rather than guessed. A
    # caravan reviewer offered `type_a_class` would be able to submit a value the caravan
    # importer has no column for.
    profile = CARAVAN_UPLOAD if VehicleClass(vehicle_class) is VehicleClass.CARAVAN else MOTORHOME_UPLOAD
    enum_cls = profile.enum_fields.get(field)
    if enum_cls is None:
        return []

    if enum_cls is CaravanBodyType:
        # Ungrouped: four options, and unlike the motorhome list they do not split into
        # two families a reviewer thinks of separately.
        return [("", [(m.value, label_for(m.value)) for m in enum_cls])]

    if enum_cls is BodyType:
        groups: dict[str, list[tuple[str, str]]] = {}
        for member in enum_cls:
            group = _BODY_TYPE_GROUPS.get(member.value, "Other")
            groups.setdefault(group, []).append((member.value, label_for(member.value)))
        return list(groups.items())

    return [("", [(member.value, label_for(member.value)) for member in enum_cls])]


def label_for(value: str | None) -> str:
    """The reviewer-facing wording for one stored value."""
    if not value:
        return "—"
    return _LABELS.get(value, value)


def is_valid_choice(
    field: str, value: str, vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS
) -> bool:
    """Whether `value` is one of `field`'s selectable values.

    Guards the decide endpoint: a select can only submit a real option, but the endpoint
    is a plain POST and nothing stops a malformed one reaching `apply_field`, which would
    raise at upload time rather than at review time.
    """
    return any(
        value == option
        for _group, options in field_choices(field, vehicle_class)
        for option, _ in options
    )


def is_required_field(field: str, vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS) -> bool:
    """Whether FMLV's field guide marks `field` as a required column.

    Not a bar on blanking — it decides the *warning* the reviewer sees before doing it.
    All four fields Swift withdrew for 2027 are required (`internal_length_mm`,
    `height_mm`, `awning_length_mm`, `personal_effects_payload_kilograms`), so clearing
    one leaves `validation.check_caravan` reporting "required field ... is missing" against
    the generated CSV. That report is correct and worth keeping: the row really does now
    have a gap FMLV expects filled. It just should not be the first the reviewer hears of
    it, hours later at upload.
    """
    required = (
        caravan_schema.REQUIRED
        if VehicleClass(vehicle_class) is VehicleClass.CARAVAN
        else schema.REQUIRED
    )
    return field in required


def can_be_blanked(field: str, vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS) -> bool:
    """Whether a reviewer may clear `field` outright rather than keep or replace it.

    The third answer to a field the adapter could not find, requested 3 September 2026:
    where a manufacturer has *withdrawn* a spec, FMLV holding a stale figure can be worse
    than holding nothing. Swift's caravans are the case in point — the 2027 site publishes
    no internal length, height or awning size at all, so each arrives as a flagged no-op
    on 24 products and, until now, could only be preserved.

    **Not offered for every field, because not every column can hold a blank**, and the
    two failure modes are silent ones:

    * **Booleans write `False`, not empty.** `apply_field` maps an absent value to `False`
      for `twin_axle` and `microwave`, and FMLV holds those as `No`. So "leave blank" on an
      axle count would quietly assert *single axle* rather than *unknown* — a worse answer
      than the figure it replaced.
    * **The string fields are the product's identity** — `manufacturer`,
      `manufacturer_display_name`, `manufacturer_range` and `model`. Clearing one takes the
      row below `diff.matching`'s threshold and orphans its FMLV product id, which
      `docs/adapters/README.md` describes at length under renames. A measurement can be
      unknown; a vehicle's name cannot.

    What is left is exactly what a reviewer means by "we don't know this": the numeric
    measurements, the layout and body-type enums, and the automatic-variant weights. All
    three map cleanly to an empty column in `apply_field`.

    `bed_types` is excluded too. It is a list, so its empty state is `[]` rather than
    `None`, and "no bed types recorded" and "this vehicle has no beds" would serialise
    identically — a distinction worth keeping until someone asks for it.
    """
    profile = upload_profile(vehicle_class)
    return (
        field in profile.int_fields
        or field in profile.enum_fields
        or field in profile.automatic_fields
    )
