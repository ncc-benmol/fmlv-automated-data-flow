"""Standard on-disk layout for run data and config.

Everything the pipeline reads or writes at runtime lives under one `data/` directory
(see DESIGN.md §5 and §8): downloaded FMLV exports, fetch snapshots, the SQLite run
store, and generated upload CSVs. The manufacturer registry and reviewers list are
hand-maintained inputs rather than runtime output, so they live under a separate
`config/` directory instead. This module is the single place that knows both layouts,
so nothing else hard-codes a path string.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

#: Matches the review app's own display convention (`webapp/app.py`'s `_LOCAL_TZ`) —
#: the upload filename's timestamp should read the same way to a UK-based reviewer.
_LOCAL_TZ = ZoneInfo("Europe/London")

#: Root of all runtime data. Pass a different `root` to any function here (e.g. a
#: tmp_path in tests, or a different mount point in the container) rather than
#: mutating this constant.
DATA_DIR = Path("data")

#: Root of hand-maintained config: the manufacturer registry and reviewers list.
#: Separate from DATA_DIR because these are inputs someone edits, not run output.
CONFIG_DIR = Path("config")

#: Characters not safe in a Windows path component, collapsed to a single "-".
_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*]+')


def safe_path_component(text: str) -> str:
    """A folder/file-name-safe version of free text like a manufacturer name.

    Manufacturer names are free text from the registry (`Manufacturer.fmlv_manufacturer`)
    and could in principle carry characters Windows paths reject — this is the one
    place that guards against that rather than every call site doing it separately.
    """
    return _UNSAFE_PATH_CHARS.sub("-", text.strip()).strip()


def registry_path(*, root: Path = CONFIG_DIR) -> Path:
    """The manufacturer registry CSV — who to visit, where, and in what shape."""
    return root / "manufacturers.csv"


def reviewers_path(*, root: Path = CONFIG_DIR) -> Path:
    """The known-reviewers CSV — who is allowed to decide on a proposed change."""
    return root / "reviewers.csv"


def schedule_path(*, root: Path = CONFIG_DIR) -> Path:
    """The run schedule CSV — which manufacturers/ranges run automatically, and when."""
    return root / "schedule.csv"


def field_guide_path(*, root: Path = CONFIG_DIR) -> Path:
    """The field guide CSV — the source of truth for `product_model.schema.IN_SCOPE`."""
    return root / "field_guide_motorhome.csv"


def snapshot_dir(manufacturer_id: int, run_id: int, *, root: Path = DATA_DIR) -> Path:
    """Where fetched pages/files for one manufacturer's run are snapshotted."""
    return root / "snapshots" / str(manufacturer_id) / str(run_id)


def exports_dir(*, root: Path = DATA_DIR) -> Path:
    """Where downloaded FMLV exports (the baseline for each run) are kept."""
    return root / "exports"


def manufacturer_exports_dir(
    manufacturer_id: int, manufacturer_name: str, *, root: Path = DATA_DIR
) -> Path:
    """Where one manufacturer's downloaded exports are kept.

    The NCC site only offers exports one manufacturer at a time (`fetch/ncc.py`), so
    exports are scoped the same way snapshots are — one subdirectory per manufacturer
    — without ever picking up a different manufacturer's stale file as the baseline
    (`cli.latest_export`). Named `<id>_<name>` rather than the bare id so the folder is
    identifiable by eye; the id is still the leading, stable part of the name in case
    the manufacturer is ever renamed in the registry.
    """
    folder = f"{manufacturer_id}_{safe_path_component(manufacturer_name)}"
    return exports_dir(root=root) / folder


def uploads_dir(*, root: Path = DATA_DIR) -> Path:
    """Where generated upload CSVs are written, ready for manual upload."""
    return root / "uploads"


def upload_csv_path(
    run_id: int, *, generated_at: datetime | None = None, root: Path = DATA_DIR
) -> Path:
    """Where one run's generated upload CSV is written.

    The filename embeds when it was generated, to the nearest minute in UK local
    time: `data/uploads/run<run>_<date>_<time>_motorhome-campervans.csv`. Generating
    twice from the same run therefore never silently overwrites an earlier CSV —
    each generation gets its own file, and the reviewer can see at a glance how
    fresh (or stale) a given upload is.
    """
    when = (generated_at or datetime.now(_LOCAL_TZ)).astimezone(_LOCAL_TZ)
    stamp = when.strftime("%Y-%m-%d_%H%M")
    return uploads_dir(root=root) / f"run{run_id}_{stamp}_motorhome-campervans.csv"


def upload_issues_path(csv_path: Path) -> Path:
    """Where the human-readable validation issues file for one generated upload CSV goes.

    Named to sit next to its CSV in `uploads_dir` (`<csv-stem>-issues.txt`), so it keeps
    the same `run<run>_...` prefix the upload download route already checks for.
    """
    return csv_path.with_name(f"{csv_path.stem}-issues.txt")


def db_path(*, root: Path = DATA_DIR) -> Path:
    """The SQLite run store file."""
    return root / "run_store.sqlite3"
