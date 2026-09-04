"""Validation for canonical Motorhome and Caravan records.

Checks are reported as data (`Issue` objects), never raised as exceptions. A row
with a missing required field or a mismatched payload figure is still useful
information for a reviewer — a reader or validator that aborts on the first
problem would throw that information away. See `model.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from . import caravan_schema, schema
from .caravan import Caravan
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

#: The shortest a real motorhome or campervan can be. The smallest vehicle this project
#: has seen is a 5.4m campervan, so 4m is well clear of anything legitimate while still
#: catching a mis-keyed or mis-parsed figure. Bailey's own Endeavour B65 page published
#: `Overall Body Length: 1.951m` (the truth, given by a comparison table further down
#: that same page, is 5.980m); the adapter read it faithfully, a reviewer accepted it,
#: and nothing downstream objected, so a 1.9m campervan reached FMLV on 20 Aug 2026.
#: Once the baseline and the site agree on a wrong figure the diff reports it as
#: verified-unchanged, which is precisely when a reviewer stops being shown it — hence a
#: floor here, in the shared layer every adapter's upload passes through, rather than in
#: the one adapter whose source happened to be wrong.
MIN_PLAUSIBLE_LENGTH_MM = 4000


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
    issues.extend(_validate_length(motorhome, key))
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


def _validate_length(motorhome: Motorhome, key: str) -> list[Issue]:
    """Catch a length no motorhome or campervan could really have.

    An `error` rather than a `warning`, so `generate_upload` reports `has_errors` and
    the review app's banner points at the issues file instead of announcing a clean
    CSV — the requester's condition (2026-09-04) was that a sub-4m vehicle must never
    be accepted without being highlighted. It does not block the write: per this
    module's docstring problems are reported as data, so a reviewer who has looked at
    the figure and stands by it is not stuck.

    Only a length below the floor is flagged. A missing figure is `missing_required`'s
    business, and no upper bound is imposed — the longest products here are 8.1m
    Autographs, but nothing rules out a longer one arriving legitimately.
    """
    length = motorhome.mh_length_mm
    if length is None or length >= MIN_PLAUSIBLE_LENGTH_MM:
        return []
    return [
        Issue(
            severity="error",
            code="implausible_length",
            message=(
                f"length {length}mm is under the {MIN_PLAUSIBLE_LENGTH_MM}mm floor for a "
                f"motorhome or campervan — check the source page against a sibling "
                f"model before uploading, as a mis-keyed figure looks like this"
            ),
            product_key=key,
            field="mh_length_mm",
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


# --------------------------------------------------------------------------- #
# Touring caravans
# --------------------------------------------------------------------------- #

#: Single-select layout groups worth flagging when unset on an existing caravan.
#: Refrigeration is excluded for the same reason as on the motorhome side — the guide
#: phrases it as "at most one", so unset is valid.
_CARAVAN_LAYOUT_GROUP_FIELDS: tuple[str, ...] = (
    "body_type",
    "sleeping_area",
    "kitchen_location",
    "bathroom_layout",
    "lounge_location",
    "heating",
)

#: The smallest and largest towing-hitch allowance seen across the 92 real caravan
#: products this project holds (Bailey's 81 and Adria's 11). Used only to decide whether
#: an implausible figure is worth a warning — not to reject anything.
_PLAUSIBLE_HITCH_MM = (500, 2000)


def validate_caravan(caravan: Caravan) -> list[Issue]:
    """Validate a single touring caravan. Never raises."""
    issues: list[Issue] = []
    key = caravan.key

    for field_name in caravan_schema.REQUIRED:
        value = getattr(caravan, field_name, None)
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

    issues.extend(_validate_caravan_payload(caravan, key))
    issues.extend(_validate_caravan_lengths(caravan, key))

    for field_name in _CARAVAN_LAYOUT_GROUP_FIELDS:
        if getattr(caravan, field_name) is None:
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


def _validate_caravan_payload(caravan: Caravan, key: str) -> list[Issue]:
    """Check the two payload columns sum to ``mtplm - mro``.

    A **warning**, not an error, and deliberately so: six of Bailey's 81 products fail it
    in FMLV's own current data — two out by 1kg, and two by 21kg and 49kg. Those are real
    discrepancies in the published figures, not extraction faults, so a check that
    rejected the product would throw away a correct scrape over someone else's typo.
    """
    derived = caravan.derived_payload_kilograms
    published = caravan.published_payload_kilograms
    if derived is None or published is None or derived == published:
        return []
    return [
        Issue(
            severity="warning",
            code="payload_mismatch",
            message=(
                f"published payload {published}kg does not match mtplm - mro ({derived}kg)"
            ),
            product_key=key,
            field="personal_effects_payload_kilograms",
        )
    ]


def _validate_caravan_lengths(caravan: Caravan, key: str) -> list[Issue]:
    """Catch the two length columns being mapped the wrong way round.

    `shipping_length_mm` is the body plus the towing hitch, so it must exceed
    `exterior_body_length_mm` — on all 76 Bailey products carrying both, by 845-1500mm.
    Swapping them is the most plausible single mistake a caravan adapter can make: both
    are lengths, both sit in the same spec table, and on any one product either ordering
    looks reasonable. Getting it wrong would be wrong on every product at once and hard
    to see in a review, so it is worth an explicit check rather than a reviewer's eye.
    """
    hitch = caravan.hitch_length_mm
    if hitch is None:
        return []
    if hitch <= 0:
        return [
            Issue(
                severity="error",
                code="shipping_length_not_longer",
                message=(
                    f"shipping length {caravan.shipping_length_mm}mm is not longer than "
                    f"exterior body length {caravan.exterior_body_length_mm}mm — it "
                    f"includes the towing hitch, so the two look swapped"
                ),
                product_key=key,
                field="shipping_length_mm",
            )
        ]
    low, high = _PLAUSIBLE_HITCH_MM
    if not (low <= hitch <= high):
        return [
            Issue(
                severity="warning",
                code="implausible_hitch_length",
                message=(
                    f"shipping length exceeds exterior body length by {hitch}mm, outside "
                    f"the {low}-{high}mm seen across every known caravan"
                ),
                product_key=key,
                field="shipping_length_mm",
            )
        ]
    return []


def validate_all_caravans(caravans: Iterable[Caravan]) -> list[Issue]:
    """Validate every caravan in a collection, in order."""
    issues: list[Issue] = []
    for caravan in caravans:
        issues.extend(validate_caravan(caravan))
    return issues
