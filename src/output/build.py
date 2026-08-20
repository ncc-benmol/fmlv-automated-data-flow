"""Applying approved decisions to the baseline, and writing the upload CSV.

DESIGN.md §6.3: accept/reject/correct is *per field*, so a run's approved output is
assembled one field at a time — start from the baseline row (or a blank one for a
`NEW_PRODUCT`), then apply every `accept`/`correct` decision on top of it. A `reject`,
or a proposal never decided at all, leaves that field exactly as the baseline had it.
Carry-through fields (DESIGN.md §4.2) are untouched by construction: they're copied
from the baseline `Motorhome` and no adapter ever proposes a change to them (the one
exception, `year`, is handled the same way as any other field — see
`store/changes.py`'s year-rollover note).

A product with no `accept`/`correct` decision at all contributes nothing to the
output — there is nothing approved to upload for it.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import paths
from ..product_model.enums import (
    BathroomLayout,
    BedType,
    BodyType,
    ColumnEnum,
    Heating,
    KitchenLocation,
    LoungeLocation,
    Refrigeration,
    SleepingArea,
)
from ..product_model.io import write_csv as write_fmlv_csv
from ..product_model.model import AutomaticVariant, Motorhome
from ..product_model.validation import Issue, format_issues, validate_all
from ..registry.models import Manufacturer
from ..store.changes import LIST_SEPARATOR, ChangeQueueEntry, list_change_queue

#: Plain integer fields (weights, dimensions, prices, counts) plus `year` — the one
#: carry-through field that can legitimately appear as a proposed change, via the
#: model-year rollover route (DESIGN.md §6.9).
_INT_FIELDS: frozenset[str] = frozenset(
    {
        "year",
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
    }
)

#: Plain string identity fields. No adapter proposes changes to these yet (Adria sets
#: them directly, without provenance — see `adapters/adria.py`), but the `Adapter`
#: protocol doesn't rule it out, so they're supported here too.
_STR_FIELDS: frozenset[str] = frozenset(
    {
        "manufacturer",
        "base_vehicle_manufacturer",
        "manufacturer_display_name",
        "manufacturer_range",
        "model",
    }
)

#: Plain boolean fields: DESIGN.md §4.3's "plain yes/no" layout pair. `archived` is
#: not here — it's a carry-through field no proposal ever touches; a `DISAPPEARED`
#: product gets a `disappearance_notice` (`store/changes.py`) instead, not a proposed
#: CSV change.
_BOOL_FIELDS: frozenset[str] = frozenset({"rear_garage", "microwave"})

#: Single-select layout groups (DESIGN.md §4.3), field name -> enum class.
_ENUM_FIELDS: dict[str, type[ColumnEnum]] = {
    "body_type": BodyType,
    "sleeping_area": SleepingArea,
    "kitchen_location": KitchenLocation,
    "bathroom_layout": BathroomLayout,
    "lounge_location": LoungeLocation,
    "heating": Heating,
    "refrigeration": Refrigeration,
}

#: The automatic-gearbox variant's dotted field paths -> its own attribute name.
_AUTOMATIC_FIELDS: dict[str, str] = {
    "automatic.mro_kilograms": "mro_kilograms",
    "automatic.payload_kilograms": "payload_kilograms",
    "automatic.rrp_pounds": "rrp_pounds",
    "automatic.price_min_range_pounds": "price_min_range_pounds",
}


def _parse_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    return int(raw)


def apply_field(motorhome: Motorhome, field_name: str, raw_value: str | None) -> Motorhome:
    """Return a copy of `motorhome` with one field set from a stored decision value.

    `raw_value` is a `proposed_change.new_value`/`decision.corrected_value` string —
    the same serialisation `store.changes._serialize` produces — so this is that
    function's inverse, one field at a time.
    """
    if field_name in _INT_FIELDS:
        return motorhome.model_copy(update={field_name: _parse_int(raw_value)})

    if field_name in _STR_FIELDS:
        return motorhome.model_copy(update={field_name: raw_value or None})

    if field_name in _BOOL_FIELDS:
        return motorhome.model_copy(update={field_name: raw_value == "True"})

    if field_name in _ENUM_FIELDS:
        enum_cls = _ENUM_FIELDS[field_name]
        value = enum_cls(raw_value) if raw_value else None
        return motorhome.model_copy(update={field_name: value})

    if field_name == "bed_types":
        bed_types = (
            [BedType(part) for part in raw_value.split(LIST_SEPARATOR)] if raw_value else []
        )
        return motorhome.model_copy(update={"bed_types": bed_types})

    if field_name in _AUTOMATIC_FIELDS:
        automatic_field = _AUTOMATIC_FIELDS[field_name]
        automatic = (motorhome.automatic or AutomaticVariant()).model_copy(
            update={automatic_field: _parse_int(raw_value)}
        )
        return motorhome.model_copy(update={"automatic": automatic})

    msg = f"don't know how to apply a decision for field {field_name!r}"
    raise ValueError(msg)


def _mirror_guide_price(motorhome: Motorhome) -> Motorhome:
    """Keep `price_min_range_pounds` equal to `rrp_pounds`, as FMLV holds it.

    **FMLV carries one price in two columns.** The NCC-side rule (20 August 2026) is
    that the column headings are not meaningful — the figure is neither strictly an RRP
    nor strictly a minimum, it is the guide price taken from whatever the manufacturer
    published next to the vehicle — and both columns always hold that same figure. The
    baseline exports bear this out: across all 179 active products in six manufacturers'
    exports the two were equal on every row, never differing and never one-blank.

    So this is applied here, at the point the upload row is built, rather than being
    collected. No adapter reads `price_min_range_pounds` — it is deliberately out of
    scope in `config/field_guide_motorhome.csv` — precisely so it never reaches the
    review queue as a second price row for a reviewer to confirm alongside the first.
    Deriving it here instead keeps the two columns in step without that noise: whatever
    price a reviewer accepts, both columns carry it.

    Only ever copied where there is a price to copy. Swift, Rimor and Chausson publish
    none at all, and a blank must stay blank rather than becoming a figure nobody read.
    """
    if motorhome.rrp_pounds is None:
        return motorhome
    return motorhome.model_copy(update={"price_min_range_pounds": motorhome.rrp_pounds})


def _approved_value(entry: ChangeQueueEntry) -> str | None:
    """The value to write for one approved entry — the correction if there was one."""
    assert entry.decision is not None
    if entry.decision.action == "correct":
        return entry.decision.corrected_value
    return entry.change.new_value


def build_upload_motorhomes(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    manufacturer: Manufacturer,
    baseline: Iterable[Motorhome],
) -> list[Motorhome]:
    """Apply every accepted/corrected decision for a run on top of the baseline.

    A product with no `accept`/`correct` decision contributes nothing — see the
    module docstring. Products are returned in `list_change_queue`'s order (by range,
    then model), which is stable and matches what the reviewer saw.
    """
    baseline_by_product_id = {
        motorhome.product_id: motorhome
        for motorhome in baseline
        if motorhome.product_id is not None
    }

    entries_by_product: dict[int, list[ChangeQueueEntry]] = defaultdict(list)
    for entry in list_change_queue(connection, run_id):
        entries_by_product[entry.product.id].append(entry)

    results: list[Motorhome] = []
    for entries in entries_by_product.values():
        approved = [
            e for e in entries if e.decision is not None and e.decision.action != "reject"
        ]
        if not approved:
            continue

        product = entries[0].product
        baseline_motorhome = baseline_by_product_id.get(product.fmlv_product_id)
        motorhome = (
            baseline_motorhome.model_copy(deep=True)
            if baseline_motorhome is not None
            else Motorhome(
                manufacturer=manufacturer.fmlv_manufacturer,
                manufacturer_display_name=manufacturer.fmlv_display_name,
                manufacturer_range=product.manufacturer_range,
                model=product.model,
            )
        )

        for entry in approved:
            motorhome = apply_field(motorhome, entry.change.field, _approved_value(entry))

        results.append(_mirror_guide_price(motorhome))

    return results


@dataclass
class UploadResult:
    """What `generate_upload` produced: the CSV path plus anything worth a reviewer's eye."""

    path: Path
    motorhomes: list[Motorhome] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    issues_path: Path | None = None

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def write_upload_csv(
    motorhomes: list[Motorhome], path: Path | str
) -> tuple[list[Issue], Path | None]:
    """Validate then write the upload CSV. Never blocks the write — see `validation.py`:
    problems are reported as data so a reviewer can see exactly what's wrong with which
    row, not silently dropped or raised past the point where they'd be useful.

    Two rows, each holding a single `-`, precede the header: the FMLV upload site
    expects the header on row 3 and data from row 4, and won't parse the file
    correctly if those two rows are genuinely empty.

    Any issues found are also written to a human-readable text file alongside the CSV
    (`paths.upload_issues_path`), so a reviewer can download and read them rather than
    the JSON shape `Issue` itself has — no file is written when there's nothing to
    report."""
    issues = validate_all(motorhomes)
    write_fmlv_csv(motorhomes, path, leading_blank_rows=2)

    issues_path: Path | None = None
    if issues:
        issues_path = paths.upload_issues_path(Path(path))
        issues_path.write_text(format_issues(issues), encoding="utf-8")

    return issues, issues_path


def generate_upload(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    manufacturer: Manufacturer,
    baseline: Iterable[Motorhome],
    path: Path | str,
) -> UploadResult:
    """Build and write one run's approved changes as an upload-ready CSV.

    `path` is the caller's choice — `paths.upload_csv_path(run_id)` is the standard
    location (DESIGN.md §5: `data/uploads/run<run>_<date>_<time>_motorhome-campervans.csv`).
    """
    motorhomes = build_upload_motorhomes(
        connection, run_id=run_id, manufacturer=manufacturer, baseline=baseline
    )
    issues, issues_path = write_upload_csv(motorhomes, path)
    return UploadResult(
        path=Path(path), motorhomes=motorhomes, issues=issues, issues_path=issues_path
    )
