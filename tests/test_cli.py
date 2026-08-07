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

from src import paths, store
from src.adapters import ADAPTERS
from src.adapters.base import ExtractedMotorhome, Provenance
from src.cli import (
    CommandError,
    _dedupe_baseline,
    execute_run,
    find_manufacturer,
    format_summary,
    latest_export,
    main,
    resolve_ranges,
)
from src.product_model import io
from src.product_model.model import Motorhome
from src.registry.models import Manufacturer, Status, TriState

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
        "ncc_supplier_name": "Adria Caravans & Motorhomes",
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
    exports = paths.manufacturer_exports_dir(3, "Adria Mobil", root=data_root)
    exports.mkdir(parents=True)
    older = exports / "2026-08-03_Adria-Mobil_motorhome-campervans.csv"
    newer = exports / "2026-08-04_Adria-Mobil_motorhome-campervans.xlsx"
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    import os

    os.utime(older, (1_000_000, 1_000_000))

    assert (
        latest_export(root=data_root, manufacturer_id=3, manufacturer_name="Adria Mobil")
        == newer
    )


def test_latest_export_ignores_a_different_manufacturers_export(data_root: Path) -> None:
    # A real bug found during Phase 7: downloading manufacturer A's export must not
    # let it be silently picked up as manufacturer B's baseline.
    other = paths.manufacturer_exports_dir(26, "Swift Group Ltd", root=data_root)
    other.mkdir(parents=True)
    (other / "2026-08-04_Swift-Group-Ltd_motorhome-campervans.xlsx").write_text(
        "swift", encoding="utf-8"
    )

    with pytest.raises(CommandError, match="--export"):
        latest_export(root=data_root, manufacturer_id=3, manufacturer_name="Adria Mobil")


def test_latest_export_with_nothing_downloaded_is_a_command_error(data_root: Path) -> None:
    with pytest.raises(CommandError, match="--export"):
        latest_export(root=data_root, manufacturer_id=3, manufacturer_name="Adria Mobil")


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


def test_a_range_scoped_run_only_diffs_baseline_rows_from_that_range(
    data_root: Path, export_path: Path
) -> None:
    """A run restricted to one range must not propose archiving other ranges' products.

    `export_path` already has an Adria/Matrix baseline row; add an Adria/Coral one too.
    A run scoped to `ranges=(("motorhomes/matrix", "Matrix"),)` that scrapes nothing
    should leave the Coral row alone — it was never in scope for this run — and only
    the unmatched Matrix row should come back as a proposed archive.
    """
    io.write_csv(
        [
            *io.read_export(export_path).motorhomes,
            make_baseline(
                product_id=4148,
                manufacturer_range="Coral",
                model="Coral Supreme 670 SL",
            ),
        ],
        export_path,
    )
    adapter = FakeAdapter(products=[])

    summary = run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=adapter,
        collect_kwargs={"ranges": (("motorhomes/matrix", "Matrix"),)},
    )

    # Only the Matrix row is in scope — Swift and Coral rows must not be diffed against.
    assert summary.baseline_count == 1
    assert summary.kinds["disappeared"] == 1

    connection = store.connect(paths.db_path(root=data_root))
    try:
        queue = store.list_change_queue(connection, summary.run.id)
        archived_ids = {entry.product.fmlv_product_id for entry in queue}
        assert archived_ids == {4147}
    finally:
        connection.close()


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


def test_dedupe_baseline_keeps_the_newer_of_two_rows_sharing_range_and_model() -> None:
    """The real Swift case: 'Escape 674' listed twice under different product_ids."""
    older = make_baseline(product_id=1765, year=2025)
    newer = make_baseline(product_id=7614, year=2026)

    deduped = _dedupe_baseline([older, newer])

    assert deduped == [newer]


def test_dedupe_baseline_breaks_a_year_tie_by_keeping_the_first_seen() -> None:
    first = make_baseline(product_id=1765, year=2026)
    second = make_baseline(product_id=7614, year=2026)

    assert _dedupe_baseline([first, second]) == [first]


def test_dedupe_baseline_leaves_rows_with_no_duplicate_untouched() -> None:
    a = make_baseline(product_id=1, manufacturer_range="Escape", model="640")
    b = make_baseline(product_id=2, manufacturer_range="Escape", model="674")

    assert _dedupe_baseline([a, b]) == [a, b]


def test_dedupe_baseline_passes_through_rows_with_no_model_untouched() -> None:
    blank_a = make_baseline(product_id=1, model=None)
    blank_b = make_baseline(product_id=2, model=None)

    assert _dedupe_baseline([blank_a, blank_b]) == [blank_a, blank_b]


def test_a_run_collapses_a_duplicate_baseline_row_instead_of_proposing_to_archive_it(
    data_root: Path,
) -> None:
    """End to end: the older duplicate must not surface as a DISAPPEARED/archive
    proposal once the newer one has matched the scraped product."""
    path = paths.exports_dir(root=data_root) / "2026-08-04" / "export.csv"
    io.write_csv(
        [
            make_baseline(product_id=1765, year=2025, mro_kilograms=3251),
            make_baseline(product_id=7614, year=2026, mro_kilograms=3251),
        ],
        path,
    )
    adapter = FakeAdapter(products=[make_extracted(mro_kilograms=3490)])

    summary = run_once(data_root=data_root, export_path=path, adapter=adapter)

    assert summary.baseline_count == 1
    assert summary.kinds["disappeared"] == 0
    assert summary.persisted.archive_proposed == 0
    connection = store.connect(paths.db_path(root=data_root))
    try:
        queue = store.list_change_queue(connection, summary.run.id)
        assert queue[0].product.fmlv_product_id == 7614
        assert not any(entry.change.field == "archived" for entry in queue)
    finally:
        connection.close()


def test_archived_baseline_rows_are_excluded_from_the_baseline(
    data_root: Path,
) -> None:
    """An archived row must not be diffed against — it's already off FMLV."""
    path = paths.exports_dir(root=data_root) / "2026-08-04" / "export.csv"
    io.write_csv(
        [
            make_baseline(),
            make_baseline(product_id=4148, model="Old 670 DC", archived=True),
        ],
        path,
    )
    adapter = FakeAdapter(products=[make_extracted()])

    summary = run_once(data_root=data_root, export_path=path, adapter=adapter)

    assert summary.baseline_count == 1


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
    # Rimor is a real registry row with no adapter yet. It used to be Swift here, until
    # Swift got one — so pick a brand still genuinely unsupported, and expect the
    # message to list whichever adapters do exist rather than naming them one by one.
    registry = data_root / "manufacturers.csv"
    registry.write_text(
        "manufacturer_id,fmlv_manufacturer,website_url\n75,Rimor,https://example.invalid/\n",
        encoding="utf-8",
    )

    exit_code = main(["run", "Rimor", "--data-dir", str(data_root)])

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "no adapter written" in error
    for supported in ADAPTERS:
        assert supported in error


# --------------------------------------------------------------------------- #
# `generate-upload`
# --------------------------------------------------------------------------- #


def test_generate_upload_writes_a_timestamped_csv_from_reviewed_decisions(
    data_root: Path, export_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = data_root / "manufacturers.csv"
    registry.write_text(
        "manufacturer_id,fmlv_manufacturer,website_url\n3,Adria Mobil,https://example.invalid/\n",
        encoding="utf-8",
    )
    summary = run_once(
        data_root=data_root,
        export_path=export_path,
        adapter=FakeAdapter(products=[make_extracted(rrp_pounds=94950)]),
    )
    connection = store.connect(paths.db_path(root=data_root))
    for entry in store.list_change_queue(connection, summary.run.id):
        store.record_decision(
            connection, proposed_change_id=entry.change.id, action="accept", decided_by="ben"
        )
    connection.close()

    exit_code = main(
        [
            "generate-upload",
            str(summary.run.id),
            "--data-dir",
            str(data_root),
            "--export",
            str(export_path),
        ]
    )

    assert exit_code == 0
    assert "wrote 1 product(s)" in capsys.readouterr().out
    written = list(paths.uploads_dir(root=data_root).glob(f"run{summary.run.id}_*.csv"))
    assert len(written) == 1
    assert written[0].name.startswith(f"run{summary.run.id}_")


def test_generate_upload_refuses_a_run_that_has_not_succeeded(
    data_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = data_root / "manufacturers.csv"
    registry.write_text(
        "manufacturer_id,fmlv_manufacturer,website_url\n3,Adria Mobil,https://example.invalid/\n",
        encoding="utf-8",
    )
    connection = store.connect(paths.db_path(root=data_root))
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    connection.close()

    exit_code = main(["generate-upload", str(run.id), "--data-dir", str(data_root)])

    assert exit_code == 2
    assert "not 'succeeded'" in capsys.readouterr().err
