"""Standalone entry point for running the review app with `uvicorn`.

`create_app` (`app.py`) is a factory that takes a `db_path`, deliberately — so tests
can point it at a throwaway SQLite file rather than a real one. That means `uvicorn`
can't serve `app.py` directly (there's no module-level `app` object, and no
zero-argument factory `--factory` could call). This module is that missing piece: it
builds one `app` object against `paths.db_path()` (or `FMLV_DB_PATH`, for pointing at
a different file) at import time, which is what `uvicorn` needs.
"""

from __future__ import annotations

import os
from pathlib import Path

from .. import paths
from .app import create_app

db_path = Path(os.environ.get("FMLV_DB_PATH", str(paths.db_path())))
app = create_app(db_path)  # reviewers.csv / manufacturers.csv resolved from paths.CONFIG_DIR
