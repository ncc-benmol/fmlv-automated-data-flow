"""Headless-browser fetching for JS-rendered manufacturer sites.

`http.Fetcher` is cheaper and should always be tried first — reach for this only when
a manufacturer's registry `needs_javascript` flag says the spec data isn't present in
the plain HTML response (see DESIGN.md §6.1 and §8.1 on keeping running cost down).
Renders the page, then snapshots the resulting HTML through the same `FetchResult`
shape as a plain HTTP fetch, so downstream code doesn't need to care which one ran.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .http import USER_AGENT, FetchResult, content_hash, snapshot_filename

#: Playwright's `wait_until` states, from least to most conservative. "networkidle"
#: waits for network activity to quiet down — the safest default for a spec page
#: that fetches its data asynchronously, at the cost of being the slowest.
DEFAULT_WAIT_UNTIL = "networkidle"

#: A `networkidle` wait can time out on a page that's actually fine — a chatty
#: analytics/chat-widget script that never goes quiet, or a slow moment on the
#: site — so a couple of retries with backoff clears most of these without
#: failing the whole run. Kept small: a page that's *genuinely* down should still
#: surface quickly rather than stall a run for minutes.
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 3.0


class BrowserFetcher:
    """Renders a page with headless Chromium and snapshots the resulting HTML.

    One instance holds one browser process for its lifetime — construct it once per
    run (or once per manufacturer needing it) and close it when done, rather than
    launching a fresh browser per page.
    """

    def __init__(
        self,
        snapshot_dir: Path | str,
        *,
        wait_until: str = DEFAULT_WAIT_UNTIL,
        user_agent: str = USER_AGENT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.wait_until = wait_until
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = _sleep
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()

    def close(self) -> None:
        self._browser.close()
        self._playwright.stop()

    def __enter__(self) -> BrowserFetcher:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _goto(self, page: object, url: str) -> object:
        """`page.goto`, retrying a `wait_until` timeout with backoff.

        A timeout here is usually the page being momentarily slow, or a background
        script (analytics, chat widget) that keeps `networkidle` from ever firing —
        not a dead site. Retried the same way `http.Fetcher.fetch` retries transient
        HTTP failures. A page that's genuinely unreachable will keep timing out and
        still surface after `max_retries`, just not on the first attempt.
        """
        last_error: PlaywrightTimeoutError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return page.goto(url, wait_until=self.wait_until)  # type: ignore[attr-defined]
            except PlaywrightTimeoutError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep(self.backoff_seconds * (2**attempt))
        assert last_error is not None
        raise last_error

    def fetch(self, url: str, *, previous_hash: str | None = None) -> FetchResult:
        """Render a page and snapshot the DOM's final HTML.

        Retries a `wait_until` timeout (see `_goto`) but nothing else — a page that
        fails outright, or a `wait_until` that's structurally too strict for this
        page, is better surfaced immediately than retried blind.
        """
        page = self._browser.new_page(user_agent=self.user_agent)
        try:
            response = self._goto(page, url)
            html = page.content()
            status_code = response.status if response is not None else 0  # type: ignore[attr-defined]
        finally:
            page.close()

        return self._snapshot_html(url, html, status_code, previous_hash=previous_hash)

    def fetch_with_capture(
        self,
        url: str,
        *,
        capture_url_contains: str,
        scroll: bool = False,
        scroll_steps: int = 20,
        scroll_pixels: int = 2000,
        scroll_pause_ms: int = 400,
        settle_ms: int = 2000,
    ) -> tuple[FetchResult, list[FetchResult]]:
        """Render a page and also snapshot any XHR/fetch response matching a URL.

        Some catalogue pages (Adria's is the first one found to do this) render
        empty on load and only fetch their real data once a component scrolls into
        view — an intersection-observer-triggered AJAX call, not present in either
        a plain HTTP fetch or a `fetch()` that only waits for `networkidle`. Setting
        `scroll=True` scrolls the page in steps to trigger that kind of lazy load;
        every response whose URL contains `capture_url_contains` is snapshotted
        exactly like any other fetch, so it is just as reproducible and diffable
        (DESIGN.md §6.6) even though it never went through `Fetcher` directly.
        """
        captured: list[tuple[str, int, str | None, bytes]] = []

        def on_response(response: object) -> None:
            if capture_url_contains not in response.url:  # type: ignore[attr-defined]
                return
            try:
                body = response.body()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — a response we can't read is just skipped
                return
            captured.append(
                (
                    response.url,  # type: ignore[attr-defined]
                    response.status,  # type: ignore[attr-defined]
                    response.headers.get("content-type"),  # type: ignore[attr-defined]
                    body,
                )
            )

        page = self._browser.new_page(user_agent=self.user_agent)
        page.on("response", on_response)
        try:
            response = self._goto(page, url)
            if scroll:
                self._scroll_to_bottom(
                    page,
                    steps=scroll_steps,
                    pixels=scroll_pixels,
                    pause_ms=scroll_pause_ms,
                )
            page.wait_for_timeout(settle_ms)
            html = page.content()
            status_code = response.status if response is not None else 0  # type: ignore[attr-defined]
        finally:
            page.close()

        page_result = self._snapshot_html(url, html, status_code)
        capture_results = [
            self._snapshot_bytes(captured_url, captured_status, content_type, body)
            for captured_url, captured_status, content_type, body in captured
        ]
        return page_result, capture_results

    @staticmethod
    def _scroll_to_bottom(page: object, *, steps: int, pixels: int, pause_ms: int) -> None:
        """Scroll down in fixed steps, triggering any intersection-observer lazy loads.

        Runs the full step count unconditionally rather than stopping once
        `scrollHeight` stops growing: that signal only means the page's *total*
        height is stable, which is true from the first step on a fixed-height page
        — it says nothing about whether we've scrolled far enough to bring a
        lazy-loaded component into view.
        """
        for _ in range(steps):
            page.mouse.wheel(0, pixels)  # type: ignore[attr-defined]
            page.wait_for_timeout(pause_ms)  # type: ignore[attr-defined]

    def _snapshot_html(
        self,
        url: str,
        html: str,
        status_code: int,
        *,
        previous_hash: str | None = None,
    ) -> FetchResult:
        content = html.encode("utf-8")
        digest = content_hash(content)
        filename = snapshot_filename(url, "text/html", digest)
        path = self.snapshot_dir / filename
        path.write_text(html, encoding="utf-8")

        return FetchResult(
            url=url,
            status_code=status_code,
            content_type="text/html",
            content_hash=digest,
            file_path=path,
            fetched_at=datetime.now(UTC).isoformat(),
            unchanged=(previous_hash is not None and previous_hash == digest),
        )

    def _snapshot_bytes(
        self, url: str, status_code: int, content_type: str | None, content: bytes
    ) -> FetchResult:
        digest = content_hash(content)
        filename = snapshot_filename(url, content_type, digest)
        path = self.snapshot_dir / filename
        path.write_bytes(content)

        return FetchResult(
            url=url,
            status_code=status_code,
            content_type=content_type,
            content_hash=digest,
            file_path=path,
            fetched_at=datetime.now(UTC).isoformat(),
        )
