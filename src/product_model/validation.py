"""Validation for canonical Motorhome records.

Checks are reported as data (`Issue` objects), never raised as exceptions. A row
with a missing required field or a mismatched payload figure is still useful
information for a reviewer — a reader or validator that aborts on the first
problem would throw that information away. See `model.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from . import schema
from .model import Motorhome

Severity = Literal["error", "warning"]

#: Single-select layout groups worth flagging when unset on an existing product.
#: Refrigeration is deliberately excluded — the guide phrases it as "at most one"
#: (fridge/fridge_freezer/neither), not "select one", so an unset value is valid.
_LAYOUT_GROUP_FIELDS: tuple[str, ...] = (
    "body_type",
    "sleeping_area",
    "kitchen_location",
    "bathroom_layout",
    "lounge_location",
    "heating",
)


@dataclass(frozen=True)
class Issue:
    """One validation or parse problem, attached to a product and/or field."""

    severity: Severity
    code: str
    message: str
    product_key: str = ""
    field: str = ""


def validate(motorhome: Motorhome) -> list[Issue]:
    """Validate a single motorhome. Never raises."""
    issues: list[Issue] = []
    key = motorhome.key

    for field_name in schema.REQUIRED:
        value = getattr(motorhome, field_name, None)
        if value is None or value == "":
            issues.append(
                Issue(
                    severity="error",
                    code="missing_required",
                    message=f"required field '{field_name}' is missing",
                    product_key=key,
                    field=field_name,
                )
            )

    issues.extend(_validate_payload(motorhome, key))
    issues.extend(_validate_automatic(motorhome, key))

    for field_name in _LAYOUT_GROUP_FIELDS:
        if getattr(motorhome, field_name) is None:
            issues.append(
                Issue(
                    severity="warning",
                    code="layout_group_unset",
                    message=f"no option selected for '{field_name}'",
                    product_key=key,
                    field=field_name,
                )
            )

    return issues


def _validate_payload(motorhome: Motorhome, key: str) -> list[Issue]:
    """Check ``payload == mtplm - mro`` — see model.derived_payload_kilograms."""
    derived = motorhome.derived_payload_kilograms
    if derived is None or motorhome.mh_payload_kilograms is None:
        return []
    if derived == motorhome.mh_payload_kilograms:
        return []
    return [
        Issue(
            severity="warning",
            code="payload_mismatch",
            message=(
                f"published payload {motorhome.mh_payload_kilograms}kg does not match "
                f"mtplm - mro ({derived}kg)"
            ),
            product_key=key,
            field="mh_payload_kilograms",
        )
    ]


def _validate_automatic(motorhome: Motorhome, key: str) -> list[Issue]:
    """Automatic-variant figures are all-or-nothing; check the group and its payload."""
    automatic = motorhome.automatic
    if automatic is None:
        return []

    issues: list[Issue] = []
    values = (
        automatic.mro_kilograms,
        automatic.payload_kilograms,
        automatic.rrp_pounds,
        automatic.price_min_range_pounds,
    )
    present = [value is not None for value in values]
    if any(present) and not all(present):
        issues.append(
            Issue(
                severity="warning",
                code="automatic_partial",
                message="automatic-gearbox figures are only partially filled in",
                product_key=key,
                field="automatic",
            )
        )

    if (
        automatic.mro_kilograms is not None
        and automatic.payload_kilograms is not None
        and motorhome.mtplm_kilograms is not None
    ):
        expected = motorhome.mtplm_kilograms - automatic.mro_kilograms
        if expected != automatic.payload_kilograms:
            issues.append(
                Issue(
                    severity="warning",
                    code="automatic_payload_mismatch",
                    message=(
                        f"automatic payload {automatic.payload_kilograms}kg does not match "
                        f"mtplm - automatic mro ({expected}kg)"
                    ),
                    product_key=key,
                    field="automatic.payload_kilograms",
                )
            )

    return issues


def validate_all(motorhomes: Iterable[Motorhome]) -> list[Issue]:
    """Validate every motorhome in a collection, in order."""
    issues: list[Issue] = []
    for motorhome in motorhomes:
        issues.extend(validate(motorhome))
    return issues


def format_issues(issues: Iterable[Issue]) -> str:
    """Render issues as human-readable text, one per line, for a reviewer to read.

    Used for the downloadable issues file alongside a generated upload CSV
    (`output.build.write_upload_csv`) — plain text rather than the JSON shape `Issue`
    itself has, since this is meant to be opened and read by a person, not parsed.
    """
    lines = []
    for issue in issues:
        where = " ".join(part for part in (issue.product_key, issue.field) if part)
        prefix = f"[{issue.severity.upper()}]"
        line = f"{prefix} {where}: {issue.message}" if where else f"{prefix} {issue.message}"
        lines.append(line)
    return "\n".join(lines) + "\n" if lines else ""
