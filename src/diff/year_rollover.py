"""Model-year rollover — DESIGN.md §9 open question 1, resolved.

`year` is a carry-through field (`fmlv/schema.py`: "PLEASE Leave as is!") and this
pipeline never bumps it automatically. Advancing it is always a human decision, made
one of two ways:

1. **Globally**, for every product of a manufacturer, as a parameter supplied when a
   run is triggered (Phase 8's CLI — not built yet). `bump_year` is the primitive that
   flag will call, one product at a time.
2. **Per product, at review time** (Phase 6's UI — not built yet), where a change was
   actually detected during the window manufacturers typically publish next year's
   models (June-September). `in_rollover_window` is a plausibility signal for that
   window, surfaced on `ProductDiff.year_rollover_eligible` (`classify.py`) for the
   review app to render as a checkbox — it never forces a bump by itself.

Deliberately not the same window as DESIGN.md §8's "August-September is peak season"
note — that one is about how *often to run the pipeline*; this one is about how
*plausible a detected change is a model-year rollover*, which the user set slightly
wider (June-September) as encoded in `ROLLOVER_WINDOW`.
"""

from __future__ import annotations

from datetime import date

from ..product_model.model import Motorhome

#: (month, day) start/end, inclusive, of the window in which a detected change is
#: plausibly a model-year rollover rather than an ordinary in-season correction.
ROLLOVER_WINDOW: tuple[tuple[int, int], tuple[int, int]] = ((6, 1), (9, 30))


def in_rollover_window(today: date | None = None) -> bool:
    """Whether `today` (default: the real today) falls inside `ROLLOVER_WINDOW`."""
    today = today or date.today()
    (start_month, start_day), (end_month, end_day) = ROLLOVER_WINDOW
    start = date(today.year, start_month, start_day)
    end = date(today.year, end_month, end_day)
    return start <= today <= end


def bump_year(motorhome: Motorhome) -> Motorhome:
    """Return a copy of `motorhome` with `year` advanced by one.

    The only place `year` is ever changed — and only when a human calls this, whether
    from a manufacturer-wide run flag or a per-product review-time checkbox tick (see
    module docstring). A product with no `year` recorded yet has nothing to advance.
    """
    if motorhome.year is None:
        return motorhome
    return motorhome.model_copy(update={"year": motorhome.year + 1})


def can_bump_year(year: int, *, today: date | None = None) -> bool:
    """Whether `year` is eligible for a bump: exactly `today`'s year, no other value.

    Both rollover routes only ever propose turning *this* year's model into next
    year's — a product already sitting at `current_year + 1` (e.g. bumped and
    accepted on an earlier run) must not be offered another bump, and neither should
    one still showing some older year, which is stale data worth a reviewer's
    attention rather than a rollover guess. `today` is injectable for tests.
    """
    current_year = (today or date.today()).year
    return year == current_year
