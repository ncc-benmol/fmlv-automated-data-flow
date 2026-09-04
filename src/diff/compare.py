"""Field-level diff between a baseline product and a freshly scraped one.

Works for either product area. What differs between motorhomes and caravans — which
fields are in scope, which numerics are "the job", which flags are layout — is held in a
`FieldProfile` per area rather than branched on at each use.

Only fields the adapter actually extracted are compared. `ExtractedMotorhome.provenance`
(`adapters/base.py`) is the record of what an adapter looked at and found — a field
with no provenance entry simply wasn't attempted. Treating a missing provenance entry
as "the value is now blank" would wrongly propose clearing data the adapter never
visited: Adria's adapter, for instance, never attempts the ~40 layout flags at all
(docs/adapters/adria.md), so none of them should ever show up as a "changed" layout
field for an Adria product.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from ..adapters.base import ExtractedProduct, Provenance
from ..product_model import caravan_schema, schema
from ..product_model.caravan import Caravan
from ..product_model.enums import (
    BathroomLayout,
    BedType,
    CaravanBodyType,
    CaravanSleepingArea,
    ColumnEnum,
    Heating,
    KitchenLocation,
    LoungeLocation,
    Refrigeration,
)
from ..product_model.model import Motorhome
from ..product_model.product import Product

Priority = Literal["tracked_numeric", "layout", "other"]

#: Motorhome field names for the ~40 layout Yes/No columns, collapsed to their 10
#: enum/bool fields (fmlv/enums.py). DESIGN.md §4.2/§4.3: a change here on an
#: *existing* product is rare and worth flagging as high-suspicion rather than routine.
LAYOUT_FIELDS: frozenset[str] = frozenset(
    {
        "body_type",
        "sleeping_area",
        "bed_types",
        "kitchen_location",
        "bathroom_layout",
        "lounge_location",
        "heating",
        "refrigeration",
        "rear_garage",
        "microwave",
    }
)

#: The same for a caravan: no rear garage, and `twin_axle` in its place. It is a chassis
#: fact rather than a layout one, but it behaves identically — a Yes/No column whose value
#: changing on an existing product is rare enough to be worth a second look.
CARAVAN_LAYOUT_FIELDS: frozenset[str] = frozenset(
    {
        "body_type",
        "sleeping_area",
        "bed_types",
        "kitchen_location",
        "bathroom_layout",
        "lounge_location",
        "heating",
        "refrigeration",
        "twin_axle",
        "microwave",
    }
)

#: Export *column* -> the model **field** that carries it, for every layout group. The
#: field guides list in-scope fields by column, but `compare_fields` walks model fields:
#: a caravan's four `type_*` columns are one `body_type` field, and asking `getattr` for
#: `type_rigid` would quietly answer `None` for every product.
_COLUMN_TO_FIELD: dict[str, str] = {
    column: field_name
    for field_name, enum_cls in (
        ("body_type", CaravanBodyType),
        ("sleeping_area", CaravanSleepingArea),
        ("bed_types", BedType),
        ("kitchen_location", KitchenLocation),
        ("bathroom_layout", BathroomLayout),
        ("lounge_location", LoungeLocation),
        ("heating", Heating),
        ("refrigeration", Refrigeration),
    )
    for column in enum_cls.columns()
}


def _as_field_paths(columns: frozenset[str]) -> frozenset[str]:
    """Translate export column names into the model field paths that hold them."""
    return frozenset(_COLUMN_TO_FIELD.get(column, column) for column in columns)

#: `schema.TRACKED_NUMERIC` lists export *column* names; the four `automatic_*` ones
#: live under a nested `Motorhome.automatic` field, so they're re-expressed here as the
#: dotted field paths `compare_fields` actually looks up.
_AUTOMATIC_FIELD_PATHS: frozenset[str] = frozenset(
    {
        "automatic.mro_kilograms",
        "automatic.payload_kilograms",
        "automatic.rrp_pounds",
        "automatic.price_min_range_pounds",
    }
)

#: Motorhome field names (or dotted paths) for the numerics a run actually chases —
#: DESIGN.md §4.2 calls this "the job".
TRACKED_NUMERIC_FIELDS: frozenset[str] = (
    frozenset(name for name in schema.TRACKED_NUMERIC if not name.startswith("automatic_"))
    | _AUTOMATIC_FIELD_PATHS
)

#: The caravan equivalent. No `automatic_*` group — a towed vehicle has no gearbox — and
#: four length fields where a motorhome has one.
CARAVAN_TRACKED_NUMERIC_FIELDS: frozenset[str] = frozenset(caravan_schema.TRACKED_NUMERIC)

_PRIORITY_ORDER: dict[Priority, int] = {"tracked_numeric": 0, "other": 1, "layout": 2}


@dataclass(frozen=True)
class FieldProfile:
    """Which fields matter, for one product area.

    The two exports disagree about all three sets — a caravan has no rear garage and no
    automatic variant, has `twin_axle` and four lengths, and its in-scope list is its own.
    Holding them together in one object keeps `compare_fields` free of `isinstance`
    branching and gives the difference exactly one place to live.
    """

    in_scope: frozenset[str]
    tracked_numeric: frozenset[str]
    layout: frozenset[str]

    def priority(self, field_path: str) -> Priority:
        if field_path in self.layout:
            return "layout"
        if field_path in self.tracked_numeric:
            return "tracked_numeric"
        return "other"


MOTORHOME_PROFILE = FieldProfile(
    in_scope=_as_field_paths(schema.IN_SCOPE),
    tracked_numeric=TRACKED_NUMERIC_FIELDS,
    layout=LAYOUT_FIELDS,
)

CARAVAN_PROFILE = FieldProfile(
    in_scope=_as_field_paths(caravan_schema.IN_SCOPE),
    tracked_numeric=CARAVAN_TRACKED_NUMERIC_FIELDS,
    layout=CARAVAN_LAYOUT_FIELDS,
)


def profile_for(product: Product) -> FieldProfile:
    """The field profile for whichever product area `product` belongs to."""
    return CARAVAN_PROFILE if isinstance(product, Caravan) else MOTORHOME_PROFILE


def _priority(field_path: str) -> Priority:
    """Motorhome-area priority, kept for callers that predate `FieldProfile`."""
    return MOTORHOME_PROFILE.priority(field_path)


def field_value(product: Product, field_path: str) -> Any:
    """Read a product field by name, or a nested one by dotted path.

    Works on a `Motorhome` or a `Caravan` — it is plain attribute access, and the field
    paths come from whichever schema the product belongs to.

    Shared with `store.changes.persist_diff`, which needs the same lookup for a
    `NEW_PRODUCT`'s extracted fields (there's no baseline to diff against, but the
    value still has to come from somewhere other than a hardcoded field list).
    """
    value: Any = product
    for part in field_path.split("."):
        if value is None:
            return None
        value = getattr(value, part, None)
    return value


@dataclass(frozen=True)
class FieldChange:
    """One field whose freshly scraped value differs from the baseline."""

    field: str
    old_value: Any
    new_value: Any
    provenance: Provenance | None
    priority: Priority
    high_suspicion: bool


@dataclass(frozen=True)
class MissingField:
    """A field the adapter didn't find on a matched, existing product.

    In-scope fields are a requirement for every update, unlike other fields where
    "the adapter never looked" is silently fine. `old_value` is the baseline's current
    figure — offered to the reviewer to confirm/keep or replace, rather than the field
    just going unchecked (the user's ask this feature implements).
    """

    field: str
    old_value: Any
    #: Whether this field is in scope for automated collection, which decides the wording
    #: the reviewer is shown. Recorded here rather than re-derived downstream: the
    #: in-scope set differs per product area, and `store.changes` used to test caravan
    #: fields against the *motorhome* set — so every caravan gap was described as one the
    #: adapter "could not determine" rather than one it was required to find. Set at
    #: construction, where the right `FieldProfile` is already in hand.
    in_scope: bool = True
    #: The adapter's own evidence, when it recorded some. Populated only for a field the
    #: adapter *attempted* and could not fill — an unfound in-scope field has no
    #: provenance by construction, so this stays `None` there. It is what lets the review
    #: form show a reviewer the page and the wording that identify what kind of product
    #: this is, so they can settle the value themselves. Requested 2026-08-29.
    provenance: Provenance | None = None


def compare_fields(
    baseline: Product, extracted: ExtractedProduct
) -> tuple[list[FieldChange], list[str], list[MissingField]]:
    """Diff every field the adapter extracted against a matched baseline product.

    Returns `(changes, confirmed_fields, missing_fields)`. `changes` are fields
    whose scraped value differs; `confirmed_fields` were checked and matched
    exactly — DESIGN.md §6.5 treats that as a first-class result too, not
    silence. `missing_fields` are `schema.IN_SCOPE` fields the adapter has no
    value for at all (still `None` on `extracted.motorhome`) even though the
    baseline has one — an in-scope field must be actively confirmed or replaced,
    not left unchecked, unlike an out-of-scope field the adapter never visited.
    """
    changes: list[FieldChange] = []
    confirmed: list[str] = []
    missing: list[MissingField] = []
    profile = profile_for(extracted.product)

    for field_path in extracted.provenance:
        old_value = field_value(baseline, field_path)
        new_value = field_value(extracted.product, field_path)
        if old_value == new_value:
            confirmed.append(field_path)
            continue
        if new_value is None and old_value is not None:
            # The adapter looked and came back empty-handed — it recorded provenance
            # saying so. Proposing `None` over a good baseline value would offer a
            # reviewer an "accept" that silently blanks the field, so this takes the
            # same confirm-or-replace route as an unfound in-scope field instead.
            # Reached when an adapter can identify a field's *family* but not its value
            # (`swift._body_type_basis`); before 2026-08-29 no adapter recorded
            # provenance for an empty field, so this branch was unreachable.
            missing.append(
                MissingField(
                    field=field_path,
                    old_value=old_value,
                    in_scope=field_path in profile.in_scope,
                    provenance=extracted.provenance.get(field_path),
                )
            )
            continue
        priority = profile.priority(field_path)
        changes.append(
            FieldChange(
                field=field_path,
                old_value=old_value,
                new_value=new_value,
                provenance=extracted.provenance.get(field_path),
                priority=priority,
                high_suspicion=priority == "layout",
            )
        )

    for field_path in profile.in_scope:
        if field_path in extracted.provenance:
            continue  # already handled above
        old_value = field_value(baseline, field_path)
        new_value = field_value(extracted.product, field_path)
        if old_value is None or new_value is not None:
            continue  # nothing on record, or the adapter found a value some other way
        missing.append(MissingField(field=field_path, old_value=old_value, in_scope=True))

    return changes, confirmed, missing


def sort_changes(changes: Iterable[FieldChange]) -> list[FieldChange]:
    """Tracked numerics first, then everything else, then layout flags last.

    DESIGN.md §4.2 calls the numerics "the job"; a rare layout-flag change on an
    existing product is high-suspicion (§4.3) and belongs at the back of a reviewer's
    queue for that product, not the front. Sort is stable, so ties keep the order the
    adapter reported them in.
    """
    return sorted(changes, key=lambda change: _PRIORITY_ORDER[change.priority])
