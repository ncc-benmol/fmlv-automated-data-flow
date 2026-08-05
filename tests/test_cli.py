"""Tests for the `fmlv run <manufacturer>` command.

`execute_run` is the first code that performs the *whole* sequence — registry, run
record, adapter, diff, persistence — so most of the value here is in the end-to-end
tests, which run the real pipeline against a real SQLite file on disk with only the
adapter and the two fetchers faked. That is deliberately the same shape TODO.md's §T3
describes doing by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fmlv_automated_data_flow import paths, store
from fmlv_automated_data_flow.adapters.base import ExtractedMotorhome, Provenance
from fmlv_automated_data_flow.cli import (
    CommandError,
    execute_run,
    find_manufacturer,
    format_summary,
    latest_export,
    main,
    resolve_ranges,
)
from fmlv_automated_data_flow.fmlv import io
from fmlv_automated_data_flow.fmlv.model import Motorhome
from fmlv_automated_data_flow.registry.models import Manufacturer, Status, TriState

RANGE_URL = "https://www.adria.co.uk/motorhomes/matrix"


def make_manufacturer(**overrides: Any) -> Manufacturer:
    fields: dict[str, Any] = {
        "manufacturer_id": 3,
        "fmlv_manufacturer": "Adria Mobil",
        "fmlv_display_name": "Adria",
        "categories": (),
        "status": Status.ACTIVE,
        "pilot_priority": 1,
        "country": "UK",
        "website_url": "https://www.adria-mobil.com/",
        "uk_site_url": "https://www.adria.co.uk/",
        "models_index_url": None,
        "price_list_url": None,
        "brochure_url": None,
        "specs_format": "mixed",
        "needs_javascript": TriState.YES,
        "login_required": False,
        "ncc_member": True,
        "contact_name": None,
        "contact_email": None,
        "contact_phone": None,
        "last_verified": None,
        "notes": None,
    }
    fields.update(overrides)
    return Manufacturer(**fields)


# --------------------------------------------------------------------------- #
# Fakes: an adapter and the two fetchers, so no network or browser is involved
# --------------------------------------------------------------------------- #


class FakeFetcher:
    """Stands in for `Fetcher`/`BrowserFetcher` — only the context manager is used."""

    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = snapshot_dir
        self.closed = False

    def __enter__(self) -> FakeFetcher:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.closed = True


@dataclass
class FakeAdapter:
    """An adapter that returns canned products and records how it was called."""

    products: list[ExtractedMotorhome]
    calls: list[dict[str, Any]] | None = None
    error: Exception | None = None
    DEFAULT_RANGES: tuple[tuple[str, str], ...] = (  # noqa: N815 — mirrors the real adapter
        ("motorhomes/matrix", "Matrix"),
        ("motorhomes/coral", "Coral"),
    )

    def collect(
        self, http: object, browser: object, snapshot_dir: Path, **kwargs: Any
    ) -> list[ExtractedMotorhome]:
        if self.calls is None:
            self.calls = []
        self.calls.append({"snapshot_dir": snapshot_dir, **kwargs})
        if self.error is not None:
            raise self.error
        return self.products


def make_baseline(**overrides: Any) -> Motorhome:
    fields: dict[str, Any] = {
        "product_id": 4147,
        "year": 2026,
        "manufacturer": "Adria Mobil",
        "manufacturer_display_name": "Adria",
        "manufacturer_range": "Matrix",
        "model": "Supreme 670 DC",
        "rrp_pounds": 93950,
        "mro_kilograms": 3184,
    }
    fields.update(overrides)
    return Motorhome(**fields)


def make_extracted(**overrides: Any) -> ExtractedMotorhome:
    fields: dict[str, Any] = {
        "manufacturer": "Adria Mobil",
        "manufacturer_range": "Matrix",
        "model": "670 DC Supreme Alde RHD",
        "rrp_pounds": 93950,
        "mro_kilograms": 3184,
    }
    fields.update(overrides)
    return ExtractedMotorhome(
        motorhome=Motorhome(**fields),
        provenance={
            "rrp_pounds": Provenance(source_url=RANGE_URL, snippet="£93,950"),
            "mro_kilograms": Provenance(source_url=RANGE_URL, snippet="MIRO-min 3184"),
        },
    )


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root


@pytest.fixture
def export_path(data_root: Path) -> Path:
    """A baseline export holding one Adria product and one from another brand.

    The second row is the point: `execute_run` must filter the baseline down to the
    manufacturer being run before diffing, or products could match across brands.
    """
    path = paths.exports_dir(root=data_root) / "2026-08-04" / "export.csv"
    io.write_csv(
        [
            make_baseline(),
            make_baseline(
                product_id=9001,
                manufacturer="Swift Group Ltd",
                manufacturer_display_name="Swift",
                manufacturer_range="Matrix",
                model="Supreme 670 DC",
            ),
        ],
        path,
    )
    return path


def run_once(
    *, data_root: Path, export_path: Path, adapter: FakeAdapter, **kwargs: Any
) -> Any:
    return execute_run(
        manufacturer=make_manufacturer(),
        adapter=adapter,
        export_path=export_path,
        data_root=data_root,
        _fetcher_factory=FakeFetcher,
        _browser_factory=FakeFetcher,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Resolving what to run
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("needle", ["Adria", "adria", "Adria Mobil", "ADRIA MOBIL", "3"])
def test_manufacturer_resolves_by_display_name_full_name_or_id(needle: str) -> None:
    manufacturers = [
        make_manufacturer(),
        make_manufacturer(
            manufacturer_id=26, fmlv_manufacturer="Swift Group Ltd", fmlv_display_name="Swift"
        ),
    ]
    assert find_manufacturer(manufacturers, needle).manufacturer_id == 3


def test_unknown_manufacturer_lists_the_known_ones() -> None:
    with pytest.raises(CommandError, match="Adria"):
        find_manufacturer([make_manufacturer()], "Hymer")


def test_ambiguous_manufacturer_asks_for_the_id() -> None:
    manufacturers = [make_manufacturer(), make_manufacturer(manufacturer_id=99)]
    with pytest.raises(CommandError, match="manufacturer_id"):
        find_manufacturer(manufacturers, "Adria")


def test_latest_export_picks_the_most_recently_modified(data_root: Path) -> None:
    exports = paths.exports_dir(root=data_root)
    (exports / "old").mkdir(parents=True)
    (exports / "new").mkdir(parents=True)
    older = exports / "old" / "export.csv"
    newer = exports / "new" / "export.xlsx"
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    import os

    os.utime(older, (1_000_000, 1_000_000))

    assert latest_export(root=data_root) == newer


def test_latest_export_with_nothing_downloaded_is_a_command_error(data_root: Path) -> None:
    with pytest.raises(CommandError, match="--export"):
        latest_export(root=data_root)


def test_resolve_ranges_selects_by_label_case_insensitively() -> None:
    adapter = FakeAdapter(products=[])
    assert resolve_ranges(adapter, ["matrix"]) == (("motorhomes/matrix", "Matrix"),)


def test_resolve_ranges_rejects_an_unknown_range() -> None:
    with pytest.raises(CommandError, match="Known ranges"):
        resolve_ranges(FakeAdapter(products=[]), ["Nonesuch"])


def test_resolve_ranges_rejects_an_adapter_that_has_no_ranges() -> None:
    with pytest.raises(CommandError, match="does not support --range"):
        resolve_ranges(SimpleNamespace(__name__="fake"), ["Matrix"])


# --------------------------------------------------------------------------- #
# The pipeline, end to end
# --------------------------------------------------------------------------- #


def test_a_run_records_everything_from_registry_to_review_queue(
    data_root: Path, export_path: Path
) -> None:
    adapter = FakeAdapter(products=[make_extracted(rrp_pounds=94950)])

    summary = run_once(data_root=data_root, export_path=export_path, adapter=adapter)

    assert summary.run.status == "succeeded"
    assert summary.run.finished_at is not None
    # Only the Adria row is the baseline — the Swift row must not be diffed against.
    assert summary.baseline_count == 1
    assert summary.scraped_count == 1
    assert summary.kinds["changed_field"] == 1

    connection = store.connect(paths.db_path(root=data_root))
    try:
        queue = store.list_change_queue(connection, summary.run.id)
        by_field = {entry.change.field: entry.change for entry in queue}
        assert by_field["rrp_pounds"].old_value == "93950"
        assert by_field["rrp_pounds"].new_value == "94950"
        assert by_field["rrp_pounds"].source_url == RANGE_URL
        # The product was matched to the baseline, not treated as new.
        assert queue[0].product.fmlv_product_id == 4147
        # mro_kilograms was checked and matched — a first-class result (DESIGN.md §6.5).
        verified = connection.execute(
            "SELECT field FROM verification WHERE run_id = ?", (summary.run.id,)
        ).fetchall()
        assert [row["field"] for row in verified] == ["mro_kilograms"]
    finally:
        connection.close()


def test_the_adapter_is_given_the_runs_own_snapshot_directory(
    data_root: Path, export_path: Path
) -> None:
    adapter = FakeAdapter(products=[make_extracted()])

    summary = run_once(data_root=data_root, export_path=export_path, adapter=adapter)

    assert adapter.calls is not None
    assert adapter.calls[0]["snapshot_dir"] == paths.snapshot_dir(3, summary.run.id, root=data_root)
    assert summary.snapshot_dir.is_dir()


def test_range_selection_is_passed_through_to_the_adapter(
    data_root: Path, export_path: Path
) -> None:
    adapter = FakeAdapter(products=[make_extracted()])

    run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=adapter,
        collect_kwargs={"ranges": (("motorhomes/matrix", "Matrix"),)},
    )

    assert adapter.calls is not None
    assert adapter.calls[0]["ranges"] == (("motorhomes/matrix", "Matrix"),)


def test_a_failing_adapter_marks_the_run_failed_and_re_raises(
    data_root: Path, export_path: Path
) -> None:
    adapter = FakeAdapter(products=[], error=RuntimeError("site is down"))

    with pytest.raises(RuntimeError, match="site is down"):
        run_once(data_root=data_root, export_path=export_path, adapter=adapter)

    connection = store.connect(paths.db_path(root=data_root))
    try:
        run = store.list_runs(connection)[0]
        assert run.status == "failed"
        assert "site is down" in (run.error_message or "")
        assert run.finished_at is not None
    finally:
        connection.close()


def test_a_second_run_reuses_the_same_product_rows(data_root: Path, export_path: Path) -> None:
    """A rename on the manufacturer's site must not create a duplicate product."""
    first = run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=FakeAdapter(products=[make_extracted(rrp_pounds=94950)]),
    )
    second = run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=FakeAdapter(
            products=[make_extracted(rrp_pounds=95950, model="670 DC Supreme Alde")]
        ),
    )

    assert second.run.id != first.run.id
    connection = store.connect(paths.db_path(root=data_root))
    try:
        products = store.list_products(connection, manufacturer_id=3)
        assert len(products) == 1
        assert products[0].model == "670 DC Supreme Alde"
        assert products[0].first_seen_run_id == first.run.id
        assert products[0].last_seen_run_id == second.run.id
    finally:
        connection.close()


def test_bump_year_proposes_a_year_change_on_an_otherwise_unchanged_product(
    data_root: Path, export_path: Path
) -> None:
    """DESIGN.md §6.9 route 1 — still a proposal a reviewer has to accept."""
    adapter = FakeAdapter(products=[make_extracted()])  # identical to the baseline

    summary = run_once(
        data_root=data_root, export_path=export_path, adapter=adapter, bump_year=True
    )

    assert summary.kinds["unchanged_confirmed"] == 1
    assert summary.persisted.year_rollover_proposed == 1

    connection = store.connect(paths.db_path(root=data_root))
    try:
        queue = store.list_change_queue(connection, summary.run.id)
        assert [entry.change.field for entry in queue] == ["year"]
        assert (queue[0].change.old_value, queue[0].change.new_value) == ("2026", "2027")
        # The suggestion came from the operator, not the manufacturer's site.
        assert queue[0].change.source_url is None
        # And nothing was decided on its behalf.
        assert queue[0].decision is None
    finally:
        connection.close()


def test_without_bump_year_an_unchanged_product_proposes_nothing(
    data_root: Path, export_path: Path
) -> None:
    summary = run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=FakeAdapter(products=[make_extracted()]),
    )

    assert summary.persisted.proposed == 0
    assert summary.persisted.verified == 2


def test_on_progress_is_threaded_through_to_the_adapter(
    data_root: Path, export_path: Path
) -> None:
    """The adapter's `on_progress` is how a long live sweep narrates itself to the
    terminal (adria.collect calls it at range/product boundaries and on a skip) —
    `execute_run` has to actually hand the adapter a working callback for that to work."""
    adapter = FakeAdapter(products=[make_extracted()])
    messages: list[str] = []

    run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=adapter,
        on_progress=messages.append,
    )

    assert adapter.calls is not None
    adapter.calls[0]["on_progress"]("a progress line")
    assert messages == ["a progress line"]


def test_on_progress_defaults_to_a_silent_no_op(data_root: Path, export_path: Path) -> None:
    adapter = FakeAdapter(products=[make_extracted()])

    run_once(data_root=data_root, export_path=export_path, adapter=adapter)

    assert adapter.calls is not None
    adapter.calls[0]["on_progress"]("should not raise")


def test_summary_reports_the_run(data_root: Path, export_path: Path) -> None:
    summary = run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=FakeAdapter(products=[make_extracted(rrp_pounds=94950)]),
    )

    text = format_summary(summary)
    assert "Adria Mobil" in text
    assert "succeeded" in text
    assert f"/runs/{summary.run.id}" in text


# --------------------------------------------------------------------------- #
# Argument handling
# --------------------------------------------------------------------------- #


def test_unknown_manufacturer_exits_two_without_a_traceback(
    data_root: Path, export_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = data_root / "manufacturers.csv"
    registry.write_text(
        "manufacturer_id,fmlv_manufacturer,website_url\n3,Adria Mobil,https://example.invalid/\n",
        encoding="utf-8",
    )

    exit_code = main(["run", "Hymer", "--data-dir", str(data_root)])

    assert exit_code == 2
    assert "Hymer" in capsys.readouterr().err


def test_missing_registry_exits_two(
    data_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["run", "Adria", "--data-dir", str(data_root)])

    assert exit_code == 2
    assert "registry not found" in capsys.readouterr().err


def test_manufacturer_without_an_adapter_says_which_ones_exist(
    data_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = data_root / "manufacturers.csv"
    registry.write_text(
        "manufacturer_id,fmlv_manufacturer,website_url\n26,Swift Group Ltd,https://example.invalid/\n",
        encoding="utf-8",
    )

    exit_code = main(["run", "Swift Group Ltd", "--data-dir", str(data_root)])

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "no adapter written" in error
    assert "Adria Mobil" in error
