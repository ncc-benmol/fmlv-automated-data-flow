"""Tests for the Playwright-based fetcher, against a local fixture (no real network).

Requires Chromium to be installed once via `uv run playwright install chromium`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fmlv_automated_data_flow.fetch.browser import BrowserFetcher

FIXTURE = Path(__file__).parent / "fixtures" / "js_rendered.html"


@pytest.fixture(scope="module")
def browser_fetcher(tmp_path_factory: pytest.TempPathFactory) -> BrowserFetcher:
    snapshot_dir = tmp_path_factory.mktemp("browser-snapshots")
    with BrowserFetcher(snapshot_dir) as fetcher:
        yield fetcher


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
