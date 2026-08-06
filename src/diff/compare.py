"""Field-level diff between a baseline product and a freshly scraped one.

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

from ..adapters.base import ExtractedMotorhome, Provenance
from ..product_model import schema
from ..product_model.model import Motorhome

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

_PRIORITY_ORDER: dict[Priority, int] = {"tracked_numeric": 0, "other": 1, "layout": 2}


def _priority(field_path: str) -> Priority:
    if field_path in LAYOUT_FIELDS:
        return "layout"
    if field_path in TRACKED_NUMERIC_FIELDS:
        return "tracked_numeric"
    return "other"


def field_value(motorhome: Motorhome, field_path: str) -> Any:
    """Read a `Motorhome` field by name, or a nested one by dotted path.

    Shared with `store.changes.persist_diff`, which needs the same lookup for a
    `NEW_PRODUCT`'s extracted fields (there's no baseline to diff against, but the
    value still has to come from somewhere other than a hardcoded field list).
    """
    value: Any = motorhome
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


def compare_fields(
    baseline: Motorhome, extracted: ExtractedMotorhome
) -> tuple[list[FieldChange], list[str]]:
    """Diff every field the adapter extracted against a matched baseline product.

    Returns `(changes, confirmed_fields)`. `changes` are fields whose scraped value
    differs; `confirmed_fields` were checked and matched exactly — DESIGN.md §6.5
    treats that as a first-class result too, not silence.
    """
    changes: list[FieldChange] = []
    confirmed: list[str] = []

    for field_path in extracted.provenance:
        old_value = field_value(baseline, field_path)
        new_value = field_value(extracted.motorhome, field_path)
        if old_value == new_value:
            confirmed.append(field_path)
            continue
        priority = _priority(field_path)
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
    return changes, confirmed


def sort_changes(changes: Iterable[FieldChange]) -> list[FieldChange]:
    """Tracked numerics first, then everything else, then layout flags last.

    DESIGN.md §4.2 calls the numerics "the job"; a rare layout-flag change on an
    existing product is high-suspicion (§4.3) and belongs at the back of a reviewer's
    queue for that product, not the front. Sort is stable, so ties keep the order the
    adapter reported them in.
    """
    return sorted(changes, key=lambda change: _PRIORITY_ORDER[change.priority])
