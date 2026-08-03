"""The review app: FastAPI + HTMX, per DESIGN.md §6.3.

"Others will run and maintain this, not just the author, and reviewer time is the
real bottleneck" — so the app is deliberately small: a run list, a per-run change
queue grouped by product, and a per-field accept/reject/correct form that submits via
HTMX and swaps just that row back in, no client-side JavaScript of our own.

`create_app(db_path)` is a factory rather than a module-level app object so tests can
point it at a throwaway SQLite file. `get_connection` is a *module-level* dependency
(not a closure over `app`) reading `request.app.state.db_path`, deliberately — a
closure-based dependency defined inside `create_app` can't be resolved here: this
file uses `from __future__ import annotations`, which stringifies every annotation,
and FastAPI resolves those strings against each function's module globals, not an
enclosing function's locals. Every route opens its own connection and closes it at
the end of the request, sidestepping `sqlite3`'s one-thread-per-connection rule
without needing a long-lived connection pool at this scale.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from .. import store
from ..diff.compare import LAYOUT_FIELDS
from ..store.decisions import Action

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
# `proposed_change` has no priority/kind column (diff.compare.FieldChange's
# priority/high_suspicion is computed, not persisted) — the templates recompute the
# "unusual" (layout) and "possible rollover" (year) badges from the field name alone
# via these globals rather than the DB carrying that classification.
_templates.env.globals["is_layout_field"] = lambda field: field in LAYOUT_FIELDS
_templates.env.globals["is_year_field"] = lambda field: field == "year"


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


def create_app(db_path: Path) -> FastAPI:
    """Build the review app against the SQLite store at `db_path`."""
    app = FastAPI(title="FMLV review")
    app.state.db_path = db_path

    @app.get("/", response_class=HTMLResponse)
    def run_list(request: Request, connection: ConnectionDep) -> HTMLResponse:
        runs = store.list_runs(connection)
        return _templates.TemplateResponse(request, "runs.html", {"runs": runs})

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: int, connection: ConnectionDep) -> HTMLResponse:
        run = _run_or_404(connection, run_id)
        queue = store.list_change_queue(connection, run_id)
        pending = [entry for entry in queue if entry.decision is None]
        decided = [entry for entry in queue if entry.decision is not None]
        return _templates.TemplateResponse(
            request,
            "run_detail.html",
            {"run": run, "pending": pending, "decided": decided},
        )

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
            store.get_proposed_change(connection, change_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"no proposed change with id {change_id}"
            ) from None

        corrected_value = corrected_value.strip()
        error = None
        if action == "correct" and not corrected_value:
            error = "Enter a corrected value before submitting a correction."
        else:
            store.record_decision(
                connection,
                proposed_change_id=change_id,
                action=action,
                corrected_value=corrected_value if action == "correct" else None,
                decided_by=reviewer_name.strip() or None,
            )

        entry = next(
            e for e in store.list_change_queue(connection, run_id) if e.change.id == change_id
        )
        return _templates.TemplateResponse(
            request, "partials/change_row.html", {"run": run, "entry": entry, "error": error}
        )

    return app
