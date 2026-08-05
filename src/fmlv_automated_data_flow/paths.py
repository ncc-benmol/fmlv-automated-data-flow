"""Standard on-disk layout for run data.

Everything the pipeline reads or writes at runtime lives under one `data/` directory
(see DESIGN.md §5 and §8): the manufacturer registry, downloaded FMLV exports, fetch
snapshots, the SQLite run store, and generated upload CSVs. This module is the single
place that knows that layout, so nothing else hard-codes a path string.
"""

from __future__ import annotations

from pathlib import Path

#: Root of all runtime data. Pass a different `root` to any function here (e.g. a
#: tmp_path in tests, or a different mount point in the container) rather than
#: mutating this constant.
DATA_DIR = Path("data")


def registry_path(*, root: Path = DATA_DIR) -> Path:
    """The manufacturer registry CSV — who to visit, where, and in what shape."""
    return root / "manufacturers.csv"


def snapshot_dir(manufacturer_id: int, run_id: int, *, root: Path = DATA_DIR) -> Path:
    """Where fetched pages/files for one manufacturer's run are snapshotted."""
    return root / "snapshots" / str(manufacturer_id) / str(run_id)


def exports_dir(*, root: Path = DATA_DIR) -> Path:
    """Where downloaded FMLV exports (the baseline for each run) are kept."""
    return root / "exports"


def uploads_dir(*, root: Path = DATA_DIR) -> Path:
    """Where generated upload CSVs are written, ready for manual upload."""
    return root / "uploads"


def upload_csv_path(run_id: int, *, root: Path = DATA_DIR) -> Path:
    """Where one run's generated upload CSV is written (DESIGN.md §5: `data/uploads/<run>/…csv`)."""
    return uploads_dir(root=root) / str(run_id) / "motorhome-campervans.csv"


def db_path(*, root: Path = DATA_DIR) -> Path:
    """The SQLite run store file."""
    return root / "run_store.sqlite3"
