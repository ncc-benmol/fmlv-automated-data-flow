"""Matching scraped products to the baseline export and diffing them field by field."""

from .classify import ChangeKind, ProductDiff, diff_products
from .compare import FieldChange, Priority, compare_fields, field_value, sort_changes
from .matching import DEFAULT_THRESHOLD, MatchResult, match_products, token_similarity
from .year_rollover import ROLLOVER_WINDOW, bump_year, in_rollover_window

__all__ = [
    "DEFAULT_THRESHOLD",
    "ROLLOVER_WINDOW",
    "ChangeKind",
    "FieldChange",
    "MatchResult",
    "Priority",
    "ProductDiff",
    "bump_year",
    "compare_fields",
    "diff_products",
    "field_value",
    "in_rollover_window",
    "match_products",
    "sort_changes",
    "token_similarity",
]
