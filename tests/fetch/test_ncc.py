"""Tests for the NCC login/download flow, against local fixtures (no real network).

Requires Chromium to be installed once via `uv run playwright install chromium` (see
the note in `tests/fetch/test_browser.py`).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.fetch.ncc import (
    CREDENTIALS_EMAIL_ENV,
    CREDENTIALS_PASSWORD_ENV,
    NccCredentials,
    NccCredentialsError,
    NccSiteConfig,
    download_export,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def fixture_server() -> Iterator[str]:
    """A local HTTP server over `fixtures/` standing in for the NCC site."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURES_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def test_credentials_from_env_reads_both_variables() -> None:
    credentials = NccCredentials.from_env(
        env={CREDENTIALS_EMAIL_ENV: "reviewer@example.com", CREDENTIALS_PASSWORD_ENV: "secret"}
    )

    assert credentials.email == "reviewer@example.com"
    assert credentials.password == "secret"


@pytest.mark.parametrize(
    "env",
    [
        {},
        {CREDENTIALS_EMAIL_ENV: "reviewer@example.com"},
        {CREDENTIALS_PASSWORD_ENV: "secret"},
    ],
)
def test_credentials_from_env_requires_both_variables(env: dict[str, str]) -> None:
    with pytest.raises(NccCredentialsError):
        NccCredentials.from_env(env=env)


def test_download_export_logs_in_and_saves_the_downloaded_file(
    fixture_server: str, tmp_path: Path
) -> None:
    config = NccSiteConfig(
        login_url=f"{fixture_server}/ncc_login.html",
        export_url=f"{fixture_server}/ncc_export.html",
    )
    credentials = NccCredentials(email="reviewer@example.com", password="secret")
    dest_path = tmp_path / "downloads" / "motorhome-campervans.csv"

    result_path = download_export(credentials, dest_path, config=config)

    assert result_path == dest_path
    assert dest_path.exists()
    assert dest_path.read_text(encoding="utf-8") == (FIXTURES_DIR / "ncc_export.csv").read_text(
        encoding="utf-8"
    )
