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

#: Fraction of the viewport height one scroll step may cover. A step larger than the
#: viewport leaves *gaps* between rest positions, and an intersection observer watching
#: a short element never fires if the element falls in one — see `_scroll_to_bottom`.
#: A half-viewport step overlaps consecutive positions, so nothing is skipped.
SCROLL_STEP_VIEWPORT_FRACTION = 0.5


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
        scroll_steps: int = 60,
        scroll_pixels: int = 2000,
        scroll_pause_ms: int = 400,
        settle_ms: int = 2000,
    ) -> tuple[FetchResult, list[FetchResult]]:
        """Render a page and also snapshot any XHR/fetch response matching a URL.

        Some catalogue pages (Adria's is the first one found to do this) render
        empty on load and only fetch their real data once a component scrolls into
        view — an intersection-observer-triggered AJAX call, not present in either
        a plain HTTP fetch or a `fetch()` that only waits for `networkidle`. Setting
        `scroll=True` scrolls the page in overlapping steps to trigger that kind of
        lazy load — `scroll_steps` caps how many steps are taken and `scroll_pixels`
        caps how far each one goes, but a step is never allowed to exceed half a
        viewport whatever `scroll_pixels` says (see `_scroll_to_bottom`);
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
        """Scroll to the bottom in overlapping steps, triggering lazy loads on the way.

        **Every step is capped at half a viewport** (`SCROLL_STEP_VIEWPORT_FRACTION`),
        which is the whole point of this method and is not a tuning preference. A step
        bigger than the viewport tiles the page with *gaps*: an element shorter than the
        gap sits below the viewport at one rest position and above it at the next, is
        never on screen while the page is still, and its intersection observer never
        fires. That is not hypothetical — Adria's 60Y range pages returned zero captures
        under the previous 2000px step against a 720px viewport, because the element
        carrying `x-intersect` is 20px tall and landed in exactly such a gap. The same
        element on `/motorhomes/matrix` happened to land inside a rest position, so the
        bug looked like "those three pages are built differently" rather than a scroll
        defect. Overlapping steps make it impossible to skip anything.

        Stops on reaching the bottom rather than always running `steps` iterations,
        since the smaller step would otherwise make a full sweep several times slower.
        `steps` is now a **cap**, guarding against an infinite-scroll page — the
        distance actually needed comes from the document's own height, re-read each
        step so a page that grows as it loads is still followed to its new bottom.
        """
        viewport = page.viewport_size or {}  # type: ignore[attr-defined]
        viewport_height = viewport.get("height") or pixels
        step = max(1, min(pixels, int(viewport_height * SCROLL_STEP_VIEWPORT_FRACTION)))

        for _ in range(steps):
            page.mouse.wheel(0, step)  # type: ignore[attr-defined]
            page.wait_for_timeout(pause_ms)  # type: ignore[attr-defined]
            at_bottom = page.evaluate(  # type: ignore[attr-defined]
                "window.scrollY + window.innerHeight >= document.body.scrollHeight - 1"
            )
            if at_bottom:
                return

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
