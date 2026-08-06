"""Tests for the NCC login/download flow, against local fixtures (no real network).

Requires Chromium to be installed once via `uv run playwright install chromium` (see
the note in `tests/fetch/test_browser.py`). The fixtures mirror the real Nova admin
site's selectors as surveyed 2026-08-06 (`fetch/ncc.py`'s module docstring) — a login
form, then an actions-dropdown → modal → zip-download flow on a stand-in
`ncc_products.html`, rather than a single download link.
"""

from __future__ import annotations

import threading
import zipfile
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
    NccExportError,
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


@pytest.fixture
def config(fixture_server: str) -> NccSiteConfig:
    return NccSiteConfig(
        login_url=f"{fixture_server}/ncc_login.html",
        products_url=f"{fixture_server}/ncc_products.html",
    )


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


def test_download_export_logs_in_selects_the_supplier_and_extracts_the_xlsx(
    config: NccSiteConfig, tmp_path: Path
) -> None:
    credentials = NccCredentials(email="reviewer@example.com", password="secret")
    dest_path = tmp_path / "downloads" / "motorhome-campervans.xlsx"

    result_path = download_export(credentials, "Test Motorhomes", dest_path, config=config)

    assert result_path == dest_path
    assert dest_path.exists()
    with zipfile.ZipFile(FIXTURES_DIR / "ncc_export.zip") as archive:
        expected = archive.read("motorhome-campervans.xlsx")
    assert dest_path.read_bytes() == expected
    # The zip is a scratch download, not something a caller should have to clean up.
    assert not dest_path.with_suffix(".zip").exists()


def test_download_export_raises_a_clear_error_when_the_xlsx_is_missing(
    config: NccSiteConfig, tmp_path: Path
) -> None:
    credentials = NccCredentials(email="reviewer@example.com", password="secret")
    dest_path = tmp_path / "downloads" / "motorhome-campervans.xlsx"
    bad_config = NccSiteConfig(
        login_url=config.login_url,
        products_url=config.products_url,
        motorhome_export_filename="does-not-exist.xlsx",
    )

    with pytest.raises(NccExportError, match="does-not-exist.xlsx"):
        download_export(credentials, "Test Motorhomes", dest_path, config=bad_config)
