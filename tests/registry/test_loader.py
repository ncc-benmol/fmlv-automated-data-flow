"""Tests for the manufacturer registry loader."""

from __future__ import annotations

import csv
from pathlib import Path

from src import registry

_COLUMNS = (
    "manufacturer_id",
    "fmlv_manufacturer",
    "fmlv_display_name",
    "categories",
    "status",
    "pilot_priority",
    "country",
    "website_url",
    "uk_site_url",
    "models_index_url",
    "price_list_url",
    "brochure_url",
    "ncc_supplier_name",
    "specs_format",
    "needs_javascript",
    "login_required",
    "ncc_member",
    "contact_name",
    "contact_email",
    "contact_phone",
    "last_verified",
    "notes",
)

REAL_REGISTRY = Path(__file__).parents[2] / "config" / "manufacturers.csv"


def write_registry(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "manufacturers.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in _COLUMNS})
    return path


def minimal_row(**overrides: str) -> dict[str, str]:
    row = {
        "manufacturer_id": "1",
        "fmlv_manufacturer": "Adria Mobil",
        "website_url": "https://www.adria-mobil.com/",
        "status": "active",
    }
    row.update(overrides)
    return row


def test_loads_a_minimal_valid_row(tmp_path: Path) -> None:
    path = write_registry(tmp_path, [minimal_row()])
    result = registry.load(path)

    assert len(result.manufacturers) == 1
    manufacturer = result.manufacturers[0]
    assert manufacturer.manufacturer_id == 1
    assert manufacturer.fmlv_manufacturer == "Adria Mobil"
    assert manufacturer.status is registry.Status.ACTIVE


def test_blank_placeholder_row_is_skipped_without_issues(tmp_path: Path) -> None:
    # The registry template ships with spare rows that have only `status=active`
    # pre-filled — these must be silently skipped, not reported as broken rows.
    path = write_registry(tmp_path, [{"status": "active"}])
    result = registry.load(path)

    assert result.manufacturers == []
    assert result.issues == []


def test_missing_required_fields_are_errors(tmp_path: Path) -> None:
    path = write_registry(tmp_path, [{"manufacturer_id": "1", "status": "active"}])
    result = registry.load(path)

    assert result.manufacturers == []
    codes = {issue.code for issue in result.issues}
    assert "missing_fmlv_manufacturer" in codes
    assert "missing_website_url" in codes
    assert all(issue.severity == "error" for issue in result.issues)


def test_duplicate_manufacturer_id_is_flagged(tmp_path: Path) -> None:
    path = write_registry(
        tmp_path,
        [
            minimal_row(manufacturer_id="1", website_url="https://a.example/"),
            minimal_row(manufacturer_id="1", website_url="https://b.example/"),
        ],
    )
    result = registry.load(path)

    assert len(result.manufacturers) == 2  # both still loaded — the issue is a flag, not a drop
    duplicate_issues = [i for i in result.issues if i.code == "duplicate_manufacturer_id"]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0].severity == "error"


def test_duplicate_website_url_is_flagged(tmp_path: Path) -> None:
    # This is the exact class of mistake found in the real registry: two different
    # manufacturers accidentally pointing at the same site.
    path = write_registry(
        tmp_path,
        [
            minimal_row(manufacturer_id="1", fmlv_manufacturer="Sunlight"),
            minimal_row(manufacturer_id="2", fmlv_manufacturer="Morelo"),
        ],
    )
    result = registry.load(path)

    duplicate_issues = [i for i in result.issues if i.code == "duplicate_website_url"]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0].severity == "warning"
    assert duplicate_issues[0].manufacturer_id == 2


def test_blank_categories_defaults_to_included_with_a_warning(tmp_path: Path) -> None:
    path = write_registry(tmp_path, [minimal_row(categories="")])
    result = registry.load(path)

    assert result.manufacturers[0].includes_motorhomes is True
    assert any(i.code == "categories_unset" for i in result.issues)


def test_caravan_only_manufacturer_is_excluded_from_motorhome_scope(tmp_path: Path) -> None:
    path = write_registry(tmp_path, [minimal_row(categories="caravan")])
    result = registry.load(path)

    assert result.manufacturers[0].includes_motorhomes is False
    assert registry.active_motorhome_manufacturers(result.manufacturers) == []


def test_paused_manufacturer_is_excluded_from_runnable(tmp_path: Path) -> None:
    path = write_registry(tmp_path, [minimal_row(status="paused")])
    result = registry.load(path)

    assert result.manufacturers[0].is_runnable is False
    assert registry.active_motorhome_manufacturers(result.manufacturers) == []


def test_active_motorhome_manufacturers_orders_by_pilot_priority(tmp_path: Path) -> None:
    path = write_registry(
        tmp_path,
        [
            minimal_row(manufacturer_id="1", fmlv_manufacturer="No priority", pilot_priority=""),
            minimal_row(manufacturer_id="2", fmlv_manufacturer="Second", pilot_priority="2"),
            minimal_row(manufacturer_id="3", fmlv_manufacturer="First", pilot_priority="1"),
        ],
    )
    result = registry.load(path)

    ordered = registry.active_motorhome_manufacturers(result.manufacturers)
    assert [m.fmlv_manufacturer for m in ordered] == ["First", "Second", "No priority"]


def test_real_registry_file_loads_without_hard_errors() -> None:
    result = registry.load(REAL_REGISTRY)

    errors = [i for i in result.issues if i.severity == "error"]
    assert errors == []
    assert len(result.manufacturers) >= 1
