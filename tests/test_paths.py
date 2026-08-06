"""Tests for the standard on-disk data layout."""

from __future__ import annotations

from pathlib import Path

from src import paths


def test_snapshot_dir_is_scoped_by_manufacturer_and_run() -> None:
    root = Path("data")
    assert paths.snapshot_dir(3, 42, root=root) == root / "snapshots" / "3" / "42"


def test_snapshot_dir_differs_per_run() -> None:
    root = Path("data")
    first = paths.snapshot_dir(3, 1, root=root)
    second = paths.snapshot_dir(3, 2, root=root)
    assert first != second


def test_helpers_respect_a_custom_root(tmp_path: Path) -> None:
    assert paths.exports_dir(root=tmp_path) == tmp_path / "exports"
    assert paths.uploads_dir(root=tmp_path) == tmp_path / "uploads"
    assert paths.db_path(root=tmp_path) == tmp_path / "run_store.sqlite3"
