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
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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


def _unlaunched_fetcher(*, max_retries: int, sleeps: list[float]) -> BrowserFetcher:
    """A `BrowserFetcher` with `_goto`'s dependencies set but no real browser launched.

    `_goto` only touches `max_retries`/`backoff_seconds`/`_sleep`/`wait_until`, so
    exercising its retry loop doesn't need Playwright running at all — avoids the cost
    (and the real 30s-scale timeouts) of driving an actual browser through this path.
    """
    fetcher = object.__new__(BrowserFetcher)
    fetcher.max_retries = max_retries
    fetcher.backoff_seconds = 3.0
    fetcher.wait_until = "networkidle"
    fetcher._sleep = sleeps.append  # type: ignore[attr-defined]
    return fetcher


class _FlakyPage:
    """Fakes `page.goto`, raising a timeout `failures` times before succeeding."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def goto(self, url: str, *, wait_until: str) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise PlaywrightTimeoutError(f"Page.goto: Timeout exceeded navigating to {url!r}")
        return "ok"


def test_goto_retries_a_timeout_and_succeeds() -> None:
    sleeps: list[float] = []
    fetcher = _unlaunched_fetcher(max_retries=2, sleeps=sleeps)
    page = _FlakyPage(failures=1)

    result = fetcher._goto(page, "https://example.invalid")

    assert result == "ok"
    assert page.calls == 2
    assert sleeps == [3.0]  # one retry, backoff for attempt 0


def test_goto_backs_off_between_retries() -> None:
    sleeps: list[float] = []
    fetcher = _unlaunched_fetcher(max_retries=2, sleeps=sleeps)
    page = _FlakyPage(failures=2)

    fetcher._goto(page, "https://example.invalid")

    assert sleeps == [3.0, 6.0]  # backoff_seconds * 2**attempt for attempts 0, 1


def test_goto_raises_after_exhausting_retries() -> None:
    sleeps: list[float] = []
    fetcher = _unlaunched_fetcher(max_retries=2, sleeps=sleeps)
    page = _FlakyPage(failures=3)

    with pytest.raises(PlaywrightTimeoutError):
        fetcher._goto(page, "https://example.invalid")

    assert page.calls == 3
    assert len(sleeps) == 2  # slept between attempts, not after the final failure


def test_fetch_with_capture_finds_nothing_without_scrolling(
    browser_fetcher: BrowserFetcher, fixture_server: str
) -> None:
    _page_result, captured = browser_fetcher.fetch_with_capture(
        f"{fixture_server}/lazy_load.html",
        capture_url_contains="data.json",
        scroll=False,
    )

    assert captured == []
