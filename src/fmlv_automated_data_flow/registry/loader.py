"""Loading `data/manufacturers.csv`.

Mirrors the approach in `fmlv.io`: a single bad row is reported as an `Issue`, not
raised, so one malformed registry entry doesn't stop every other manufacturer from
loading. Two cross-row checks run as the file loads: duplicate `manufacturer_id`s, and
duplicate `website_url`s — the latter catches copy-paste mistakes between adjacent
rows (two different brands accidentally pointing at the same site).
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .models import Manufacturer, Status, TriState

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    """One problem found while loading the registry."""

    severity: Severity
    code: str
    message: str
    row_number: int  # 1-indexed; row 1 is the header, so data starts at 2
    manufacturer_id: int | None = None


@dataclass
class LoadResult:
    manufacturers: list[Manufacturer] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _to_int(value: str | None) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _to_bool(value: str | None) -> bool | None:
    text = (_clean(value) or "").lower()
    if text in {"yes", "true", "1"}:
        return True
    if text in {"no", "false", "0"}:
        return False
    return None


def _split_categories(value: str | None) -> tuple[str, ...]:
    text = _clean(value)
    if text is None:
        return ()
    return tuple(part.strip().lower() for part in text.split(",") if part.strip())


#: A row is a spare placeholder — not a real manufacturer — if none of these three
#: identifying columns are filled in. The template ships with `status=active`
#: pre-filled on spare rows, so checking every column would misclassify them as
#: real-but-broken rows instead of correctly ignoring them.
_IDENTIFYING_COLUMNS = ("manufacturer_id", "fmlv_manufacturer", "website_url")


def _is_blank_row(row: dict[str, str]) -> bool:
    """True for the spare placeholder rows the registry template ships with."""
    return not any(_clean(row.get(column)) for column in _IDENTIFYING_COLUMNS)


def _row_to_manufacturer(
    row: dict[str, str], row_number: int
) -> tuple[Manufacturer | None, list[Issue]]:
    if _is_blank_row(row):
        return None, []

    issues: list[Issue] = []
    manufacturer_id = _to_int(row.get("manufacturer_id"))
    fmlv_manufacturer = _clean(row.get("fmlv_manufacturer"))
    website_url = _clean(row.get("website_url"))

    if manufacturer_id is None:
        issues.append(
            Issue(
                severity="error",
                code="missing_manufacturer_id",
                message="manufacturer_id is required and must be an integer",
                row_number=row_number,
            )
        )
    if fmlv_manufacturer is None:
        issues.append(
            Issue(
                severity="error",
                code="missing_fmlv_manufacturer",
                message=(
                    "fmlv_manufacturer is required — must match the FMLV export's "
                    "'manufacturer' column exactly"
                ),
                row_number=row_number,
                manufacturer_id=manufacturer_id,
            )
        )
    if website_url is None:
        issues.append(
            Issue(
                severity="error",
                code="missing_website_url",
                message="website_url is required",
                row_number=row_number,
                manufacturer_id=manufacturer_id,
            )
        )

    if manufacturer_id is None or fmlv_manufacturer is None or website_url is None:
        # Can't build a usable row without these — already reported above.
        return None, issues

    categories = _split_categories(row.get("categories"))
    if not categories:
        issues.append(
            Issue(
                severity="warning",
                code="categories_unset",
                message=(
                    "categories is blank; assuming this manufacturer is in scope "
                    "for motorhomes (the prototype's only scope) until confirmed"
                ),
                row_number=row_number,
                manufacturer_id=manufacturer_id,
            )
        )

    status_raw = (_clean(row.get("status")) or Status.ACTIVE.value).lower()
    try:
        status = Status(status_raw)
    except ValueError:
        issues.append(
            Issue(
                severity="warning",
                code="unknown_status",
                message=f"unrecognised status '{status_raw}', treating as active",
                row_number=row_number,
                manufacturer_id=manufacturer_id,
            )
        )
        status = Status.ACTIVE

    needs_js_raw = (_clean(row.get("needs_javascript")) or TriState.UNKNOWN.value).lower()
    try:
        needs_javascript = TriState(needs_js_raw)
    except ValueError:
        needs_javascript = TriState.UNKNOWN

    manufacturer = Manufacturer(
        manufacturer_id=manufacturer_id,
        fmlv_manufacturer=fmlv_manufacturer,
        fmlv_display_name=_clean(row.get("fmlv_display_name")),
        categories=categories,
        status=status,
        pilot_priority=_to_int(row.get("pilot_priority")),
        country=_clean(row.get("country")),
        website_url=website_url,
        uk_site_url=_clean(row.get("uk_site_url")),
        models_index_url=_clean(row.get("models_index_url")),
        price_list_url=_clean(row.get("price_list_url")),
        brochure_url=_clean(row.get("brochure_url")),
        specs_format=(_clean(row.get("specs_format")) or "unknown").lower(),
        needs_javascript=needs_javascript,
        login_required=_to_bool(row.get("login_required")) or False,
        ncc_member=_to_bool(row.get("ncc_member")),
        contact_name=_clean(row.get("contact_name")),
        contact_email=_clean(row.get("contact_email")),
        contact_phone=_clean(row.get("contact_phone")),
        last_verified=_clean(row.get("last_verified")),
        notes=_clean(row.get("notes")),
    )
    return manufacturer, issues


def load(path: Path | str) -> LoadResult:
    """Load and validate the manufacturer registry CSV."""
    result = LoadResult()
    seen_ids: dict[int, int] = {}
    seen_urls: dict[str, int] = {}

    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):  # header occupies row 1
            manufacturer, issues = _row_to_manufacturer(row, row_number)
            result.issues.extend(issues)
            if manufacturer is None:
                continue

            if manufacturer.manufacturer_id in seen_ids:
                result.issues.append(
                    Issue(
                        severity="error",
                        code="duplicate_manufacturer_id",
                        message=(
                            f"manufacturer_id {manufacturer.manufacturer_id} is also used "
                            f"on row {seen_ids[manufacturer.manufacturer_id]}"
                        ),
                        row_number=row_number,
                        manufacturer_id=manufacturer.manufacturer_id,
                    )
                )
            else:
                seen_ids[manufacturer.manufacturer_id] = row_number

            if manufacturer.website_url in seen_urls:
                result.issues.append(
                    Issue(
                        severity="warning",
                        code="duplicate_website_url",
                        message=(
                            f"website_url is also used by manufacturer_id "
                            f"{seen_urls[manufacturer.website_url]} — likely a copy-paste error"
                        ),
                        row_number=row_number,
                        manufacturer_id=manufacturer.manufacturer_id,
                    )
                )
            else:
                seen_urls[manufacturer.website_url] = manufacturer.manufacturer_id

            result.manufacturers.append(manufacturer)

    return result


def active_motorhome_manufacturers(
    manufacturers: Iterable[Manufacturer],
) -> list[Manufacturer]:
    """Manufacturers in scope for a motorhome run, ordered by pilot priority.

    Rows with no `pilot_priority` sort after every prioritised row, preserving their
    relative (file) order.
    """
    eligible = [m for m in manufacturers if m.is_runnable and m.includes_motorhomes]
    return sorted(
        eligible,
        key=lambda m: (m.pilot_priority is None, m.pilot_priority or 0),
    )
