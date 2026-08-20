"""The run store: SQLite persistence for runs, snapshots, changes and decisions."""

from .changes import (
    ChangeQueueEntry,
    DisappearanceNotice,
    DisappearanceNoticeEntry,
    MISSING_FIELD_SNIPPET,
    PersistResult,
    ProposedChange,
    RunReviewSummary,
    get_proposed_change,
    list_change_queue,
    list_disappearance_notices,
    persist_diff,
    record_disappearance_notice,
    record_proposed_change,
    record_verification,
    run_review_summary,
    was_previously_rejected,
)
from .db import connect
from .decisions import Decision, get_decision, latest_decision, record_decision
from .products import Product, get_product, list_products, upsert_seen
from .runs import Run, fail_run, finish_run, get_run, list_run_manufacturers, list_runs, start_run

__all__ = [
    "ChangeQueueEntry",
    "Decision",
    "DisappearanceNotice",
    "DisappearanceNoticeEntry",
    "MISSING_FIELD_SNIPPET",
    "PersistResult",
    "Product",
    "ProposedChange",
    "Run",
    "RunReviewSummary",
    "connect",
    "fail_run",
    "finish_run",
    "get_decision",
    "get_product",
    "get_proposed_change",
    "get_run",
    "latest_decision",
    "list_change_queue",
    "list_disappearance_notices",
    "list_products",
    "list_run_manufacturers",
    "list_runs",
    "persist_diff",
    "record_decision",
    "record_disappearance_notice",
    "record_proposed_change",
    "record_verification",
    "run_review_summary",
    "start_run",
    "upsert_seen",
    "was_previously_rejected",
]
