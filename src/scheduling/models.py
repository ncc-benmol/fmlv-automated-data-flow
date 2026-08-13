"""The schedule data model.

One `ScheduleEntry` per row of `config/schedule.csv` — see
`config/schedule.README.md` for the column-by-column field guide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

#: `first_run` is written by hand in the CSV as a UK wall-clock time — this is the
#: zone it's interpreted in, matching the review app's own display convention
#: (`webapp/app.py`'s `_LOCAL_TZ`).
LOCAL_TZ = ZoneInfo("Europe/London")


class FrequencyUnit(str, Enum):
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"


_UNIT_TO_TIMEDELTA_KWARG = {
    FrequencyUnit.HOURS: "hours",
    FrequencyUnit.DAYS: "days",
    FrequencyUnit.WEEKS: "weeks",
}


@dataclass(frozen=True)
class ScheduleEntry:
    """One row of `schedule.csv`: one manufacturer, an optional set of ranges, and
    when it should run."""

    schedule_id: str
    manufacturer_id: int
    ranges: tuple[str, ...]  # empty = whole manufacturer, every range
    first_run: datetime  # timezone-aware, Europe/London
    frequency_value: int
    frequency_unit: FrequencyUnit
    enabled: bool
    notes: str | None = None

    @property
    def frequency(self) -> timedelta:
        return timedelta(**{_UNIT_TO_TIMEDELTA_KWARG[self.frequency_unit]: self.frequency_value})
