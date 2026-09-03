"""The review app: FastAPI + HTMX, per DESIGN.md §6.3.

"Others will run and maintain this, not just the author, and reviewer time is the
real bottleneck" — so the app is deliberately small: a home page linking to the two
things a reviewer does (trigger a run, review runs), a run list, and a per-field
accept/reject/correct form that submits via HTMX and swaps just that row back in, no
client-side JavaScript of our own.

`create_app(db_path)` is a factory rather than a module-level app object so tests can
point it at a throwaway SQLite file. `get_connection` is a *module-level* dependency
(not a closure over `app`) reading `request.app.state.db_path`, deliberately — a
closure-based dependency defined inside `create_app` can't be resolved here: this
file uses `from __future__ import annotations`, which stringifies every annotation,
and FastAPI resolves those strings against each function's module globals, not an
enclosing function's locals. Every route opens its own connection and closes it at
the end of the request, sidestepping `sqlite3`'s one-thread-per-connection rule
without needing a long-lived connection pool at this scale.

Triggering a run from the browser (`/trigger`) runs the real pipeline
(`cli.execute_run`) — fetches, PDFs, a headless browser — which can take minutes, so
it can't run inline in the request. It's handed to a worker thread via
`asyncio.to_thread`; the request waits only for `execute_run`'s `on_run_started`
callback to fire (an in-process DB insert, near-instant) and then redirects to the new
run's detail page, which shows "in progress" until the background thread finishes.

A scheduled run (`config/schedule.csv`, DESIGN.md's original plan for this was a
separate Windows Task Scheduler job) is instead driven from *inside* this same
process: `create_app` starts an APScheduler `BackgroundScheduler` on the FastAPI
`lifespan`, polling `_check_schedule` every `schedule_check_interval_minutes`. That
scheduler runs jobs on its own worker thread pool — not the asyncio event loop this
app otherwise runs on — so `_check_schedule` calls `execute_run` directly rather than
via `asyncio.to_thread`, the same way a synchronous CLI invocation would. One process
covers both "review this in a browser" and "keep the schedule ticking", rather than
running a separate always-on scheduler service alongside it.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from .. import paths, scheduling, store
from ..adapters import adapter_for
from ..cli import (
    CommandError,
    _dedupe_baseline,
    execute_run,
    find_manufacturer,
    latest_export,
    resolve_ranges,
)
from ..diff.compare import LAYOUT_FIELDS
from ..output import generate_upload
from ..product_model import io
from ..registry import loader
from ..store.decisions import Action
from ..vehicle_class import VehicleClass
from . import choices
from .reviewers import load_reviewers

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
# `proposed_change` has no priority/kind column (diff.compare.FieldChange's
# priority/high_suspicion is computed, not persisted) — the templates recompute the
# "unusual" (layout) and "possible rollover" (year) badges from the field name alone
# via these globals rather than the DB carrying that classification.
_templates.env.globals["is_layout_field"] = lambda field: field in LAYOUT_FIELDS
_templates.env.globals["is_year_field"] = lambda field: field == "year"
_templates.env.globals["field_choices"] = choices.field_choices
_templates.env.globals["choice_label"] = choices.label_for
# A `MissingField` proposal (store.changes.persist_diff) always has `old_value ==
# new_value` and this exact snippet — same "match on the snippet text" trick as the
# archive/year-rollover proposals above, since there's no DB column for "why".
_templates.env.globals["is_missing_field"] = lambda change: (change.source_snippet or "").startswith(
    (store.MISSING_FIELD_SNIPPET, store.UNDETERMINED_FIELD_SNIPPET)
)


#: Everything is stored in UTC (`datetime.now(UTC)` throughout `store/`); this is
#: display-only. "Europe/London" rather than a fixed offset because it's the zone
#: DESIGN.md's UK host and reviewers are both in, and it self-adjusts for BST/GMT —
#: see TODO.md's note on why "GMT Standard Time" is the right Windows-side name for it.
_LOCAL_TZ = ZoneInfo("Europe/London")


def _format_datetime(value: str | None) -> str:
    """`2026-08-06T08:05:39.853663+00:00` (UTC) -> `2026-08-06 | 09:05:39` (local)."""
    if not value:
        return "—"
    local = datetime.fromisoformat(value).astimezone(_LOCAL_TZ)
    return local.strftime("%Y-%m-%d | %H:%M:%S")


def _format_datetime_short(value: str | None) -> str:
    """Same as `fmt_dt` but without seconds — the runs list doesn't need that precision."""
    if not value:
        return "—"
    local = datetime.fromisoformat(value).astimezone(_LOCAL_TZ)
    return local.strftime("%Y-%m-%d | %H:%M")


def _run_duration(run: store.Run) -> str | None:
    """`mm:ss` elapsed between `started_at` and `finished_at`, or `None` while running."""
    if not run.finished_at:
        return None
    started = datetime.fromisoformat(run.started_at)
    finished = datetime.fromisoformat(run.finished_at)
    total_seconds = int((finished - started).total_seconds())
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}m{seconds:02d}s"


_templates.env.filters["fmt_dt"] = _format_datetime
_templates.env.filters["fmt_dt_short"] = _format_datetime_short
_templates.env.globals["run_duration"] = _run_duration


def get_connection(request: Request) -> Iterator[sqlite3.Connection]:
    """Open a connection against this app's configured `db_path`, closed after use."""
    connection = store.connect(request.app.state.db_path)
    try:
        yield connection
    finally:
        connection.close()


ConnectionDep = Annotated[sqlite3.Connection, Depends(get_connection)]


def _run_or_404(connection: sqlite3.Connection, run_id: int) -> store.Run:
    try:
        return store.get_run(connection, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no run with id {run_id}") from None


def check_schedule(app: FastAPI) -> list[scheduling.ScheduleEntry]:
    """One scheduler tick: trigger every schedule entry that's due right now.

    Re-reads `schedule.csv` and the manufacturer registry from disk on every call, so
    an edit to either takes effect on the next tick with no restart needed. Runs
    `execute_run` synchronously, the same pipeline `/trigger` and the CLI's `fmlv run`
    use, just with `trigger="scheduled"` and nothing waiting on the result — called
    from the APScheduler job `create_app` registers, and directly from tests that want
    to exercise a tick without waiting on the real interval.
    """
    registry_result = loader.load(app.state.registry_path)
    by_id = {m.manufacturer_id: m for m in registry_result.manufacturers}
    schedule_result = scheduling.load(app.state.schedule_path)

    connection = store.connect(app.state.db_path)
    try:
        triggered: list[scheduling.ScheduleEntry] = []
        for entry in schedule_result.entries:
            if not entry.enabled:
                continue
            manufacturer = by_id.get(entry.manufacturer_id)
            if manufacturer is None:
                continue
            adapter = adapter_for(manufacturer.fmlv_manufacturer)
            if adapter is None:
                continue

            status = scheduling.describe(entry, adapter=adapter, connection=connection)
            if status.error or not status.is_due:
                continue
            if scheduling.has_run_in_progress(
                connection, manufacturer_id=manufacturer.manufacturer_id
            ):
                continue

            collect_kwargs: dict[str, object] = {}
            if entry.ranges:
                collect_kwargs["ranges"] = resolve_ranges(adapter, entry.ranges)

            def _on_progress(message: str, schedule_id: str = entry.schedule_id) -> None:
                print(f"[schedule:{schedule_id}] {message}")

            try:
                execute_run(
                    manufacturer=manufacturer,
                    adapter=adapter,
                    refresh_export=True,
                    data_root=app.state.data_root,
                    trigger="scheduled",
                    collect_kwargs=collect_kwargs,
                    on_progress=_on_progress,
                )
            except Exception as exc:  # noqa: BLE001 — execute_run already records this against the run
                print(f"[schedule:{entry.schedule_id}] failed: {type(exc).__name__}: {exc}")
            triggered.append(entry)
        return triggered
    finally:
        connection.close()


def create_app(
    db_path: Path,
    *,
    reviewers_path: Path | None = None,
    registry_path: Path | None = None,
    schedule_path: Path | None = None,
    enable_scheduler: bool = True,
    schedule_check_interval_minutes: int = 1,
) -> FastAPI:
    """Build the review app against the SQLite store at `db_path`.

    `reviewers_path`, `registry_path` and `schedule_path` default to the standard
    `config/` layout (`paths.py`) — independent of where `db_path` lives — but can be
    overridden, the same way tests point `db_path` at a throwaway file. If
    `reviewers_path` resolves to a file that doesn't exist, the reviewer dropdown is
    empty and decisions are never gated by name — the behaviour before reviewers.csv
    existed, so a test or a dev checkout without the file still works.

    `enable_scheduler=False` builds the app without starting the background scheduler
    at all — for tests that exercise `/schedules` or the manual `/trigger` flow and
    don't want a real `execute_run` firing on a timer underneath them. Tests that do
    want to exercise a tick call `check_schedule(app)` directly rather than waiting on
    the real interval.
    """
    data_root = db_path.parent
    reviewers_file = reviewers_path or paths.reviewers_path()
    registry_file = registry_path or paths.registry_path()
    schedule_file = schedule_path or paths.schedule_path()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = BackgroundScheduler()
        if enable_scheduler:
            scheduler.add_job(
                lambda: check_schedule(app),
                "interval",
                minutes=schedule_check_interval_minutes,
            )
            scheduler.start()
        app.state.scheduler = scheduler
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="FMLV Automated Data Ingestion", lifespan=lifespan)
    app.state.db_path = db_path
    app.state.data_root = data_root
    app.state.registry_path = registry_file
    app.state.schedule_path = schedule_file
    app.state.reviewers = load_reviewers(reviewers_file)
    app.state.reviewer_names_lower = {r.name.lower() for r in app.state.reviewers}
    # Holds references to in-flight background run tasks so they aren't garbage
    # collected mid-run — `asyncio` only keeps a weak reference to a task otherwise.
    app.state.background_tasks = set()

    def _load_registry() -> tuple[list, list]:
        """Manufacturers with an adapter, and any registry load errors to show."""
        result = loader.load(app.state.registry_path)
        errors = [issue.message for issue in result.issues if issue.severity == "error"]
        runnable = [m for m in result.manufacturers if adapter_for(m.fmlv_manufacturer)]
        return runnable, errors

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return _templates.TemplateResponse(request, "home.html", {})

    _RUN_STATUSES = ("running", "succeeded", "failed")

    @app.get("/runs", response_class=HTMLResponse)
    def run_list(
        request: Request,
        connection: ConnectionDep,
        limit: str = "10",
        manufacturer_id: str = "",
        status: str | None = None,
        start_date: str = "",
        vehicle_class: str = "",
    ) -> HTMLResponse:
        if status not in _RUN_STATUSES:
            status = None  # an unknown/empty value means "all statuses", not an error

        # Same "cleared means all" treatment as `status`: an empty or unrecognised value
        # is not an error, it means the reviewer isn't narrowing by product area.
        try:
            vehicle_class_filter: VehicleClass | None = (
                VehicleClass(vehicle_class) if vehicle_class else None
            )
        except ValueError:
            vehicle_class_filter = None

        # Plain str params (like `limit`) rather than `int | None`/`date | None`,
        # deliberately: the filter form's "cleared" state submits an empty string for
        # each, which FastAPI would reject outright as an invalid int/date before this
        # handler ever ran.
        try:
            manufacturer_id_filter: int | None = int(manufacturer_id) if manufacturer_id else None
        except ValueError:
            manufacturer_id_filter = None

        try:
            start_date_filter: date | None = date.fromisoformat(start_date) if start_date else None
        except ValueError:
            start_date_filter = None

        runs = store.list_runs(
            connection,
            manufacturer_id=manufacturer_id_filter,
            status=status,
            vehicle_class=vehicle_class_filter,
        )
        if start_date_filter is not None:
            # Filtered here rather than in the SQL `store.list_runs` runs on, against
            # the *local* calendar date — matching what the "Started" column actually
            # shows a reviewer (`_format_datetime_short`, Europe/London) rather than
            # the UTC date `started_at` is stored in, which would occasionally disagree
            # with the displayed date near midnight.
            runs = [
                run
                for run in runs
                if datetime.fromisoformat(run.started_at).astimezone(_LOCAL_TZ).date()
                == start_date_filter
            ]
        if limit != "all":
            try:
                runs = runs[: int(limit)]
            except ValueError:
                limit = "10"
                runs = runs[:10]
        # Only a succeeded run has a change queue worth summarising — a running or
        # failed run has no proposed_change rows yet (persist_diff runs at the very
        # end), so skip the query rather than show a misleading "0 pending".
        review_summaries = {
            run.id: store.run_review_summary(connection, run.id)
            for run in runs
            if run.status == "succeeded"
        }
        return _templates.TemplateResponse(
            request,
            "runs.html",
            {
                "runs": runs,
                "review_summaries": review_summaries,
                "limit": limit,
                "manufacturers": store.list_run_manufacturers(connection),
                "selected_manufacturer_id": manufacturer_id_filter,
                "selected_status": status,
                "selected_start_date": start_date_filter.isoformat() if start_date_filter else "",
                "vehicle_classes": list(VehicleClass),
                "selected_vehicle_class": (
                    vehicle_class_filter.value if vehicle_class_filter else ""
                ),
            },
        )

    @app.get("/schedules", response_class=HTMLResponse)
    def schedule_list(request: Request, connection: ConnectionDep) -> HTMLResponse:
        registry_result = loader.load(app.state.registry_path)
        registry_by_id = {m.manufacturer_id: m for m in registry_result.manufacturers}

        schedule_result = scheduling.load(app.state.schedule_path)
        schedule_errors = [
            issue.message for issue in schedule_result.issues if issue.severity == "error"
        ]

        rows = []
        for entry in schedule_result.entries:
            manufacturer = registry_by_id.get(entry.manufacturer_id)
            display_name = (
                (manufacturer.fmlv_display_name or manufacturer.fmlv_manufacturer)
                if manufacturer
                else f"manufacturer_id {entry.manufacturer_id}"
            )
            adapter = adapter_for(manufacturer.fmlv_manufacturer) if manufacturer else None

            if manufacturer is None:
                error = f"no manufacturer_id {entry.manufacturer_id} in the registry"
                status = None
            elif adapter is None:
                error = f"no adapter written for {manufacturer.fmlv_manufacturer!r} yet"
                status = None
            else:
                status = scheduling.describe(entry, adapter=adapter, connection=connection)
                error = status.error

            rows.append(
                {
                    "entry": entry,
                    "manufacturer_name": display_name,
                    "range_display": ", ".join(entry.ranges) if entry.ranges else "All ranges",
                    "frequency_display": (
                        f"every {entry.frequency_value} "
                        f"{entry.frequency_unit.value[:-1] if entry.frequency_value == 1 else entry.frequency_unit.value}"
                    ),
                    "last_triggered_at": status.last_triggered_at.isoformat()
                    if status and status.last_triggered_at
                    else None,
                    "next_due_at": status.next_due_at.isoformat()
                    if status and status.next_due_at
                    else None,
                    "is_due": bool(status and status.is_due),
                    "error": error,
                }
            )

        return _templates.TemplateResponse(
            request,
            "schedules.html",
            {
                "rows": rows,
                "registry_errors": [
                    issue.message
                    for issue in registry_result.issues
                    if issue.severity == "error"
                ],
                "schedule_errors": schedule_errors,
            },
        )

    @app.get("/trigger", response_class=HTMLResponse)
    def trigger_form(request: Request) -> HTMLResponse:
        manufacturers, errors = _load_registry()
        return _templates.TemplateResponse(
            request,
            "trigger.html",
            {"manufacturers": manufacturers, "registry_errors": errors, "error": None},
        )

    @app.post("/trigger", response_class=HTMLResponse)
    async def trigger_submit(
        request: Request,
        manufacturer_name: str = Form(...),
        range_name: str = Form(""),
    ) -> HTMLResponse:
        manufacturers, registry_errors = _load_registry()

        def render_error(message: str) -> HTMLResponse:
            return _templates.TemplateResponse(
                request,
                "trigger.html",
                {
                    "manufacturers": manufacturers,
                    "registry_errors": registry_errors,
                    "error": message,
                    "submitted_manufacturer": manufacturer_name,
                    "submitted_range": range_name,
                },
                status_code=422,
            )

        try:
            manufacturer = find_manufacturer(manufacturers, manufacturer_name)
            adapter = adapter_for(manufacturer.fmlv_manufacturer)
            if adapter is None:  # pragma: no cover — _load_registry already filters these out
                msg = f"no adapter written for {manufacturer.fmlv_manufacturer!r} yet"
                raise CommandError(msg)

            collect_kwargs: dict[str, object] = {}
            range_name = range_name.strip()
            if range_name:
                collect_kwargs["ranges"] = resolve_ranges(adapter, [range_name])
        except CommandError as exc:
            return render_error(str(exc))

        run_box: dict[str, store.Run] = {}
        started = threading.Event()

        def on_run_started(run: store.Run) -> None:
            run_box["run"] = run
            started.set()

        # `refresh_export=True`: a reviewer triggering a run expects it to check
        # against the *current* FMLV data, not whichever export happens to already be
        # on disk — see `execute_run`'s docstring. This downloads a fresh one (the
        # equivalent of `fmlv fetch-export`) before diffing, inside the background
        # thread since it needs a real NCC login and can take a while; a run that
        # fails here (bad credentials, no ncc_supplier_name) is recorded as a failed
        # run like any other failure, and shows up the same way on the run's page.
        task = asyncio.create_task(
            asyncio.to_thread(
                execute_run,
                manufacturer=manufacturer,
                adapter=adapter,
                refresh_export=True,
                data_root=app.state.data_root,
                trigger="manual",
                collect_kwargs=collect_kwargs,
                on_run_started=on_run_started,
            )
        )
        app.state.background_tasks.add(task)
        task.add_done_callback(app.state.background_tasks.discard)

        await asyncio.to_thread(started.wait, 10)
        if "run" not in run_box:
            return render_error(
                "The run did not start within 10 seconds — check the server logs."
            )
        return RedirectResponse(f"/runs/{run_box['run'].id}", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: int, connection: ConnectionDep) -> HTMLResponse:
        run = _run_or_404(connection, run_id)
        if run.status == "running":
            return _templates.TemplateResponse(request, "run_in_progress.html", {"run": run})

        queue = store.list_change_queue(connection, run_id)
        pending = [entry for entry in queue if entry.decision is None]
        decided = [entry for entry in queue if entry.decision is not None]
        disappearance_notices = store.list_disappearance_notices(connection, run_id)
        return _templates.TemplateResponse(
            request,
            "run_detail.html",
            {
                "run": run,
                "pending": pending,
                "decided": decided,
                "disappearance_notices": disappearance_notices,
                "reviewers": app.state.reviewers,
            },
        )

    @app.post("/runs/{run_id}/generate-upload")
    def generate_upload_route(run_id: int, connection: ConnectionDep) -> JSONResponse:
        """Build the upload CSV from whatever has been decided on this run so far.

        A deliberately separate action from triggering a run (`/trigger`) — the CSV
        should only be produced once a reviewer chooses to, not automatically the
        moment a run finishes, so it always reflects a human's actual decisions.

        Returns JSON rather than a page: both the runs list and the run detail page
        call this without navigating away, showing the result in a floating banner
        instead (`base.html`'s `generateUpload()`/`showToast()`).
        """
        run = _run_or_404(connection, run_id)
        if run.status != "succeeded":
            return JSONResponse(
                {"ok": False, "error": f"run #{run.id} is {run.status!r}, not 'succeeded'."},
                status_code=409,
            )

        try:
            registry_result = loader.load(app.state.registry_path)
            manufacturer = find_manufacturer(
                registry_result.manufacturers, str(run.manufacturer_id)
            )
            export_path = latest_export(
                root=app.state.data_root,
                manufacturer_id=manufacturer.manufacturer_id,
                manufacturer_name=manufacturer.fmlv_manufacturer,
            )
        except CommandError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)

        read = io.read_export(export_path)
        baseline = _dedupe_baseline(
            motorhome
            for motorhome in read.motorhomes
            if motorhome.manufacturer == manufacturer.fmlv_manufacturer
            and not motorhome.archived
        )
        result = generate_upload(
            connection,
            run_id=run.id,
            manufacturer=manufacturer,
            baseline=baseline,
            path=paths.upload_csv_path(
                run.id, vehicle_class=run.vehicle_class, root=app.state.data_root
            ),
        )

        # No folder/file:// link — Chrome (and most browsers) blocks navigation to
        # local file:// URIs from a served page, so a clickable "open Explorer" link
        # doesn't reliably work. The filename (shown as plain text) plus this app's
        # own download route is the option that works regardless of which machine the
        # reviewer's browser is on.
        return JSONResponse(
            {
                "ok": True,
                "path": str(result.path),
                "filename": result.path.name,
                "count": len(result.motorhomes),
                "has_errors": result.has_errors,
                "issues": [f"{issue.severity}: {issue.message}" for issue in result.issues],
                "download_url": f"/runs/{run.id}/uploads/{result.path.name}",
                "issues_filename": result.issues_path.name if result.issues_path else None,
                "issues_download_url": (
                    f"/runs/{run.id}/uploads/{result.issues_path.name}"
                    if result.issues_path
                    else None
                ),
            }
        )

    @app.get("/runs/{run_id}/uploads/{filename}")
    def download_upload(run_id: int, filename: str) -> FileResponse:
        """Download one previously generated upload CSV, or its issues text file, for this run.

        `filename` must be exactly one `paths.upload_csv_path`/`paths.upload_issues_path`
        produced for this run (checked by prefix, and that it resolves inside
        `uploads_dir` with no path separators) — each generation gets its own
        timestamped file, so there can be more than one for a given run.
        """
        if "/" in filename or "\\" in filename or not filename.startswith(f"run{run_id}_"):
            raise HTTPException(status_code=404, detail="upload CSV not found")
        path = paths.uploads_dir(root=app.state.data_root) / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="upload CSV not found")
        media_type = "text/plain" if filename.endswith(".txt") else "text/csv"
        return FileResponse(path, filename=filename, media_type=media_type)

    @app.post("/runs/{run_id}/changes/{change_id}/decide", response_class=HTMLResponse)
    def decide(
        request: Request,
        run_id: int,
        change_id: int,
        connection: ConnectionDep,
        action: Action = Form(...),
        corrected_value: str = Form(""),
        reviewer_name: str = Form(""),
    ) -> HTMLResponse:
        run = _run_or_404(connection, run_id)
        try:
            change = store.get_proposed_change(connection, change_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"no proposed change with id {change_id}"
            ) from None

        corrected_value = corrected_value.strip()
        reviewer_name = reviewer_name.strip()
        error = None
        selectable = choices.field_choices(change.field)
        known_reviewers: set[str] = app.state.reviewer_names_lower
        if known_reviewers and reviewer_name.lower() not in known_reviewers:
            error = "Select your name from the reviewer list before deciding."
        elif action == "correct" and not corrected_value:
            error = (
                "Choose a value before submitting."
                if selectable
                else "Enter a corrected value before submitting a correction."
            )
        elif (
            action == "correct"
            and selectable
            and not choices.is_valid_choice(change.field, corrected_value)
        ):
            # A `<select>` cannot submit this, but the endpoint is a plain POST and an
            # unrecognised value would only fail later, in `build.apply_field`, at upload.
            error = f"{corrected_value!r} is not one of the values {change.field} accepts."
        else:
            store.record_decision(
                connection,
                proposed_change_id=change_id,
                action=action,
                corrected_value=corrected_value if action == "correct" else None,
                decided_by=reviewer_name or None,
            )

        entry = next(
            e for e in store.list_change_queue(connection, run_id) if e.change.id == change_id
        )
        return _templates.TemplateResponse(
            request,
            "partials/change_row.html",
            {
                "run": run,
                "entry": entry,
                "error": error,
                "reviewers": app.state.reviewers,
            },
        )

    @app.post(
        "/runs/{run_id}/products/{product_id}/accept-all", response_class=HTMLResponse
    )
    def accept_all(
        request: Request,
        run_id: int,
        product_id: int,
        connection: ConnectionDep,
        reviewer_name: str = Form(""),
    ) -> HTMLResponse:
        """Accept every still-pending change for one product in one click.

        Only the changes that were pending *when the button was pressed* are decided,
        but the whole product's group (decided and freshly-decided alike) is
        re-rendered, so the "Accept all" button — which `product_group.html` only
        shows while something in the group is still pending — disappears the moment
        nothing is left to decide, rather than needing a second click to catch up.
        """
        run = _run_or_404(connection, run_id)
        queue = store.list_change_queue(connection, run_id)
        target_entries = [e for e in queue if e.product.id == product_id and e.decision is None]
        if not target_entries and not any(e.product.id == product_id for e in queue):
            raise HTTPException(
                status_code=404, detail=f"no product {product_id} in run {run_id}"
            )

        reviewer_name = reviewer_name.strip()
        error = None
        known_reviewers: set[str] = app.state.reviewer_names_lower
        if known_reviewers and reviewer_name.lower() not in known_reviewers:
            error = "Select your name from the reviewer list before deciding."
        else:
            for entry in target_entries:
                store.record_decision(
                    connection,
                    proposed_change_id=entry.change.id,
                    action="accept",
                    decided_by=reviewer_name or None,
                )

        # The whole product's group, not just the entries just decided — so a second
        # render (e.g. the button re-appearing before an htmx swap lands) still shows
        # every row for the product rather than only the ones this request touched.
        queue_after = store.list_change_queue(connection, run_id)
        entries = [e for e in queue_after if e.product.id == product_id]
        product = entries[0].product
        return _templates.TemplateResponse(
            request,
            "partials/product_group.html",
            {
                "run": run,
                "product": product,
                "entries": entries,
                "error": error,
                "reviewers": app.state.reviewers,
            },
        )

    return app
