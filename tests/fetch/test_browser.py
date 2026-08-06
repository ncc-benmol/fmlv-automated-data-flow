"""Tests for the Playwright-based fetcher, against a local fixture (no real network).

Requires Chromium to be installed once via `uv run playwright install chromium`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

from src.fetch.browser import BrowserFetcher

FIXTURE = Path(__file__).parent / "fixtures" / "js_rendered.html"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def browser_fetcher(tmp_path_factory: pytest.TempPathFactory) -> BrowserFetcher:
    snapshot_dir = tmp_path_factory.mktemp("browser-snapshots")
    with BrowserFetcher(snapshot_dir) as fetcher:
        yield fetcher


@pytest.fixture(scope="module")
def fixture_server() -> Iterator[str]:
    """A local HTTP server over `fixtures/`, needed so `fetch()` calls aren't blocked by
    the browser's same-origin policy the way they would be from a `file://` page."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURES_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def test_renders_javascript_before_snapshotting(browser_fetcher: BrowserFetcher) -> None:
    result = browser_fetcher.fetch(FIXTURE.as_uri())

    assert result.status_code == 200
    assert result.content_type == "text/html"
    html = result.file_path.read_text(encoding="utf-8")
    # The raw fixture says "not yet rendered" — the browser must have run the script.
    assert "rendered by JS" in html
    assert "not yet rendered" not in html


def test_previous_hash_match_marks_unchanged(browser_fetcher: BrowserFetcher) -> None:
    first = browser_fetcher.fetch(FIXTURE.as_uri())
    second = browser_fetcher.fetch(FIXTURE.as_uri(), previous_hash=first.content_hash)

    assert second.unchanged is True
    assert second.content_hash == first.content_hash


def test_fetch_with_capture_snapshots_a_scroll_triggered_xhr(
    browser_fetcher: BrowserFetcher, fixture_server: str
) -> None:
    page_result, captured = browser_fetcher.fetch_with_capture(
        f"{fixture_server}/lazy_load.html",
        capture_url_contains="data.json",
        scroll=True,
    )

    assert page_result.status_code == 200
    assert len(captured) == 1
    assert captured[0].status_code == 200
    assert captured[0].content_type == "application/json"
    assert captured[0].file_path.read_text(encoding="utf-8").strip() == '{"hello": "world"}'


def test_fetch_with_capture_finds_nothing_without_scrolling(
    browser_fetcher: BrowserFetcher, fixture_server: str
) -> None:
    _page_result, captured = browser_fetcher.fetch_with_capture(
        f"{fixture_server}/lazy_load.html",
        capture_url_contains="data.json",
        scroll=False,
    )

    assert captured == []
