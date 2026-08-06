"""The command line: `fmlv run <manufacturer>`.

Every stage this drives already exists as a library and is tested on its own — until
now nothing performed the *sequence*, which is the one thing no unit test covers. So
this module is deliberately only wiring and reporting: resolve the registry row, start
a `run` record, hand the fetchers to that manufacturer's adapter, diff what comes back
against the baseline export, and persist the result for the review app (DESIGN.md §5).

Four decisions worth knowing about:

* **The baseline is filtered to one manufacturer before diffing.**
  `diff.match_products` requires this and nothing enforces it — an unfiltered baseline
  would let one brand's product match another brand's row. The filter is
  `Motorhome.manufacturer == Manufacturer.fmlv_manufacturer`, which is precisely what
  that registry column exists to guarantee.

* **A run that raises is still recorded**, as `status='failed'` with the message,
  rather than left stuck at `'running'` forever. Whatever was snapshotted before the
  failure stays on disk, so a half-finished run is still debuggable.

* **`--bump-year` is route 1 of DESIGN.md §6.9** — the model-year rollover applied to
  every product of a manufacturer on explicit human instruction. It proposes the bump
  as an ordinary `proposed_change` row that still has to be accepted in the review app;
  it does not write `year` anywhere by itself. Route 2 (the per-product suggestion
  during the June–September window) needs no flag and happens regardless.

* **The fetcher factories are injectable** (`_fetcher_factory` / `_browser_factory`,
  following the same underscore convention as `fetch.http.Fetcher`'s `_sleep`) so that
  `execute_run` — the whole pipeline, the interesting part — is testable without a
  network or a Chromium process.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import paths, store
from .adapters import Adapter, adapter_for
from .diff import diff_products
from .fetch.browser import BrowserFetcher
from .fetch.http import Fetcher
from .fmlv import io
from .registry import Manufacturer, loader
from .store.runs import Trigger

#: Export file types `fmlv.io.read_export` can dispatch on.
EXPORT_SUFFIXES = (".xlsx", ".csv")


class CommandError(Exception):
    """A problem with what was asked for, reported as a message rather than a traceback.

    Reserved for things the person running the command can fix — an unknown
    manufacturer, a missing export, a brand with no adapter yet. A failure *during* a
    run is not one of these: that gets recorded against the run and re-raised.
    """


# --------------------------------------------------------------------------- #
# Resolving what to run
# --------------------------------------------------------------------------- #


def find_manufacturer(manufacturers: Sequence[Manufacturer], needle: str) -> Manufacturer:
    """Resolve a command-line name to exactly one registry row.

    Accepts the numeric `manufacturer_id`, the full `fmlv_manufacturer`, or the shorter
    `fmlv_display_name` — case-insensitively. The long form is what the export uses,
    but "Adria" is what anyone typing a command actually reaches for, and both should
    work.
    """
    wanted = needle.strip().lower()
    matches = [
        manufacturer
        for manufacturer in manufacturers
        if str(manufacturer.manufacturer_id) == wanted
        or manufacturer.fmlv_manufacturer.lower() == wanted
        or (manufacturer.fmlv_display_name or "").lower() == wanted
    ]

    if len(matches) == 1:
        return matches[0]
    if not matches:
        known = ", ".join(
            sorted(m.fmlv_display_name or m.fmlv_manufacturer for m in manufacturers)
        )
        msg = f"no manufacturer matching {needle!r} in the registry. Known: {known or '(none)'}"
        raise CommandError(msg)
    msg = (
        f"{needle!r} matches {len(matches)} registry rows "
        f"({', '.join(m.fmlv_manufacturer for m in matches)}) — use the manufacturer_id"
    )
    raise CommandError(msg)


def latest_export(*, root: Path) -> Path:
    """The most recently modified FMLV export under `data/exports/`.

    Phase 7's Playwright download writes a dated directory per download, so "newest
    file wins" is the right default for a scheduled run; `--export` overrides it when
    testing against one specific baseline.
    """
    directory = paths.exports_dir(root=root)
    candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in EXPORT_SUFFIXES
    ]
    if not candidates:
        msg = (
            f"no {' or '.join(EXPORT_SUFFIXES)} export found under {directory} — "
            f"download one first, or point at it with --export"
        )
        raise CommandError(msg)
    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_ranges(adapter: Adapter, wanted: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Narrow an adapter's ranges to the named ones, for a smoke run against one range.

    Ranges are not part of the `Adapter` protocol — what a "range" is, and whether a
    site even has them, is the adapter's business. So this is an opt-in escape hatch:
    it works for an adapter that publishes a `DEFAULT_RANGES` tuple (as `adria` does)
    and is a clear error for one that doesn't, rather than being silently ignored.
    """
    default: tuple[tuple[str, str], ...] | None = getattr(adapter, "DEFAULT_RANGES", None)
    if default is None:
        msg = f"adapter {getattr(adapter, '__name__', adapter)!r} does not support --range"
        raise CommandError(msg)

    by_label = {label.lower(): (path, label) for path, label in default}
    selected: list[tuple[str, str]] = []
    for name in wanted:
        match = by_label.get(name.strip().lower())
        if match is None:
            known = ", ".join(label for _path, label in default)
            msg = f"unknown range {name!r}. Known ranges: {known}"
            raise CommandError(msg)
        selected.append(match)
    return tuple(selected)


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunSummary:
    """Everything worth reporting about one completed run."""

    run: store.Run
    export_path: Path
    baseline_count: int
    scraped_count: int
    kinds: Counter[str]
    persisted: store.PersistResult
    snapshot_dir: Path


def execute_run(
    *,
    manufacturer: Manufacturer,
    adapter: Adapter,
    export_path: Path,
    data_root: Path = paths.DATA_DIR,
    trigger: Trigger = "manual",
    bump_year: bool = False,
    collect_kwargs: dict[str, Any] | None = None,
    on_progress: Callable[[str], None] = lambda message: None,
    on_run_started: Callable[[store.Run], None] = lambda run: None,
    _fetcher_factory: Callable[[Path], Fetcher] = Fetcher,
    _browser_factory: Callable[[Path], BrowserFetcher] = BrowserFetcher,
) -> RunSummary:
    """Run one manufacturer end to end, recording everything against a `run` row.

    `on_run_started` fires right after the `run` row is inserted, before the slow
    fetch/diff work begins — a caller that kicks this off on a background thread (the
    review app's "trigger a run" page) can use it to learn the real `run.id` and
    redirect a waiting request there, without waiting for the whole run to finish.
    """
    connection = store.connect(paths.db_path(root=data_root))
    try:
        ranges = (collect_kwargs or {}).get("ranges")
        range_label = ", ".join(label for _path, label in ranges) if ranges else None
        run = store.start_run(
            connection,
            manufacturer_id=manufacturer.manufacturer_id,
            fmlv_manufacturer=manufacturer.fmlv_manufacturer,
            trigger=trigger,
            range_label=range_label,
        )
        on_run_started(run)
        snapshot_dir = paths.snapshot_dir(manufacturer.manufacturer_id, run.id, root=data_root)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        try:
            read = io.read_export(export_path)
            baseline = [
                motorhome
                for motorhome in read.motorhomes
                if motorhome.manufacturer == manufacturer.fmlv_manufacturer
            ]

            # One browser process and one HTTP client for the whole run — the browser
            # is launched even for an adapter that won't use it, which the `Adapter`
            # protocol's shape currently requires. Cheap enough at one run per
            # manufacturer; worth revisiting if a sweep ever launches dozens.
            with _fetcher_factory(snapshot_dir) as http, _browser_factory(snapshot_dir) as browser:
                scraped = adapter.collect(
                    http, browser, snapshot_dir, on_progress=on_progress, **(collect_kwargs or {})
                )

            diffs = diff_products(scraped, baseline)
            persisted = store.persist_diff(
                connection,
                run_id=run.id,
                manufacturer_id=manufacturer.manufacturer_id,
                diffs=diffs,
                bump_year_all=bump_year,
            )
            finished = store.finish_run(connection, run.id)
        except Exception as exc:
            store.fail_run(connection, run.id, f"{type(exc).__name__}: {exc}")
            raise

        return RunSummary(
            run=finished,
            export_path=export_path,
            baseline_count=len(baseline),
            scraped_count=len(scraped),
            kinds=Counter(diff.kind.value for diff in diffs),
            persisted=persisted,
            snapshot_dir=snapshot_dir,
        )
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def format_summary(summary: RunSummary) -> str:
    """A short human-readable report of one run, for the terminal."""
    persisted = summary.persisted
    kinds = summary.kinds
    lines = [
        f"{summary.run.fmlv_manufacturer} — run #{summary.run.id} ({summary.run.status})",
        f"  baseline    {summary.baseline_count} products from {summary.export_path}",
        f"  scraped     {summary.scraped_count} products",
        (
            f"  classified  {kinds['changed_field']} changed, "
            f"{kinds['unchanged_confirmed']} unchanged, "
            f"{kinds['new_product']} new, "
            f"{kinds['disappeared']} disappeared"
        ),
        f"  proposed    {persisted.proposed} changes for review",
    ]
    if persisted.year_rollover_proposed:
        lines.append(f"              of which {persisted.year_rollover_proposed} are year bumps")
    lines.append(f"  verified    {persisted.verified} fields checked and unchanged")
    if persisted.suppressed_rejections:
        lines.append(
            f"  suppressed  {persisted.suppressed_rejections} previously-rejected changes"
        )
    lines.append(f"  snapshots   {summary.snapshot_dir}")
    lines.append(f"  review at   /runs/{summary.run.id}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Argument handling
# --------------------------------------------------------------------------- #


def _run_command(args: argparse.Namespace) -> int:
    data_root: Path = args.data_dir

    registry_file = args.registry or paths.registry_path(root=data_root)
    if not registry_file.exists():
        msg = f"manufacturer registry not found at {registry_file}"
        raise CommandError(msg)

    registry = loader.load(registry_file)
    for issue in registry.issues:
        if issue.severity == "error":
            print(f"registry error (row {issue.row_number}): {issue.message}", file=sys.stderr)

    manufacturer = find_manufacturer(registry.manufacturers, args.manufacturer)

    adapter = adapter_for(manufacturer.fmlv_manufacturer)
    if adapter is None:
        from .adapters import ADAPTERS

        msg = (
            f"no adapter written for {manufacturer.fmlv_manufacturer!r} yet. "
            f"Adapters exist for: {', '.join(sorted(ADAPTERS)) or '(none)'}"
        )
        raise CommandError(msg)

    # Ranges before the export: a mistyped `--range` is answerable from the arguments
    # alone, so it shouldn't be masked by "no export downloaded yet".
    collect_kwargs: dict[str, Any] = {}
    if args.ranges:
        collect_kwargs["ranges"] = resolve_ranges(adapter, args.ranges)

    export_path: Path = args.export or latest_export(root=data_root)
    if not export_path.exists():
        msg = f"export not found: {export_path}"
        raise CommandError(msg)

    def report_progress(message: str) -> None:
        print(message, flush=True)

    try:
        summary = execute_run(
            manufacturer=manufacturer,
            adapter=adapter,
            export_path=export_path,
            data_root=data_root,
            trigger=args.trigger,
            bump_year=args.bump_year,
            collect_kwargs=collect_kwargs,
            on_progress=report_progress,
        )
    except Exception as exc:  # noqa: BLE001 — already recorded against the run
        print(f"run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(format_summary(summary))
    if summary.baseline_count == 0:
        print(
            f"warning: the export has no rows for {manufacturer.fmlv_manufacturer!r}, so "
            f"every scraped product was classified as new — check the export and that "
            f"the registry's fmlv_manufacturer matches its 'manufacturer' column",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fmlv",
        description="Automated data flow for Find My Leisure Vehicle.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="run one manufacturer end to end: fetch, diff, and queue changes for review",
    )
    run_parser.add_argument(
        "manufacturer",
        help="registry name, display name or manufacturer_id — e.g. 'Adria', 'Adria Mobil', 3",
    )
    run_parser.add_argument(
        "--export",
        type=Path,
        default=None,
        help="baseline FMLV export to diff against (default: newest under data/exports/)",
    )
    run_parser.add_argument(
        "--data-dir",
        type=Path,
        default=paths.DATA_DIR,
        help=f"root for exports, snapshots and the run store (default: {paths.DATA_DIR})",
    )
    run_parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="manufacturer registry CSV (default: <data-dir>/manufacturers.csv)",
    )
    run_parser.add_argument(
        "--trigger",
        choices=("manual", "scheduled"),
        default="manual",
        help="how this run was triggered, recorded on the run (default: manual)",
    )
    run_parser.add_argument(
        "--range",
        action="append",
        dest="ranges",
        metavar="NAME",
        help="limit the run to one model range, repeatable — e.g. --range Matrix",
    )
    run_parser.add_argument(
        "--bump-year",
        action="store_true",
        help=(
            "propose bumping year on every product of this manufacturer (DESIGN.md "
            "§6.9 route 1). Still reviewed and accepted per product like any change."
        ),
    )
    run_parser.set_defaults(handler=_run_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code: 0 ok, 1 run failed, 2 bad request."""
    args = build_parser().parse_args(argv)
    try:
        handler: Callable[[argparse.Namespace], int] = args.handler
        return handler(args)
    except CommandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
