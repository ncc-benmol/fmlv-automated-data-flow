"""Tests for the HTTP fetcher: retries, politeness delay, snapshotting, hashing.

Uses `httpx.MockTransport` so nothing here makes a real network call, and a fake
clock so retry/politeness delays don't actually make the test suite slow.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from fmlv_automated_data_flow.fetch.http import Fetcher, content_hash


class FakeClock:
    """A controllable clock + sleep recorder, so tests don't actually wait."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_fetcher(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    clock: FakeClock | None = None,
    **kwargs: object,
) -> tuple[Fetcher, FakeClock]:
    clock = clock or FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    kwargs.setdefault("backoff_seconds", 1.0)
    kwargs.setdefault("politeness_delay_seconds", 1.0)
    fetcher = Fetcher(
        tmp_path,
        client=client,
        _monotonic=clock.monotonic,
        _sleep=clock.sleep,
        **kwargs,
    )
    return fetcher, clock


def test_successful_fetch_snapshots_content(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<html>hi</html>", headers={"content-type": "text/html"}
        )

    fetcher, _clock = make_fetcher(tmp_path, handler)
    result = fetcher.fetch("https://example.com/page")

    assert result.status_code == 200
    assert result.content_hash == content_hash(b"<html>hi</html>")
    assert result.file_path.exists()
    assert result.file_path.read_bytes() == b"<html>hi</html>"
    assert result.file_path.suffix == ".html"
    assert result.unchanged is False


def test_previous_hash_match_marks_unchanged(tmp_path: Path) -> None:
    content = b"same every time"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    fetcher, _clock = make_fetcher(tmp_path, handler)
    result = fetcher.fetch("https://example.com/page", previous_hash=content_hash(content))

    assert result.unchanged is True


def test_previous_hash_mismatch_marks_changed(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"new content")

    fetcher, _clock = make_fetcher(tmp_path, handler)
    result = fetcher.fetch("https://example.com/page", previous_hash="not-the-real-hash")

    assert result.unchanged is False


def test_retries_server_errors_then_succeeds(tmp_path: Path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"finally")

    fetcher, clock = make_fetcher(tmp_path, handler)
    result = fetcher.fetch("https://example.com/flaky")

    assert calls["count"] == 3
    assert result.status_code == 200
    assert result.file_path.read_bytes() == b"finally"
    assert len(clock.sleeps) == 2  # two retries, two backoff sleeps


def test_gives_up_after_max_retries_and_still_snapshots_the_failure(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"still down")

    fetcher, _clock = make_fetcher(tmp_path, handler, max_retries=2)
    result = fetcher.fetch("https://example.com/always-down")

    assert result.status_code == 503
    assert result.file_path.read_bytes() == b"still down"


def test_does_not_retry_a_plain_404(tmp_path: Path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, content=b"not found")

    fetcher, _clock = make_fetcher(tmp_path, handler)
    result = fetcher.fetch("https://example.com/missing")

    assert calls["count"] == 1
    assert result.status_code == 404


def test_honours_retry_after_header_on_429(tmp_path: Path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"retry-after": "5"})
        return httpx.Response(200, content=b"ok")

    fetcher, clock = make_fetcher(tmp_path, handler)
    fetcher.fetch("https://example.com/rate-limited")

    assert clock.sleeps[0] == 5.0


def test_enforces_politeness_delay_between_requests(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    fetcher, clock = make_fetcher(tmp_path, handler, politeness_delay_seconds=2.0)
    fetcher.fetch("https://example.com/one")
    sleeps_before_second_fetch = len(clock.sleeps)
    fetcher.fetch("https://example.com/two")

    assert len(clock.sleeps) > sleeps_before_second_fetch


def test_snapshot_filename_is_stable_for_the_same_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"content")

    fetcher, _clock = make_fetcher(tmp_path, handler)
    first = fetcher.fetch("https://example.com/stable")
    second = fetcher.fetch("https://example.com/stable")

    assert first.file_path == second.file_path


def test_transport_error_raises_after_exhausting_retries(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    fetcher, _clock = make_fetcher(tmp_path, handler, max_retries=1)
    with pytest.raises(httpx.ConnectError):
        fetcher.fetch("https://example.com/unreachable")


def test_context_manager_closes_the_client(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with Fetcher(tmp_path, client=client) as fetcher:
        fetcher.fetch("https://example.com/one")

    assert client.is_closed
