"""Reading and writing the FMLV motorhome/campervan export.

The NCC export is an Excel workbook; the upload path is a CSV. Both share the same
column set (`schema.COLUMNS`), so one row-dict <-> Motorhome mapping serves both
directions and both formats — `read_export` dispatches on file suffix, everything
else is shared.

Parsing never raises on a single bad row or an ambiguous layout group. Problems are
collected as `validation.Issue`s alongside the parsed data (see `ReadResult`), so one
malformed row doesn't take down a whole-file read.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from . import schema
from .enums import (
    BathroomLayout,
    BedType,
    BodyType,
    Heating,
    KitchenLocation,
    LoungeLocation,
    Refrigeration,
    SleepingArea,
    ColumnEnum,
)
from .model import AutomaticVariant, Motorhome
from .validation import Issue

#: (canonical field name, enum class) for every single-select layout group.
_SINGLE_SELECT_FIELDS: tuple[tuple[str, type[ColumnEnum]], ...] = (
    ("body_type", BodyType),
    ("sleeping_area", SleepingArea),
    ("kitchen_location", KitchenLocation),
    ("bathroom_layout", BathroomLayout),
    ("lounge_location", LoungeLocation),
    ("heating", Heating),
    ("refrigeration", Refrigeration),
)


@dataclass
class ReadResult:
    """The outcome of reading an export: parsed rows plus anything that went wrong."""

    motorhomes: list[Motorhome] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Raw cell -> Python value
# --------------------------------------------------------------------------- #


def _is_yes(value: Any) -> bool:
    return value is not None and str(value).strip().lower() == schema.YES.lower()


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):  # bool is an int subclass — reject before the int check
        return None
    if isinstance(value, int | float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    return int(float(text))


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_images(value: Any) -> list[str]:
    text = _to_str(value)
    if not text:
        return []
    return [part.strip() for part in text.split(schema.IMAGE_SEPARATOR) if part.strip()]


def _select_single(
    row: dict[str, Any], enum_cls: type[ColumnEnum], product_key: str
) -> tuple[ColumnEnum | None, list[Issue]]:
    """Pick the one member whose column is 'Yes'.

    The guide says exactly one should be set, but real data can disagree — flag more
    than one as an issue rather than raising, and fall back to the first match so the
    row still parses.
    """
    matches = [member for member in enum_cls if _is_yes(row.get(member.value))]
    if len(matches) <= 1:
        return (matches[0] if matches else None), []
    issue = Issue(
        severity="warning",
        code="ambiguous_layout_group",
        message=(
            f"more than one option selected for {enum_cls.__name__}: "
            f"{[m.value for m in matches]}"
        ),
        product_key=product_key,
        field=enum_cls.__name__,
    )
    return matches[0], [issue]


def _select_many(row: dict[str, Any], enum_cls: type[ColumnEnum]) -> list[ColumnEnum]:
    return [member for member in enum_cls if _is_yes(row.get(member.value))]


def row_to_motorhome(row: dict[str, Any]) -> tuple[Motorhome, list[Issue]]:
    """Convert one raw export row (column name -> cell value) into a Motorhome."""
    issues: list[Issue] = []
    key_hint = (
        f"{row.get('manufacturer_display_name') or row.get('manufacturer') or '?'} "
        f"{row.get('model') or '?'}"
    )

    selected: dict[str, ColumnEnum | None] = {}
    for field_name, enum_cls in _SINGLE_SELECT_FIELDS:
        value, group_issues = _select_single(row, enum_cls, key_hint)
        selected[field_name] = value
        issues.extend(group_issues)

    bed_types = _select_many(row, BedType)

    automatic = AutomaticVariant(
        mro_kilograms=_to_int(row.get("automatic_mro_kilograms")),
        payload_kilograms=_to_int(row.get("automatic_mh_payload_kilograms")),
        rrp_pounds=_to_int(row.get("automatic_rrp_pounds")),
        price_min_range_pounds=_to_int(row.get("automatic_price_min_range_pounds")),
    )
    if automatic.is_empty():
        automatic = None

    motorhome = Motorhome(
        product_id=_to_int(row.get("product_id")),
        year=_to_int(row.get("year")),
        manufacturing_release_date=_to_int(row.get("manufacturing_release_date")),
        latest_model_id=_to_int(row.get("latest_model_id")),
        images=_to_images(row.get("images")),
        archived=_is_yes(row.get("archived")),
        manufacturer=_to_str(row.get("manufacturer")),
        base_vehicle_manufacturer=_to_str(row.get("base_vehicle_manufacturer")),
        manufacturer_display_name=_to_str(row.get("manufacturer_display_name")),
        manufacturer_range=_to_str(row.get("manufacturer_range")),
        model=_to_str(row.get("model")),
        dealer_specials_range=_to_str(row.get("dealer_specials_range")),
        dealer=_to_str(row.get("dealer")),
        dealer_model_variant=_to_str(row.get("dealer_model_variant")),
        mh_passenger_seats_inc_driver=_to_int(row.get("mh_passenger_seats_inc_driver")),
        berths=_to_int(row.get("berths")),
        rrp_pounds=_to_int(row.get("rrp_pounds")),
        price_min_range_pounds=_to_int(row.get("price_min_range_pounds")),
        price_max_range_pounds=_to_int(row.get("price_max_range_pounds")),
        mro_kilograms=_to_int(row.get("mro_kilograms")),
        mtplm_kilograms=_to_int(row.get("mtplm_kilograms")),
        mh_payload_kilograms=_to_int(row.get("mh_payload_kilograms")),
        mh_length_mm=_to_int(row.get("mh_length_mm")),
        mh_width_mm=_to_int(row.get("mh_width_mm")),
        mh_height_mm=_to_int(row.get("mh_height_mm")),
        bed_types=bed_types,
        rear_garage=_is_yes(row.get("rear_garage")),
        microwave=_is_yes(row.get("microwave")),
        automatic=automatic,
        **selected,
    )
    return motorhome, issues


# --------------------------------------------------------------------------- #
# Motorhome -> raw row, for writing
# --------------------------------------------------------------------------- #


def motorhome_to_row(motorhome: Motorhome) -> dict[str, str]:
    """Convert a Motorhome into a raw row dict, keyed by every column in `schema.COLUMNS`."""
    row: dict[str, str] = dict.fromkeys(schema.COLUMNS, "")

    def set_int(column: str, value: int | None) -> None:
        row[column] = "" if value is None else str(value)

    def set_str(column: str, value: str | None) -> None:
        row[column] = value or ""

    def set_yes_no(column: str, value: bool) -> None:  # noqa: FBT001
        row[column] = schema.YES if value else schema.NO

    set_int("product_id", motorhome.product_id)
    set_int("year", motorhome.year)
    set_int("manufacturing_release_date", motorhome.manufacturing_release_date)
    set_str("manufacturer", motorhome.manufacturer)
    set_str("base_vehicle_manufacturer", motorhome.base_vehicle_manufacturer)
    set_str("manufacturer_display_name", motorhome.manufacturer_display_name)
    set_str("manufacturer_range", motorhome.manufacturer_range)
    set_str("dealer_specials_range", motorhome.dealer_specials_range)
    set_str("dealer", motorhome.dealer)
    set_str("model", motorhome.model)
    set_str("dealer_model_variant", motorhome.dealer_model_variant)

    for field_name, enum_cls in _SINGLE_SELECT_FIELDS:
        selected_member = getattr(motorhome, field_name)
        for member in enum_cls:
            row[member.value] = schema.YES if member is selected_member else schema.NO

    for member in BedType:
        row[member.value] = schema.YES if member in motorhome.bed_types else schema.NO

    set_int("mh_passenger_seats_inc_driver", motorhome.mh_passenger_seats_inc_driver)
    set_int("berths", motorhome.berths)
    set_int("rrp_pounds", motorhome.rrp_pounds)
    set_int("price_min_range_pounds", motorhome.price_min_range_pounds)
    set_int("price_max_range_pounds", motorhome.price_max_range_pounds)
    set_int("mro_kilograms", motorhome.mro_kilograms)
    set_int("mtplm_kilograms", motorhome.mtplm_kilograms)
    set_int("mh_payload_kilograms", motorhome.mh_payload_kilograms)
    set_int("mh_length_mm", motorhome.mh_length_mm)
    set_int("mh_width_mm", motorhome.mh_width_mm)
    set_int("mh_height_mm", motorhome.mh_height_mm)

    set_yes_no("rear_garage", motorhome.rear_garage)
    set_yes_no("microwave", motorhome.microwave)

    automatic = motorhome.automatic or AutomaticVariant()
    set_int("automatic_mro_kilograms", automatic.mro_kilograms)
    set_int("automatic_mh_payload_kilograms", automatic.payload_kilograms)
    set_int("automatic_rrp_pounds", automatic.rrp_pounds)
    set_int("automatic_price_min_range_pounds", automatic.price_min_range_pounds)

    set_int("latest_model_id", motorhome.latest_model_id)
    set_str(
        "images",
        schema.IMAGE_SEPARATOR.join(motorhome.images) if motorhome.images else None,
    )
    set_yes_no("archived", motorhome.archived)

    return row


# --------------------------------------------------------------------------- #
# File-level read/write
# --------------------------------------------------------------------------- #


def _rows_from_xlsx(path: Path) -> Iterable[dict[str, Any]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.worksheets[0]
        rows = worksheet.iter_rows(values_only=True)
        header = [str(cell).strip() if cell is not None else "" for cell in next(rows)]
        for raw_row in rows:
            if all(cell is None for cell in raw_row):
                continue
            yield dict(zip(header, raw_row, strict=False))
    finally:
        workbook.close()


def _rows_from_csv(path: Path, *, skip_leading_blank_rows: int = 0) -> Iterable[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for _ in range(skip_leading_blank_rows):
            next(handle)
        yield from csv.DictReader(handle)


def read_rows(rows: Iterable[dict[str, Any]]) -> ReadResult:
    """Parse an already-loaded sequence of raw row dicts into a `ReadResult`."""
    result = ReadResult()
    for row in rows:
        motorhome, issues = row_to_motorhome(row)
        result.motorhomes.append(motorhome)
        result.issues.extend(issues)
    return result


def read_xlsx(path: Path | str) -> ReadResult:
    """Read a motorhome/campervan export saved as `.xlsx`."""
    return read_rows(_rows_from_xlsx(Path(path)))


def read_csv(path: Path | str, *, skip_leading_blank_rows: int = 0) -> ReadResult:
    """Read a motorhome/campervan export (or a generated upload CSV) saved as `.csv`.

    `skip_leading_blank_rows` mirrors `write_csv`'s parameter of the same name, for
    reading back a generated upload CSV (header on row 3) rather than a plain export
    (header on row 1, the default).
    """
    return read_rows(_rows_from_csv(Path(path), skip_leading_blank_rows=skip_leading_blank_rows))


def read_export(path: Path | str) -> ReadResult:
    """Read a motorhome/campervan export, dispatching on file suffix."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return read_xlsx(path)
    if suffix == ".csv":
        return read_csv(path)
    msg = f"unsupported export file type: {suffix!r} ({path})"
    raise ValueError(msg)


def write_csv(
    motorhomes: Iterable[Motorhome], path: Path | str, *, leading_blank_rows: int = 0
) -> None:
    """Write motorhomes as a CSV in the exact FMLV upload column order.

    `leading_blank_rows` writes that many empty rows before the header — the FMLV
    upload site expects the header on row 3 and data from row 4, i.e.
    `leading_blank_rows=2` (see `output.write_upload_csv`). Defaults to 0 so every
    other caller (round-tripping, tests) still gets a plain CSV with the header on
    row 1.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=schema.COLUMNS)
        for _ in range(leading_blank_rows):
            handle.write("\n")
        writer.writeheader()
        for motorhome in motorhomes:
            writer.writerow(motorhome_to_row(motorhome))
