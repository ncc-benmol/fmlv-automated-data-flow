"""The command line: `fmlv run <manufacturer>`.

Every stage this drives already exists as a library and is tested on its own — until
now nothing performed the *sequence*, which is the one thing no unit test covers. So
this module is deliberately only wiring and reporting: resolve the registry row, start
a `run` record, hand the fetchers to that manufacturer's adapter, diff what comes back
against the baseline export, and persist the result for the review app (DESIGN.md §5).

Four decisions worth knowing about:

* **The baseline is filtered to one manufacturer before diffing, archived rows and
  stale model years are dropped, and same-range/model duplicates are collapsed to the
  newest model year.** `diff.match_products` requires the manufacturer filter and
  nothing enforces it — an unfiltered baseline would let one brand's product match
  another brand's row. The filter is `Motorhome.manufacturer ==
  Manufacturer.fmlv_manufacturer`, which is precisely what that registry column exists
  to guarantee. Rows with `archived=Yes` are excluded too: they're gone from FMLV
  already, so there's nothing to diff a scraped product against.
  `_is_current_model_year` excludes everything except this calendar year and next —
  FMLV keeps every model year a manufacturer has ever listed, and only the current and
  next year's models are ever live for sale, so anything older is noise for the diff.
  `_dedupe_baseline` handles a third case found on a real Swift run: the export can
  carry two *non-archived* rows for the same `manufacturer_range`/`model` under
  different `product_id`s (an older listing FMLV never archived when the newer one was
  added). Left alone, one scraped product matches one of the two, the other goes
  unmatched and is proposed for archiving — but `store.products.upsert_seen`'s
  range/model fallback then folds that archive proposal onto the *same* product row as
  the match's field changes, since the two duplicates are indistinguishable by
  range/model alone. Keeping only the row with the higher `year` (ties broken by
  leaving the first one seen) avoids ever creating the DISAPPEARED half of that pair;
  the discarded duplicates are exactly what a human would call archived, so this is a
  baseline-quality fix, not a matching one.

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
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import paths, store
from .adapters import Adapter, adapter_for
from .diff import DEFAULT_THRESHOLD, diff_products
from .fetch.browser import BrowserFetcher
from .fetch.http import Fetcher
from .fetch.ncc import (
    NccCredentials,
    NccCredentialsError,
    NccExportError,
    caravan_export_path,
    download_export,
)
from .output import generate_upload
from .product_model import caravan_io, io
from .product_model.model import Motorhome
from .product_model.product import Product
from .registry import Manufacturer, loader
from .store.runs import Trigger
from .vehicle_class import DEFAULT as DEFAULT_VEHICLE_CLASS
from .vehicle_class import VehicleClass

#: Export file types `product_model.io.read_export` can dispatch on.
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


def latest_export(
    *,
    root: Path,
    manufacturer_id: int,
    manufacturer_name: str,
    vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS,
) -> Path:
    """The most recently modified FMLV export for one manufacturer and product area.

    `fetch/ncc.py`'s download is per-manufacturer (the NCC site offers exports no
    other way), so the search is scoped to that manufacturer's own subdirectory under
    `data/exports/` — otherwise a stale export downloaded for a *different*
    manufacturer could silently become today's baseline. `fetch-export` names each
    download `<date>_<manufacturer>_<area>.xlsx` directly in that subdirectory (no
    per-date nesting), so "newest file wins" is the right default for a scheduled run;
    `--export` overrides it when testing against one specific baseline.

    **The area is part of the filter, not a nicety.** One export action saves both
    sheets side by side in that directory, so "newest file wins" alone would hand a
    caravan run whichever of the two happened to be written last — and a motorhome
    baseline against caravan scrapes classifies all 23 caravans as new products and all
    45 motorhomes as disappeared.
    """
    directory = paths.manufacturer_exports_dir(manufacturer_id, manufacturer_name, root=root)
    stem = VehicleClass(vehicle_class).export_stem
    candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in EXPORT_SUFFIXES and stem in path.name
    ]
    if not candidates:
        msg = (
            f"no {' or '.join(EXPORT_SUFFIXES)} export matching {stem!r} found under "
            f"{directory} — run `fmlv fetch-export` first, or point at one with --export"
        )
        raise CommandError(msg)
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_baseline(path: Path | str, vehicle_class: VehicleClass) -> list[Product]:
    """Every product in one export, parsed against that product area's schema.

    The two schemas share a file format and almost no columns, so reading a caravan
    export through `io.read_export` yields 81 products with every dimension blank rather
    than an error — which is why the caller states the area rather than this guessing it.
    """
    if VehicleClass(vehicle_class) is VehicleClass.CARAVAN:
        return list(caravan_io.read_export(path).caravans)
    return list(io.read_export(path).motorhomes)


def fetch_export(
    *,
    manufacturer: Manufacturer,
    data_root: Path,
    headless: bool = True,
    on_progress: Callable[[str], None] = lambda message: None,
    vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS,
) -> Path:
    """Log in to the NCC site and download one manufacturer's current export.

    The shared implementation behind `fmlv fetch-export` and, via `execute_run`'s
    `refresh_export`, the automatic baseline refresh a triggered run does before
    diffing — so the two never drift apart on what "the current export" means.

    **Both sheets are always downloaded** — one NCC export action returns them together —
    and `vehicle_class` decides which of the two this returns as *the baseline for this
    run*. Getting that wrong is silent and total rather than an error: a caravan run
    handed the motorhome sheet parses 45 motorhomes as caravans with every dimension
    blank, matches none of them, and reports every caravan as a new product. It did
    exactly that on the first real caravan run, on 3 September 2026.
    """
    if not manufacturer.ncc_supplier_name:
        msg = (
            f"{manufacturer.fmlv_manufacturer!r} has no ncc_supplier_name set in the "
            f"registry — open the NCC site's 'Export Products by Supplier' dropdown "
            f"(/nova/resources/products) and copy the exact label into "
            f"config/manufacturers.csv"
        )
        raise CommandError(msg)

    try:
        credentials = NccCredentials.from_env()
    except NccCredentialsError as exc:
        raise CommandError(str(exc)) from exc

    safe_name = paths.safe_path_component(manufacturer.fmlv_manufacturer)
    # `download_export` is told where to put the motorhome sheet and derives the caravan
    # one from it (`ncc.caravan_export_path`), so the pair stay named and dated together.
    dest_path = (
        paths.manufacturer_exports_dir(
            manufacturer.manufacturer_id, manufacturer.fmlv_manufacturer, root=data_root
        )
        / f"{date.today().isoformat()}_{safe_name}_motorhome-campervans.xlsx"
    )

    try:
        download_export(
            credentials,
            manufacturer.ncc_supplier_name,
            dest_path,
            headless=headless,
            on_progress=on_progress,
        )
    except NccExportError as exc:
        raise CommandError(str(exc)) from exc

    if VehicleClass(vehicle_class) is VehicleClass.CARAVAN:
        caravan_path = caravan_export_path(dest_path)
        if not caravan_path.exists():
            # A motorhome-only supplier's export has no caravan sheet. Silently falling
            # back to the motorhome one is the failure this whole argument exists to
            # prevent, so refuse instead.
            msg = (
                f"{manufacturer.fmlv_manufacturer!r}'s export contains no touring-caravan "
                f"sheet, so there is no caravan baseline to diff against. Check the "
                f"manufacturer really does list caravans on the NCC site."
            )
            raise CommandError(msg)
        return caravan_path

    return dest_path


def _is_current_model_year(year: int | None, *, today: date | None = None) -> bool:
    """Whether `year` is this calendar year or next — the only years worth diffing.

    FMLV carries every model year a manufacturer has ever listed, going back well
    before what's actually for sale — a baseline row from 2022 has nothing live to
    diff a scraped product against. `today` is injectable for tests.
    """
    current_year = (today or date.today()).year
    return year in (current_year, current_year + 1)



def match_threshold(adapter: Adapter) -> float:
    """How similar a scraped product's name must be to a baseline row's to be the same vehicle.

    `diff.matching`'s 0.5 default suits almost every manufacturer, but it is a single
    number applied to a token-bag score, and `docs/adapters/README.md` records why it
    cannot be moved globally: Adria's documented *good* match scores 0.667, lower than
    Etrusco's worst *bad* match at 0.750, so no global value separates them.

    An adapter whose own products happen to be separable declares `MATCH_THRESHOLD` and
    this returns it — the same `getattr` opt-in as `DEFAULT_RANGES` and
    `baseline_in_scope`, so no other manufacturer is affected. This is the
    per-manufacturer threshold that README names as "the shape to reach for".
    """
    return float(getattr(adapter, "MATCH_THRESHOLD", DEFAULT_THRESHOLD))


def baseline_scope(
    adapter: Adapter, ranges: Sequence[tuple[str, str]]
) -> Callable[[Motorhome], bool]:
    """Which baseline rows a `--range`-narrowed run should diff against.

    Usually a range selector *is* the FMLV `manufacturer_range`, so the default is a
    straight match on that column. An adapter whose selectors don't map that way
    declares a `baseline_in_scope(motorhome, labels)` function and this defers to it —
    the same `getattr` opt-in as `DEFAULT_RANGES`, so no other adapter is affected.

    Adria is the case that needs it: its 60Y editions live on their own range pages but
    FMLV files them under the ordinary range, marked in the model. Getting the scope
    wrong is not cosmetic in either direction — too narrow and a product the NCC already
    holds is proposed as new (a duplicate on upload), too wide and live products the run
    never swept are reported as disappeared.
    """
    labels = {label for _path, label in ranges}
    hook = getattr(adapter, "baseline_in_scope", None)
    if hook is None:
        return lambda motorhome: motorhome.manufacturer_range in labels
    return lambda motorhome: bool(hook(motorhome, labels))


def _dedupe_baseline(motorhomes: Iterable[Motorhome]) -> list[Motorhome]:
    """Collapse baseline rows sharing a `(manufacturer_range, model)` to the newest.

    See the module docstring's third bullet for why this exists — a real Swift export
    had two non-archived rows both named "Escape 674" under different `product_id`s.
    Ties (equal or both-`None` `year`) keep whichever row was seen first, which is
    arbitrary but stable. Rows with no `manufacturer_range` or no `model` can't be
    compared this way and are passed through untouched rather than being collapsed
    into each other by a shared blank key.
    """
    groups: dict[tuple[str, str], list[Motorhome]] = defaultdict(list)
    passthrough: list[Motorhome] = []
    order: list[tuple[str, str]] = []
    for motorhome in motorhomes:
        if not motorhome.manufacturer_range or not motorhome.model:
            passthrough.append(motorhome)
            continue
        key = (motorhome.manufacturer_range, motorhome.model)
        if key not in groups:
            order.append(key)
        groups[key].append(motorhome)

    deduped = [
        max(group, key=lambda motorhome: motorhome.year if motorhome.year is not None else -1)
        for key in order
        for group in (groups[key],)
    ]
    return passthrough + deduped


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
    export_path: Path | None = None,
    data_root: Path = paths.DATA_DIR,
    trigger: Trigger = "manual",
    bump_year: bool = False,
    refresh_export: bool = False,
    vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS,
    collect_kwargs: dict[str, Any] | None = None,
    on_progress: Callable[[str], None] = lambda message: None,
    on_run_started: Callable[[store.Run], None] = lambda run: None,
    _fetcher_factory: Callable[[Path], Fetcher] = Fetcher,
    _browser_factory: Callable[[Path], BrowserFetcher] = BrowserFetcher,
    _export_fetcher: Callable[..., Path] = fetch_export,
) -> RunSummary:
    """Run one manufacturer end to end, recording everything against a `run` row.

    `on_run_started` fires right after the `run` row is inserted, before the slow
    fetch/diff work begins — a caller that kicks this off on a background thread (the
    review app's "trigger a run" page) can use it to learn the real `run.id` and
    redirect a waiting request there, without waiting for the whole run to finish.

    `refresh_export=True` downloads a fresh baseline from the NCC site before diffing
    (`fetch_export`, the same thing `fmlv fetch-export` does) instead of diffing
    against whatever happens to already be on disk — the review app's "trigger a run"
    page always sets this, since a reviewer expects "trigger a run" to mean "check
    against the current FMLV data", not "check against whatever the last person
    downloaded". `export_path` is then optional and, if given anyway, is ignored in
    favour of the freshly downloaded one. Exactly one of `export_path` and
    `refresh_export` must be usable, checked before the `run` row is even created —
    this is a caller mistake, not something to record as a failed run.

    `vehicle_class` names which FMLV product area is being swept, and is recorded on the
    `run` row so the review app can tell a Bailey caravan run from a Bailey motorhome one.
    It defaults to motorhomes, which is what every adapter written so far produces.
    """
    if export_path is None and not refresh_export:
        msg = "execute_run needs export_path, or refresh_export=True to fetch one"
        raise CommandError(msg)

    connection = store.connect(paths.db_path(root=data_root))
    try:
        ranges = (collect_kwargs or {}).get("ranges")
        range_label = ", ".join(label for _path, label in ranges) if ranges else None
        in_scope = baseline_scope(adapter, ranges) if ranges else None
        run = store.start_run(
            connection,
            manufacturer_id=manufacturer.manufacturer_id,
            fmlv_manufacturer=manufacturer.fmlv_manufacturer,
            trigger=trigger,
            range_label=range_label,
            vehicle_class=vehicle_class,
        )
        on_run_started(run)
        snapshot_dir = paths.snapshot_dir(manufacturer.manufacturer_id, run.id, root=data_root)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        try:
            if refresh_export:
                fetch_started = time.monotonic()
                on_progress(
                    f"Fetching latest {manufacturer.fmlv_manufacturer} export from FMLV..."
                )
                export_path = _export_fetcher(
                    manufacturer=manufacturer,
                    data_root=data_root,
                    on_progress=on_progress,
                    vehicle_class=vehicle_class,
                )
                on_progress(
                    f"Using export {export_path} "
                    f"(FMLV login + download took {time.monotonic() - fetch_started:.1f}s)"
                )

            baseline = _dedupe_baseline(
                product
                for product in read_baseline(export_path, vehicle_class)
                if product.manufacturer == manufacturer.fmlv_manufacturer
                and not product.archived
                and _is_current_model_year(product.year)
                and (in_scope is None or in_scope(product))
            )

            # One browser process and one HTTP client for the whole run — the browser
            # is launched even for an adapter that won't use it, which the `Adapter`
            # protocol's shape currently requires. Cheap enough at one run per
            # manufacturer; worth revisiting if a sweep ever launches dozens.
            scrape_started = time.monotonic()
            on_progress(f"Scraping {manufacturer.fmlv_manufacturer} website...")
            with _fetcher_factory(snapshot_dir) as http, _browser_factory(snapshot_dir) as browser:
                scraped = adapter.collect(
                    http, browser, snapshot_dir, on_progress=on_progress, **(collect_kwargs or {})
                )
            on_progress(
                f"Scraped {len(scraped)} product(s) "
                f"(website sweep took {time.monotonic() - scrape_started:.1f}s)"
            )

            diff_started = time.monotonic()
            diffs = diff_products(
                scraped, baseline, threshold=match_threshold(adapter)
            )
            persisted = store.persist_diff(
                connection,
                run_id=run.id,
                manufacturer_id=manufacturer.manufacturer_id,
                diffs=diffs,
                bump_year_all=bump_year,
                vehicle_class=vehicle_class,
            )
            on_progress(
                f"Compared {len(scraped)} scraped against {len(baseline)} baseline product(s) "
                f"(diff + persist took {time.monotonic() - diff_started:.1f}s)"
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
    if persisted.disappeared_noted:
        lines.append(
            f"  missing     {persisted.disappeared_noted} product(s) not found on the "
            "site — no CSV change proposed, consider deactivating manually"
        )
    if persisted.missing_field_proposed:
        lines.append(
            f"              of which {persisted.missing_field_proposed} are "
            "in-scope fields not found this run"
        )
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


def _print_with_timestamp(message: str) -> None:
    """`[14:32:07] message` — so a terminal run shows when each section happened.

    Wall-clock rather than elapsed-since-start: `execute_run` already reports how
    long the FMLV fetch and the website sweep each took as part of the message text
    (see its "took Xs" progress lines), so the timestamp here is for lining that up
    against real time / other logs, not for re-deriving durations by hand.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def _run_command(args: argparse.Namespace) -> int:
    data_root: Path = args.data_dir
    config_root: Path = args.config_dir

    registry_file = args.registry or paths.registry_path(root=config_root)
    if not registry_file.exists():
        msg = f"manufacturer registry not found at {registry_file}"
        raise CommandError(msg)

    registry = loader.load(registry_file)
    for issue in registry.issues:
        if issue.severity == "error":
            print(f"registry error (row {issue.row_number}): {issue.message}", file=sys.stderr)

    manufacturer = find_manufacturer(registry.manufacturers, args.manufacturer)

    vehicle_class = VehicleClass(args.vehicle_class)
    adapter = adapter_for(manufacturer.fmlv_manufacturer, vehicle_class)
    if adapter is None:
        from .adapters import ADAPTERS, adapters_for

        # Name the product area. Bailey has a motorhome adapter and (for now) no caravan
        # one, so a bare "no adapter written for 'Bailey'" would read as plainly wrong to
        # someone who has just run Bailey successfully.
        other_areas = sorted(other.label for other in adapters_for(manufacturer.fmlv_manufacturer))
        available = sorted(f"{name} ({registered.value})" for name, registered in ADAPTERS)
        msg = (
            f"no {vehicle_class.value} adapter written for "
            f"{manufacturer.fmlv_manufacturer!r} yet."
        )
        if other_areas:
            msg += f" It does have: {', '.join(other_areas)}."
        msg += f" Adapters exist for: {', '.join(available) or '(none)'}"
        raise CommandError(msg)

    # Ranges before the export: a mistyped `--range` is answerable from the arguments
    # alone, so it shouldn't be masked by "no export downloaded yet".
    collect_kwargs: dict[str, Any] = {}
    if args.ranges:
        collect_kwargs["ranges"] = resolve_ranges(adapter, args.ranges)

    export_path: Path = args.export or latest_export(
        root=data_root,
        manufacturer_id=manufacturer.manufacturer_id,
        manufacturer_name=manufacturer.fmlv_manufacturer,
    )
    if not export_path.exists():
        msg = f"export not found: {export_path}"
        raise CommandError(msg)

    try:
        summary = execute_run(
            manufacturer=manufacturer,
            adapter=adapter,
            export_path=export_path,
            data_root=data_root,
            trigger=args.trigger,
            bump_year=args.bump_year,
            vehicle_class=vehicle_class,
            collect_kwargs=collect_kwargs,
            on_progress=_print_with_timestamp,
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


def _fetch_export_command(args: argparse.Namespace) -> int:
    """`fmlv fetch-export <manufacturer>`: log in to the NCC site and download its export.

    Thin wiring over `fetch_export` — registry resolution plus the same error
    reporting `_run_command` uses.
    """
    data_root: Path = args.data_dir
    config_root: Path = args.config_dir

    registry_file = args.registry or paths.registry_path(root=config_root)
    if not registry_file.exists():
        msg = f"manufacturer registry not found at {registry_file}"
        raise CommandError(msg)

    registry = loader.load(registry_file)
    manufacturer = find_manufacturer(registry.manufacturers, args.manufacturer)

    dest_path = fetch_export(
        manufacturer=manufacturer,
        data_root=data_root,
        headless=not args.show_browser,
        on_progress=_print_with_timestamp,
    )

    print(f"downloaded {manufacturer.fmlv_manufacturer} export to {dest_path}")
    return 0


def _generate_upload_command(args: argparse.Namespace) -> int:
    """`fmlv generate-upload <run_id>`: build the upload CSV from a run's decisions.

    Deliberately its own command rather than something `run` does automatically —
    the CSV should only be produced once a reviewer has actually been through the
    change queue, not the moment a run finishes (the review app's "Generate upload"
    button, added alongside this, is the same rule enforced in the browser).
    """
    data_root: Path = args.data_dir
    config_root: Path = args.config_dir
    connection = store.connect(paths.db_path(root=data_root))
    try:
        try:
            run = store.get_run(connection, args.run_id)
        except KeyError as exc:
            raise CommandError(str(exc)) from exc

        if run.status != "succeeded":
            msg = f"run #{run.id} is {run.status!r}, not 'succeeded' — nothing to upload"
            raise CommandError(msg)

        registry_file = args.registry or paths.registry_path(root=config_root)
        if not registry_file.exists():
            msg = f"manufacturer registry not found at {registry_file}"
            raise CommandError(msg)
        registry = loader.load(registry_file)
        manufacturer = find_manufacturer(registry.manufacturers, str(run.manufacturer_id))

        export_path: Path = args.export or latest_export(
            root=data_root,
            manufacturer_id=manufacturer.manufacturer_id,
            manufacturer_name=manufacturer.fmlv_manufacturer,
            vehicle_class=run.vehicle_class,
        )
        if not export_path.exists():
            msg = f"export not found: {export_path}"
            raise CommandError(msg)

        baseline = _dedupe_baseline(
            product
            for product in read_baseline(export_path, run.vehicle_class)
            if product.manufacturer == manufacturer.fmlv_manufacturer
            and not product.archived
            and _is_current_model_year(product.year)
        )

        queue = store.list_change_queue(connection, run.id)
        pending = sum(1 for entry in queue if entry.decision is None)
        if pending:
            print(
                f"warning: {pending} change(s) on run #{run.id} are still awaiting a "
                f"decision — the upload will only include what's already been reviewed",
                file=sys.stderr,
            )

        result = generate_upload(
            connection,
            run_id=run.id,
            manufacturer=manufacturer,
            baseline=baseline,
            path=paths.upload_csv_path(
                run.id, vehicle_class=run.vehicle_class, root=data_root
            ),
            vehicle_class=run.vehicle_class,
        )
    finally:
        connection.close()

    print(f"wrote {len(result.motorhomes)} product(s) to {result.path}")
    for issue in result.issues:
        print(f"  {issue.severity}: {issue.message}", file=sys.stderr)
    if result.has_errors:
        print(
            "warning: the CSV has validation errors — review before uploading",
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
        "--config-dir",
        type=Path,
        default=paths.CONFIG_DIR,
        help=f"root for the manufacturer registry (default: {paths.CONFIG_DIR})",
    )
    run_parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="manufacturer registry CSV (default: <config-dir>/manufacturers.csv)",
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
    run_parser.add_argument(
        "--class",
        dest="vehicle_class",
        choices=tuple(member.value for member in VehicleClass),
        default=DEFAULT_VEHICLE_CLASS.value,
        help=(
            "which FMLV product area to sweep — a manufacturer that builds both has a "
            "separate adapter for each (default: %(default)s)"
        ),
    )
    run_parser.set_defaults(handler=_run_command)

    fetch_export_parser = subparsers.add_parser(
        "fetch-export",
        help="log in to the NCC site and download one manufacturer's current export",
    )
    fetch_export_parser.add_argument(
        "manufacturer",
        help="registry name, display name or manufacturer_id — e.g. 'Adria', 'Adria Mobil', 3",
    )
    fetch_export_parser.add_argument(
        "--data-dir",
        type=Path,
        default=paths.DATA_DIR,
        help=f"root for exports (default: {paths.DATA_DIR})",
    )
    fetch_export_parser.add_argument(
        "--config-dir",
        type=Path,
        default=paths.CONFIG_DIR,
        help=f"root for the manufacturer registry (default: {paths.CONFIG_DIR})",
    )
    fetch_export_parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="manufacturer registry CSV (default: <config-dir>/manufacturers.csv)",
    )
    fetch_export_parser.add_argument(
        "--show-browser",
        action="store_true",
        help="run non-headless, for debugging against the real site",
    )
    fetch_export_parser.set_defaults(handler=_fetch_export_command)

    generate_upload_parser = subparsers.add_parser(
        "generate-upload",
        help="build the upload-ready CSV from a run's reviewed decisions",
    )
    generate_upload_parser.add_argument(
        "run_id",
        type=int,
        help="the run whose reviewed changes should be built into an upload CSV",
    )
    generate_upload_parser.add_argument(
        "--export",
        type=Path,
        default=None,
        help="baseline FMLV export to apply decisions on top of (default: newest under data/exports/)",
    )
    generate_upload_parser.add_argument(
        "--data-dir",
        type=Path,
        default=paths.DATA_DIR,
        help=f"root for exports and the run store (default: {paths.DATA_DIR})",
    )
    generate_upload_parser.add_argument(
        "--config-dir",
        type=Path,
        default=paths.CONFIG_DIR,
        help=f"root for the manufacturer registry (default: {paths.CONFIG_DIR})",
    )
    generate_upload_parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="manufacturer registry CSV (default: <config-dir>/manufacturers.csv)",
    )
    generate_upload_parser.set_defaults(handler=_generate_upload_command)

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
