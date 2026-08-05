# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.115",
#     "uvicorn>=0.30",
# ]
# ///
"""Deployment smoke test for the Windows Server VM (DESIGN.md §8.3).

Deliberately trivial: one service, no FMLV logic, no database, no network calls out.
Its only job is to prove the host can run and serve a Python web service before the
real application is deployed to it.

Standalone by design. The PEP 723 block above means `uv run smoke_service.py` fetches
its own dependencies, so this also exercises uv and outbound access to PyPI without
needing the project itself to install cleanly first.

    uv run deploy/smoketest/smoke_service.py            # localhost:8099
    uv run deploy/smoketest/smoke_service.py --host 0.0.0.0 --port 8099

Endpoints:
    GET /          human-readable page, for eyeballing in a browser
    GET /api/time  JSON: the current date and time, plus enough host detail to prove
                   *which* machine answered and which account it ran as
    GET /healthz   {"status": "ok"} — the cheap check for scripts and monitoring
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import os
import platform
import socket
import sys

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

STARTED_AT = dt.datetime.now(dt.timezone.utc)

app = FastAPI(title="FMLV deployment smoke test", version="1.0.0")


def _host_facts() -> dict[str, object]:
    """Identify the machine and account that answered, not just the time.

    Answering "what time is it" from the wrong host would look like success, so the
    hostname and account are part of the payload rather than a nicety.
    """
    now_local = dt.datetime.now().astimezone()
    return {
        "date": now_local.strftime("%Y-%m-%d"),
        "time": now_local.strftime("%H:%M:%S"),
        "timezone": str(now_local.tzinfo),
        "datetime_local": now_local.isoformat(),
        "datetime_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": sys.version.split()[0],
        "running_as": _current_user(),
        "cwd": os.getcwd(),
        "uptime_seconds": round(
            (dt.datetime.now(dt.timezone.utc) - STARTED_AT).total_seconds(), 1
        ),
        "service_started_utc": STARTED_AT.isoformat(),
    }


def _current_user() -> str:
    """`getpass.getuser()` raises rather than returns when a service has no USERNAME set."""
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - depends on the service account's environment
        return "unknown"


@app.get("/api/time")
def api_time() -> dict[str, object]:
    return _host_facts()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    facts = _host_facts()
    rows = "\n".join(
        f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in facts.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FMLV deployment smoke test</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 3rem auto; max-width: 44rem;
            padding: 0 1rem; line-height: 1.5; }}
    h1 {{ font-size: 1.4rem; }}
    .ok {{ color: #0a7f3f; font-weight: 600; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1.5rem; }}
    th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd;
              vertical-align: top; }}
    th {{ width: 12rem; font-weight: 600; color: #444; }}
    td {{ font-family: ui-monospace, Consolas, monospace; font-size: 0.9rem;
          word-break: break-all; }}
    p.note {{ color: #666; font-size: 0.9rem; margin-top: 2rem; }}
  </style>
</head>
<body>
  <h1>FMLV deployment smoke test <span class="ok">&#10003; responding</span></h1>
  <p>The current date and time on <strong>{facts["hostname"]}</strong>:
     <strong>{facts["date"]} {facts["time"]}</strong></p>
  <table>{rows}</table>
  <p class="note">This service exists only to prove the host can run and serve a Python
     web service (DESIGN.md &sect;8.3). It contains no FMLV logic.
     JSON version: <a href="/api/time">/api/time</a>.</p>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind. Use 0.0.0.0 on the VM so another machine can reach it.",
    )
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
