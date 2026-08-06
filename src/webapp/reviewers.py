"""Loading `data/reviewers.csv` — who is allowed to decide on a proposed change.

Deliberately tiny compared to `registry/loader.py`: two columns, no cross-row checks.
A missing file is not an error — it just means the app can't populate the reviewer
dropdown or gate decisions by name, which is the behaviour before this file existed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Reviewer:
    name: str
    email: str | None


def load_reviewers(path: Path) -> list[Reviewer]:
    """Load the reviewer list, or return `[]` if `path` doesn't exist."""
    if not path.exists():
        return []

    reviewers: list[Reviewer] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("reviewer_name") or "").strip()
            if not name:
                continue
            email = (row.get("reviewer_email") or "").strip() or None
            reviewers.append(Reviewer(name=name, email=email))
    return reviewers
