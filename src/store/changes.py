"""Turning a run's diff (Phase 5's `diff.diff_products`) into durable rows.

`diff_products` is a pure, in-memory function — this module is where its output
becomes something a reviewer can act on: `proposed_change` rows for anything that
changed or is new, `verification` rows for anything checked and confirmed unchanged
(DESIGN.md §6.5). `ChangeKind.DISAPPEARED` is deliberately not persisted here — there's
no actionable proposal for it yet (proposing `archived = Yes` is still [F], see
TODO.md Phase 5).

DESIGN.md §6.8 ("rejections are remembered") is enforced in `was_previously_rejected`:
a proposed change is skipped if the exact same (product, field, new_value) was
rejected last time. A manufacturer later publishing a *different* corrected figure for
that field is a new proposal and is still shown — only the literal rejected value is
suppressed.

A `year_rollover_eligible` product (DESIGN.md §6.9) gets one more proposal beyond
what `diff.compare` found: a `field="year"` change from the baseline's year to
`year_rollover.bump_year`'s result. This is deliberately routed through the exact
same `proposed_change`/`decision` machinery as every other field — accepting it *is*
the "checkbox" TODO.md's Phase 5 entry described, rather than a separate mechanism.
Its `source_url` is `None` and its snippet says so: the suggestion comes from the
pipeline noticing the season, not from anything read off the manufacturer's site.

`bump_year_all` is §6.9's *other* route, the one the CLI's `--bump-year` passes:
the same proposal, for every product of the manufacturer rather than only the
seasonally plausible ones. Both routes converge here deliberately — a globally
requested rollover is still reviewed and accepted per product, and the pipeline
still never writes `year` on its own. Neither route proposes a bump unless the
baseline's `year` is exactly today's year — `year_rollover.can_bump_year` gates it,
so a product already sitting at `current_year + 1` (bumped and accepted earlier) or
still showing some older, stale year is never offered one.

`ChangeKind.DISAPPEARED` **is** persisted here, as a proposed `field="archived"`
change (old `False` -> new `True`) rather than being dropped: a product missing from
a manufacturer's latest sweep is exactly the "should this be archived?" question a
reviewer needs put in front of them, not silence. It goes through the same
accept/reject/correct machinery, `source_url=None`, as the pipeline's own inference
rather than something read off the site.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from ..diff.classify import ChangeKind, ProductDiff
from ..diff.compare import field_value
from ..diff.year_rollover import bump_year, can_bump_year
from . import products as products_store
from .decisions import Decision
from .products import Product

#: `source_snippet` for the year-rollover suggestion — explains its provenance is the
#: pipeline's own seasonal heuristic, not a fact read off the manufacturer's site.
YEAR_ROLLOVER_SNIPPET = (
    "Suggested by the pipeline: a change was detected during the June-September "
    "model-year rollover window (DESIGN.md §6.9), not read from the "
    "manufacturer's site."
)

#: `source_snippet` for a propose-to-archive suggestion — a `DISAPPEARED` product.
ARCHIVE_SNIPPET = (
    "Not found on the manufacturer's site during this run's latest sweep — "
    "proposing to archive this product."
)

#: `source_snippet` for a `diff.MissingField` proposal — an in-scope field
#: (`schema.IN_SCOPE`) the adapter couldn't find this run. Reviewer templates match
#: on this exact text (`webapp.app`'s `is_missing_field` global) the same way
#: `ARCHIVE_SNIPPET`/`YEAR_ROLLOVER_SNIPPET` are matched on, since `proposed_change`
#: has no column of its own for "why was this proposed".
MISSING_FIELD_SNIPPET = (
    "This field is marked in-scope for automated collection, but was not found on "
    "the manufacturer's site this run. Confirm the existing figure is still "
    "correct, or enter a replacement."
)

#: How `_serialize` joins a multi-valued field (e.g. `bed_types`) into one TEXT column.
#: `output.build.apply_field` is `_serialize`'s inverse and splits on this same
#: constant — keep them in sync.
LIST_SEPARATOR = ", "


@dataclass(frozen=True)
class ProposedChange:
    """One field-level proposal, persisted from a `diff.FieldChange` or a new field."""

    id: int
    run_id: int
    product_id: int
    field: str
    old_value: str | None
    new_value: str | None
    source_url: str | None
    source_snippet: str | None
    confidence: float | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ProposedChange:
        return cls(
            id=row["id"],
            run_id=row["run_id"],
            product_id=row["product_id"],
            field=row["field"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            source_url=row["source_url"],
            source_snippet=row["source_snippet"],
            confidence=row["confidence"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class ChangeQueueEntry:
    """One row for the review UI: a proposed change, its product, and its decision."""

    change: ProposedChange
    product: Product
    decision: Decision | None


@dataclass(frozen=True)
class RunReviewSummary:
    """Review status of one run's change queue, for the runs overview page."""

    pending_count: int
    primary_reviewer: str | None


@dataclass(frozen=True)
class PersistResult:
    """A summary of what persisting one run's diff did — for a run-completion message."""

    proposed: int = 0
    verified: int = 0
    suppressed_rejections: int = 0
    year_rollover_proposed: int = 0
    archive_proposed: int = 0
    missing_field_proposed: int = 0


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _serialize(value: Any) -> str | None:
    """Stringify a diff value for storage — every `proposed_change` column is TEXT."""
    if value is None:
        return None
    if isinstance(value, list):
        return LIST_SEPARATOR.join(item for item in (_serialize(entry) for entry in value) if item)
    if hasattr(value, "value"):  # enum member, e.g. BodyType.A_CLASS
        return str(value.value)
    return str(value)


def get_proposed_change(connection: sqlite3.Connection, change_id: int) -> ProposedChange:
    """Fetch a proposed change by id. Raises `KeyError` if it doesn't exist."""
    row = connection.execute(
        "SELECT * FROM proposed_change WHERE id = ?", (change_id,)
    ).fetchone()
    if row is None:
        msg = f"no proposed_change with id {change_id}"
        raise KeyError(msg)
    return ProposedChange.from_row(row)


def was_previously_rejected(
    connection: sqlite3.Connection, *, product_id: int, field: str, new_value: str | None
) -> bool:
    """Whether the exact (product, field, new_value) triple was rejected last time.

    Only the most recent decision for a matching proposal counts — an earlier
    rejection later overridden (accept/correct) must not keep suppressing it.
    """
    row = connection.execute(
        """
        SELECT decision.action
        FROM proposed_change
        JOIN decision ON decision.proposed_change_id = proposed_change.id
        WHERE proposed_change.product_id = ?
          AND proposed_change.field = ?
          AND proposed_change.new_value IS ?
        ORDER BY decision.decided_at DESC, decision.id DESC
        LIMIT 1
        """,
        (product_id, field, new_value),
    ).fetchone()
    return row is not None and row["action"] == "reject"


def record_proposed_change(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    product_id: int,
    field: str,
    old_value: str | None,
    new_value: str | None,
    source_url: str | None = None,
    source_snippet: str | None = None,
    confidence: float | None = None,
) -> ProposedChange:
    cursor = connection.execute(
        """
        INSERT INTO proposed_change
            (run_id, product_id, field, old_value, new_value, source_url, source_snippet,
             confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, product_id, field, old_value, new_value, source_url, source_snippet,
         confidence, _now()),
    )
    connection.commit()
    assert cursor.lastrowid is not None
    return get_proposed_change(connection, cursor.lastrowid)


def record_verification(
    connection: sqlite3.Connection, *, run_id: int, product_id: int, field: str
) -> None:
    connection.execute(
        "INSERT INTO verification (run_id, product_id, field, verified_at) VALUES (?, ?, ?, ?)",
        (run_id, product_id, field, _now()),
    )
    connection.commit()


def run_review_summary(connection: sqlite3.Connection, run_id: int) -> RunReviewSummary:
    """How much of a run's change queue is left to review, and who's reviewed most of it.

    `primary_reviewer` is whichever named reviewer has the most decisions recorded on
    this run (ties broken alphabetically) — a simple "who's mainly been through this"
    signal for the runs overview page, not a permissions concept. `None` if nothing on
    the run has been decided yet.
    """
    pending_row = connection.execute(
        """
        SELECT COUNT(*) AS pending
        FROM proposed_change
        LEFT JOIN decision ON decision.id = (
            SELECT id FROM decision AS latest
            WHERE latest.proposed_change_id = proposed_change.id
            ORDER BY latest.decided_at DESC, latest.id DESC
            LIMIT 1
        )
        WHERE proposed_change.run_id = ? AND decision.id IS NULL
        """,
        (run_id,),
    ).fetchone()

    reviewer_row = connection.execute(
        """
        SELECT decision.decided_by AS reviewer, COUNT(*) AS n
        FROM proposed_change
        JOIN decision ON decision.id = (
            SELECT id FROM decision AS latest
            WHERE latest.proposed_change_id = proposed_change.id
            ORDER BY latest.decided_at DESC, latest.id DESC
            LIMIT 1
        )
        WHERE proposed_change.run_id = ? AND decision.decided_by IS NOT NULL
        GROUP BY decision.decided_by
        ORDER BY n DESC, reviewer ASC
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()

    return RunReviewSummary(
        pending_count=pending_row["pending"],
        primary_reviewer=reviewer_row["reviewer"] if reviewer_row is not None else None,
    )


def persist_diff(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    manufacturer_id: int,
    diffs: list[ProductDiff],
    bump_year_all: bool = False,
    today: date | None = None,
) -> PersistResult:
    """Persist one run's worth of `diff_products` output.

    Upserts the product identity mapping (`store.products.upsert_seen`) for every
    matched, new or disappeared product, then records `proposed_change`/`verification`
    rows. `DISAPPEARED` products get a propose-to-archive change — see the module
    docstring — rather than being skipped.

    `bump_year_all` proposes a `year` bump for every existing product, not just the
    seasonally eligible ones — DESIGN.md §6.9 route 1, requested explicitly by a human
    when triggering the run. A genuinely new product is never given one: it has no
    baseline year to bump. Either route is capped by `year_rollover.can_bump_year`
    (`today`, injectable for tests, defaults to the real today).
    """
    proposed = 0
    verified = 0
    suppressed = 0
    year_rollover_proposed = 0
    archive_proposed = 0
    missing_field_proposed = 0

    for diff in diffs:
        if diff.kind == ChangeKind.DISAPPEARED:
            assert diff.baseline is not None
            product = products_store.upsert_seen(
                connection,
                manufacturer_id=manufacturer_id,
                fmlv_product_id=diff.fmlv_product_id,
                manufacturer_range=diff.baseline.manufacturer_range,
                model=diff.baseline.model,
                run_id=run_id,
            )
            new_value = _serialize(True)
            if was_previously_rejected(
                connection, product_id=product.id, field="archived", new_value=new_value
            ):
                suppressed += 1
            else:
                record_proposed_change(
                    connection,
                    run_id=run_id,
                    product_id=product.id,
                    field="archived",
                    old_value=_serialize(diff.baseline.archived),
                    new_value=new_value,
                    source_url=None,
                    source_snippet=ARCHIVE_SNIPPET,
                )
                proposed += 1
                archive_proposed += 1
            continue

        assert diff.extracted is not None
        product = products_store.upsert_seen(
            connection,
            manufacturer_id=manufacturer_id,
            fmlv_product_id=diff.fmlv_product_id,
            manufacturer_range=diff.extracted.motorhome.manufacturer_range,
            model=diff.extracted.motorhome.model,
            run_id=run_id,
        )

        if diff.kind == ChangeKind.NEW_PRODUCT:
            for field_name, provenance in diff.extracted.provenance.items():
                record_proposed_change(
                    connection,
                    run_id=run_id,
                    product_id=product.id,
                    field=field_name,
                    old_value=None,
                    new_value=_serialize(field_value(diff.extracted.motorhome, field_name)),
                    source_url=provenance.source_url,
                    source_snippet=provenance.snippet,
                )
                proposed += 1
            continue

        for change in diff.changes:
            new_value = _serialize(change.new_value)
            if was_previously_rejected(
                connection, product_id=product.id, field=change.field, new_value=new_value
            ):
                suppressed += 1
                continue
            record_proposed_change(
                connection,
                run_id=run_id,
                product_id=product.id,
                field=change.field,
                old_value=_serialize(change.old_value),
                new_value=new_value,
                source_url=change.provenance.source_url if change.provenance else None,
                source_snippet=change.provenance.snippet if change.provenance else None,
                confidence=diff.match_score,
            )
            proposed += 1

        if (
            (bump_year_all or diff.year_rollover_eligible)
            and diff.baseline is not None
            and diff.baseline.year is not None
            and not any(change.field == "year" for change in diff.changes)
            and can_bump_year(diff.baseline.year, today=today)
        ):
            new_value = _serialize(bump_year(diff.baseline).year)
            if was_previously_rejected(
                connection, product_id=product.id, field="year", new_value=new_value
            ):
                suppressed += 1
            else:
                record_proposed_change(
                    connection,
                    run_id=run_id,
                    product_id=product.id,
                    field="year",
                    old_value=_serialize(diff.baseline.year),
                    new_value=new_value,
                    source_url=None,
                    source_snippet=YEAR_ROLLOVER_SNIPPET,
                )
                proposed += 1
                year_rollover_proposed += 1

        for field_name in diff.confirmed_fields:
            record_verification(connection, run_id=run_id, product_id=product.id, field=field_name)
            verified += 1

        for missing in diff.missing_fields:
            # No `was_previously_rejected` gate here, unlike an ordinary proposal:
            # "reject" isn't a coherent action for a field that's simply missing —
            # the review UI only offers "keep existing" (accept) or "replace"
            # (correct) for these — so a still-missing field keeps being asked
            # about every run until a reviewer resolves it one way or the other.
            old_serialized = _serialize(missing.old_value)
            record_proposed_change(
                connection,
                run_id=run_id,
                product_id=product.id,
                field=missing.field,
                old_value=old_serialized,
                new_value=old_serialized,
                source_url=None,
                source_snippet=MISSING_FIELD_SNIPPET,
            )
            proposed += 1
            missing_field_proposed += 1

    return PersistResult(
        proposed=proposed,
        verified=verified,
        suppressed_rejections=suppressed,
        year_rollover_proposed=year_rollover_proposed,
        archive_proposed=archive_proposed,
        missing_field_proposed=missing_field_proposed,
    )


def list_change_queue(connection: sqlite3.Connection, run_id: int) -> list[ChangeQueueEntry]:
    """Every proposed change for a run, with its product and latest decision (if any).

    Ordered by product identity then field, so a reviewer sees every proposal for one
    product together — matches DESIGN.md §6.3's "beside each change" framing.
    """
    rows = connection.execute(
        """
        SELECT
            proposed_change.*,
            product.manufacturer_id AS product_manufacturer_id,
            product.fmlv_product_id AS product_fmlv_product_id,
            product.manufacturer_range AS product_manufacturer_range,
            product.model AS product_model,
            product.first_seen_run_id AS product_first_seen_run_id,
            product.last_seen_run_id AS product_last_seen_run_id,
            decision.id AS decision_id,
            decision.action AS decision_action,
            decision.corrected_value AS decision_corrected_value,
            decision.decided_by AS decision_decided_by,
            decision.decided_at AS decision_decided_at
        FROM proposed_change
        JOIN product ON product.id = proposed_change.product_id
        LEFT JOIN decision ON decision.id = (
            SELECT id FROM decision AS latest
            WHERE latest.proposed_change_id = proposed_change.id
            ORDER BY latest.decided_at DESC, latest.id DESC
            LIMIT 1
        )
        WHERE proposed_change.run_id = ?
        ORDER BY product.manufacturer_range, product.model, proposed_change.field
        """,
        (run_id,),
    ).fetchall()

    entries: list[ChangeQueueEntry] = []
    for row in rows:
        change = ProposedChange.from_row(row)
        product = Product(
            id=row["product_id"],
            manufacturer_id=row["product_manufacturer_id"],
            fmlv_product_id=row["product_fmlv_product_id"],
            manufacturer_range=row["product_manufacturer_range"],
            model=row["product_model"],
            first_seen_run_id=row["product_first_seen_run_id"],
            last_seen_run_id=row["product_last_seen_run_id"],
        )
        decision = None
        if row["decision_id"] is not None:
            decision = Decision(
                id=row["decision_id"],
                proposed_change_id=change.id,
                action=row["decision_action"],
                corrected_value=row["decision_corrected_value"],
                decided_by=row["decision_decided_by"],
                decided_at=row["decision_decided_at"],
            )
        entries.append(ChangeQueueEntry(change=change, product=product, decision=decision))
    return entries
