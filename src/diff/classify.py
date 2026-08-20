"""Classifying every scraped and baseline product into one of four outcomes.

DESIGN.md §6.5 treats "verified unchanged" as a first-class result, not silence, and
TODO.md's Phase 5 asks for exactly four classifications: new product, changed field,
unchanged-confirmed, disappeared. This module ties `matching.py` and `compare.py`
together to produce one `ProductDiff` per scraped product plus one per baseline
product that went unmatched — nothing is ever silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from ..adapters.base import ExtractedMotorhome
from ..product_model.model import Motorhome
from .compare import FieldChange, MissingField, compare_fields, sort_changes
from .matching import DEFAULT_THRESHOLD, match_products
from .year_rollover import in_rollover_window


class ChangeKind(str, Enum):
    """Which of the four Phase 5 outcomes a product diff represents."""

    NEW_PRODUCT = "new_product"
    CHANGED_FIELD = "changed_field"
    UNCHANGED_CONFIRMED = "unchanged_confirmed"
    DISAPPEARED = "disappeared"


@dataclass(frozen=True)
class ProductDiff:
    """One product's outcome for this run.

    `fmlv_product_id` is `None` for a `NEW_PRODUCT` — DESIGN.md §4.1: a genuinely new
    product is submitted with `product_id` blank and the NCC website mints one.
    """

    kind: ChangeKind
    key: str
    fmlv_product_id: int | None
    baseline: Motorhome | None
    extracted: ExtractedMotorhome | None
    changes: list[FieldChange] = field(default_factory=list)
    confirmed_fields: list[str] = field(default_factory=list)
    missing_fields: list[MissingField] = field(default_factory=list)
    match_score: float | None = None
    match_method: str | None = None
    #: A plausible (not certain) sign this changed product is a model-year rollover —
    #: DESIGN.md §9 open question 1. True only for a `CHANGED_FIELD` product seen
    #: during `year_rollover.ROLLOVER_WINDOW`; the review app (Phase 6) surfaces this
    #: as a checkbox, it never bumps `year` on its own.
    year_rollover_eligible: bool = False


def diff_products(
    scraped: list[ExtractedMotorhome],
    baseline: list[Motorhome],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    today: date | None = None,
) -> list[ProductDiff]:
    """Match, diff and classify every scraped product plus every baseline product.

    `baseline` should already be scoped to one manufacturer, the same as `scraped`
    naturally is (one adapter run = one manufacturer) — see `matching.match_products`.
    `today` is injectable for tests; defaults to the real today (see `year_rollover`).
    """
    match_results = match_products(scraped, baseline, threshold=threshold)

    diffs: list[ProductDiff] = []
    matched_baseline_indices: set[int] = set()

    for result in match_results:
        if result.baseline is None:
            diffs.append(
                ProductDiff(
                    kind=ChangeKind.NEW_PRODUCT,
                    key=result.extracted.motorhome.key,
                    fmlv_product_id=None,
                    baseline=None,
                    extracted=result.extracted,
                )
            )
            continue

        assert result.baseline_index is not None
        matched_baseline_indices.add(result.baseline_index)
        changes, confirmed, missing = compare_fields(result.baseline, result.extracted)
        kind = ChangeKind.CHANGED_FIELD if changes else ChangeKind.UNCHANGED_CONFIRMED
        diffs.append(
            ProductDiff(
                kind=kind,
                key=result.baseline.key,
                fmlv_product_id=result.baseline.product_id,
                baseline=result.baseline,
                extracted=result.extracted,
                changes=sort_changes(changes),
                confirmed_fields=confirmed,
                missing_fields=missing,
                match_score=result.score,
                match_method=result.method,
                year_rollover_eligible=(
                    kind == ChangeKind.CHANGED_FIELD and in_rollover_window(today)
                ),
            )
        )

    for index, baseline_motorhome in enumerate(baseline):
        if index in matched_baseline_indices:
            continue
        diffs.append(
            ProductDiff(
                kind=ChangeKind.DISAPPEARED,
                key=baseline_motorhome.key,
                fmlv_product_id=baseline_motorhome.product_id,
                baseline=baseline_motorhome,
                extracted=None,
            )
        )

    return diffs
