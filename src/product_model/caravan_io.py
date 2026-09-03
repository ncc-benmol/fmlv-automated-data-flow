"""Reading and writing the FMLV touring-caravan export.

The sibling of `io.py`. Same shape of job — one row-dict <-> `Caravan` mapping serving
both the `.xlsx` the NCC exports and the `.csv` we upload — and the same rule that a
single bad row never takes down a whole-file read: problems come back as
`validation.Issue`s alongside the parsed data.

The low-level cell coercions (`_to_int`, `_to_str`, `_is_yes`, `_to_images`) and the
ambiguous-group handling are imported from `io` rather than copied. They are about the
*export format*, which the two product areas share exactly, not about either schema.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import caravan_schema, schema
from .caravan import Caravan
from .enums import (
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
from .io import _is_yes, _rows_from_csv, _rows_from_xlsx, _select_many, _select_single, _to_images
from .io import _to_int as _to_int
from .io import _to_str as _to_str
from .validation import Issue

#: (canonical field name, enum class) for every single-select layout group on a caravan.
#: Body type and sleeping area differ from the motorhome set; the other five are shared.
_SINGLE_SELECT_FIELDS: tuple[tuple[str, type[ColumnEnum]], ...] = (
    ("body_type", CaravanBodyType),
    ("sleeping_area", CaravanSleepingArea),
    ("kitchen_location", KitchenLocation),
    ("bathroom_layout", BathroomLayout),
    ("lounge_location", LoungeLocation),
    ("heating", Heating),
    ("refrigeration", Refrigeration),
)


@dataclass
class CaravanReadResult:
    """The outcome of reading a caravan export: parsed rows plus anything that went wrong."""

    caravans: list[Caravan] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Raw row -> Caravan
# --------------------------------------------------------------------------- #


def row_to_caravan(row: dict[str, Any]) -> tuple[Caravan, list[Issue]]:
    """Convert one raw export row (column name -> cell value) into a `Caravan`."""
    issues: list[Issue] = []
    key_hint = (
        f"{row.get('manufacturer_display_name') or row.get('manufacturer') or '?'} "
        f"{row.get('model') or '?'}"
    )

    selected: dict[str, ColumnEnum | None] = {}
    extra_column_flags: list[str] = []
    for field_name, enum_cls in _SINGLE_SELECT_FIELDS:
        value, extras, group_issues = _select_single(row, enum_cls, key_hint)
        selected[field_name] = value
        extra_column_flags.extend(extras)
        issues.extend(group_issues)

    caravan = Caravan(
        product_id=_to_int(row.get("product_id")),
        year=_to_int(row.get("year")),
        manufacturing_release_date=_to_int(row.get("manufacturing_release_date")),
        latest_model_id=_to_int(row.get("latest_model_id")),
        images=_to_images(row.get("images")),
        archived=_is_yes(row.get("archived")),
        extra_column_flags=extra_column_flags,
        manufacturer=_to_str(row.get("manufacturer")),
        manufacturer_display_name=_to_str(row.get("manufacturer_display_name")),
        manufacturer_range=_to_str(row.get("manufacturer_range")),
        model=_to_str(row.get("model")),
        dealer_specials_range=_to_str(row.get("dealer_specials_range")),
        dealer=_to_str(row.get("dealer")),
        dealer_model_variant=_to_str(row.get("dealer_model_variant")),
        berths=_to_int(row.get("berths")),
        rrp_pounds=_to_int(row.get("rrp_pounds")),
        price_min_range_pounds=_to_int(row.get("price_min_range_pounds")),
        price_max_range_pounds=_to_int(row.get("price_max_range_pounds")),
        mtplm_kilograms=_to_int(row.get("mtplm_kilograms")),
        mro_kilograms=_to_int(row.get("mro_kilograms")),
        optional_equipment_payload_kilograms=_to_int(
            row.get("optional_equipment_payload_kilograms")
        ),
        personal_effects_payload_kilograms=_to_int(
            row.get("personal_effects_payload_kilograms")
        ),
        internal_length_mm=_to_int(row.get("internal_length_mm")),
        exterior_body_length_mm=_to_int(row.get("exterior_body_length_mm")),
        shipping_length_mm=_to_int(row.get("shipping_length_mm")),
        awning_length_mm=_to_int(row.get("awning_length_mm")),
        overall_width_mm=_to_int(row.get("overall_width_mm")),
        height_mm=_to_int(row.get("height_mm")),
        headroom_mm=_to_int(row.get("headroom_mm")),
        bed_types=_select_many(row, BedType),
        twin_axle=_is_yes(row.get("twin_axle")),
        microwave=_is_yes(row.get("microwave")),
        **selected,
    )
    return caravan, issues


# --------------------------------------------------------------------------- #
# Caravan -> raw row, for writing
# --------------------------------------------------------------------------- #


def caravan_to_row(caravan: Caravan) -> dict[str, str]:
    """Convert a `Caravan` into a raw row dict, keyed by every caravan export column."""
    row: dict[str, str] = dict.fromkeys(caravan_schema.COLUMNS, "")

    def set_int(column: str, value: int | None) -> None:
        row[column] = "" if value is None else str(value)

    def set_str(column: str, value: str | None) -> None:
        row[column] = value or ""

    def set_yes_no(column: str, value: bool) -> None:  # noqa: FBT001
        row[column] = schema.YES if value else schema.NO

    set_int("product_id", caravan.product_id)
    set_int("year", caravan.year)
    set_int("manufacturing_release_date", caravan.manufacturing_release_date)
    set_str("manufacturer", caravan.manufacturer)
    set_str("manufacturer_display_name", caravan.manufacturer_display_name)
    set_str("manufacturer_range", caravan.manufacturer_range)
    set_str("dealer_specials_range", caravan.dealer_specials_range)
    set_str("dealer", caravan.dealer)
    set_str("model", caravan.model)
    set_str("dealer_model_variant", caravan.dealer_model_variant)

    for field_name, enum_cls in _SINGLE_SELECT_FIELDS:
        selected_member = getattr(caravan, field_name)
        for member in enum_cls:
            row[member.value] = schema.YES if member is selected_member else schema.NO

    # Re-assert flags FMLV holds that the single-select fields above have just written
    # off — see `Motorhome.extra_column_flags`.
    for column in caravan.extra_column_flags:
        if column in row:
            row[column] = schema.YES

    for member in BedType:
        row[member.value] = schema.YES if member in caravan.bed_types else schema.NO

    set_int("berths", caravan.berths)
    set_int("rrp_pounds", caravan.rrp_pounds)
    set_int("price_min_range_pounds", caravan.price_min_range_pounds)
    set_int("price_max_range_pounds", caravan.price_max_range_pounds)
    set_int("mtplm_kilograms", caravan.mtplm_kilograms)
    set_int("mro_kilograms", caravan.mro_kilograms)
    set_int(
        "optional_equipment_payload_kilograms", caravan.optional_equipment_payload_kilograms
    )
    set_int("personal_effects_payload_kilograms", caravan.personal_effects_payload_kilograms)
    set_int("internal_length_mm", caravan.internal_length_mm)
    set_int("overall_width_mm", caravan.overall_width_mm)
    set_int("exterior_body_length_mm", caravan.exterior_body_length_mm)
    set_int("shipping_length_mm", caravan.shipping_length_mm)
    set_int("height_mm", caravan.height_mm)
    set_int("awning_length_mm", caravan.awning_length_mm)
    set_int("headroom_mm", caravan.headroom_mm)

    set_yes_no("twin_axle", caravan.twin_axle)
    set_yes_no("microwave", caravan.microwave)

    set_int("latest_model_id", caravan.latest_model_id)
    set_str(
        "images",
        schema.IMAGE_SEPARATOR.join(caravan.images) if caravan.images else None,
    )
    set_yes_no("archived", caravan.archived)

    return row


# --------------------------------------------------------------------------- #
# File-level read/write
# --------------------------------------------------------------------------- #


def read_rows(rows: Iterable[dict[str, Any]]) -> CaravanReadResult:
    """Parse an already-loaded sequence of raw row dicts into a `CaravanReadResult`."""
    result = CaravanReadResult()
    for row in rows:
        caravan, issues = row_to_caravan(row)
        result.caravans.append(caravan)
        result.issues.extend(issues)
    return result


def read_xlsx(path: Path | str) -> CaravanReadResult:
    """Read a touring-caravan export saved as `.xlsx`."""
    return read_rows(_rows_from_xlsx(Path(path)))


def read_csv(path: Path | str, *, skip_leading_blank_rows: int = 0) -> CaravanReadResult:
    """Read a touring-caravan export, or a generated upload CSV, saved as `.csv`."""
    return read_rows(_rows_from_csv(Path(path), skip_leading_blank_rows=skip_leading_blank_rows))


def read_export(path: Path | str) -> CaravanReadResult:
    """Read a touring-caravan export, dispatching on file suffix."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return read_xlsx(path)
    if suffix == ".csv":
        return read_csv(path)
    msg = f"unsupported export file type: {suffix!r} ({path})"
    raise ValueError(msg)


def write_csv(
    caravans: Iterable[Caravan], path: Path | str, *, leading_blank_rows: int = 0
) -> None:
    """Write caravans as a CSV in the exact FMLV upload column order.

    `leading_blank_rows` behaves as `io.write_csv`'s does — the FMLV upload site wants the
    header on row 3, so the real upload path passes 2.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=caravan_schema.COLUMNS)
        for _ in range(leading_blank_rows):
            handle.write("-\n")
        writer.writeheader()
        for caravan in caravans:
            writer.writerow(caravan_to_row(caravan))
