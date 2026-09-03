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

from ..output.build import CARAVAN_UPLOAD, MOTORHOME_UPLOAD
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
