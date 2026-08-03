"""Headless-browser fetching for JS-rendered manufacturer sites.

`http.Fetcher` is cheaper and should always be tried first — reach for this only when
a manufacturer's registry `needs_javascript` flag says the spec data isn't present in
the plain HTML response (see DESIGN.md §6.1 and §8.1 on keeping running cost down).
Renders the page, then snapshots the resulting HTML through the same `FetchResult`
shape as a plain HTTP fetch, so downstream code doesn't need to care which one ran.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from playwright.sync_api import sync_playwright

from .http import USER_AGENT, FetchResult, content_hash, snapshot_filename

#: Playwright's `wait_until` states, from least to most conservative. "networkidle"
#: waits for network activity to quiet down — the safest default for a spec page
#: that fetches its data asynchronously, at the cost of being the slowest.
DEFAULT_WAIT_UNTIL = "networkidle"


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
    ) -> None:
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.wait_until = wait_until
        self.user_agent = user_agent
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

    def fetch(self, url: str, *, previous_hash: str | None = None) -> FetchResult:
        """Render a page and snapshot the DOM's final HTML.

        Unlike `http.Fetcher`, there is no retry loop here — a page that fails to
        render is more likely a real site problem (or a `wait_until` that's too
        strict for this page) than a transient network blip, and is better surfaced
        immediately than retried blind.
        """
        page = self._browser.new_page(user_agent=self.user_agent)
        try:
            response = page.goto(url, wait_until=self.wait_until)
            html = page.content()
            status_code = response.status if response is not None else 0
        finally:
            page.close()

        content = html.encode("utf-8")
        digest = content_hash(content)
        filename = snapshot_filename(url, "text/html")
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
