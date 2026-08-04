"""Polite, retrying, snapshotting HTTP fetching.

Every response is written to disk before anything else happens to it (see DESIGN.md
§6.6) — this makes runs reproducible and debuggable without re-fetching, and is the
basis of the content-hash gating that keeps running costs near zero (§8.1).

This module only fetches and snapshots. It does *not* decide whether a page has
"changed" in any product sense — it just reports the content hash of what it fetched
next to whatever hash the caller already knew about, so the caller (Phase 4/5 code,
once it exists) can skip re-parsing and re-diffing an unchanged page.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

import httpx

#: Identifies the crawler and gives sites a contact point, per DESIGN.md's crawl
#: politeness intent (open question 4 — standing to crawl is still being confirmed).
USER_AGENT = (
    "NCC-FMLV-DataFlow/0.1 (+https://www.thencc.org.uk; "
    "automated data collection for Find My Leisure Vehicle; "
    "contact ben.m@thencc.org.uk)"
)

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0
DEFAULT_POLITENESS_DELAY_SECONDS = 1.0

#: Status codes worth retrying: server errors and rate limiting. Not 4xx in general —
#: a 404 is a permanent answer, retrying it just wastes the manufacturer's bandwidth.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_CONTENT_TYPE_SUFFIXES: dict[str, str] = {
    "text/html": ".html",
    "application/json": ".json",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}


@dataclass(frozen=True)
class FetchResult:
    """One fetched page or file, already written to disk."""

    url: str
    status_code: int
    content_type: str | None
    content_hash: str
    file_path: Path
    fetched_at: str
    unchanged: bool = False  # True when content_hash matches the caller's previous_hash


def content_hash(content: bytes) -> str:
    """A stable identifier for a page's content, used for skip-if-unchanged gating."""
    return hashlib.sha256(content).hexdigest()


def snapshot_filename(url: str, content_type: str | None) -> str:
    """Deterministic, filesystem-safe filename for a URL's snapshot."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = _CONTENT_TYPE_SUFFIXES.get(mime, ".bin")
    return f"{digest}{suffix}"


class Fetcher:
    """A polite, retrying, snapshotting HTTP client.

    One instance is meant to live for the duration of a single run: it enforces a
    minimum delay between requests (`politeness_delay_seconds`) and writes every
    response under `snapshot_dir`.
    """

    def __init__(
        self,
        snapshot_dir: Path | str,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        politeness_delay_seconds: float = DEFAULT_POLITENESS_DELAY_SECONDS,
        user_agent: str = USER_AGENT,
        client: httpx.Client | None = None,
        _monotonic: Callable[[], float] = time.monotonic,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.politeness_delay_seconds = politeness_delay_seconds
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )
        self._monotonic = _monotonic
        self._sleep = _sleep
        self._last_request_at: float | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _wait_for_politeness(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._monotonic() - self._last_request_at
        remaining = self.politeness_delay_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            if retry_after is not None:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
        return self.backoff_seconds * (2**attempt)

    def fetch(self, url: str, *, previous_hash: str | None = None) -> FetchResult:
        """Fetch a URL, snapshot it, and report whether its hash matches `previous_hash`.

        Retries server errors (5xx) and rate limiting (429) with backoff, honouring a
        `Retry-After` header when present. A 4xx other than 429 is not retried — it's
        treated as the site's final answer and snapshotted as-is, so a reviewer or a
        later run can still see what happened.

        Raises the underlying `httpx` exception if every attempt fails at the
        transport level (DNS, connection, timeout) — there is no page to snapshot in
        that case.
        """
        self._wait_for_politeness()

        response: httpx.Response | None = None
        transport_error: httpx.TransportError | None = None

        for attempt in range(self.max_retries + 1):
            transport_error = None
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                transport_error = exc
                response = None
            finally:
                self._last_request_at = self._monotonic()

            is_retryable = response is not None and response.status_code in _RETRYABLE_STATUS_CODES
            if response is not None and not is_retryable:
                break
            if attempt < self.max_retries:
                self._sleep(self._retry_delay(attempt, response))

        if response is None:
            assert transport_error is not None
            raise transport_error

        content = response.content
        digest = content_hash(content)
        filename = snapshot_filename(url, response.headers.get("content-type"))
        path = self.snapshot_dir / filename
        path.write_bytes(content)

        return FetchResult(
            url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            content_hash=digest,
            file_path=path,
            fetched_at=datetime.now(UTC).isoformat(),
            unchanged=(previous_hash is not None and previous_hash == digest),
        )
