"""Tests for the standard on-disk data layout."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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


def test_manufacturer_exports_dir_is_named_id_underscore_name() -> None:
    root = Path("data")
    assert (
        paths.manufacturer_exports_dir(3, "Adria Mobil", root=root)
        == root / "exports" / "3_Adria Mobil"
    )


def test_safe_path_component_collapses_windows_unsafe_characters() -> None:
    assert paths.safe_path_component('Ace: "Motorhomes" / Ltd') == "Ace- -Motorhomes- - Ltd"


def test_upload_csv_path_embeds_the_run_and_a_uk_local_timestamp() -> None:
    root = Path("data")
    generated_at = datetime(2026, 8, 7, 14, 32, tzinfo=ZoneInfo("UTC"))
    assert (
        paths.upload_csv_path(10, generated_at=generated_at, root=root)
        # 14:32 UTC is 15:32 in UK local time during BST.
        == root / "uploads" / "run10_2026-08-07_1532_motorhome-campervans.csv"
    )


def test_upload_csv_path_differs_between_two_generations_of_the_same_run() -> None:
    root = Path("data")
    first = paths.upload_csv_path(10, generated_at=datetime(2026, 8, 7, 9, 0), root=root)
    second = paths.upload_csv_path(10, generated_at=datetime(2026, 8, 7, 9, 1), root=root)
    assert first != second
