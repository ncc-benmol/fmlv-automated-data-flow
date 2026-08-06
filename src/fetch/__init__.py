"""Fetching, snapshotting and content extraction for manufacturer and NCC sources."""

from .browser import BrowserFetcher
from .http import USER_AGENT, FetchResult, Fetcher, content_hash, snapshot_filename
from .ncc import (
    NccCredentials,
    NccCredentialsError,
    NccExportError,
    NccSiteConfig,
    download_export,
)
from .pdf import ExtractedPage, ExtractedPdf, extract_text

__all__ = [
    "USER_AGENT",
    "BrowserFetcher",
    "ExtractedPage",
    "ExtractedPdf",
    "FetchResult",
    "Fetcher",
    "NccCredentials",
    "NccCredentialsError",
    "NccExportError",
    "NccSiteConfig",
    "content_hash",
    "download_export",
    "extract_text",
    "snapshot_filename",
]
