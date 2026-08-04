"""Text extraction from downloaded PDF snapshots.

Downloading a PDF is just an ordinary `http.Fetcher.fetch()` call — `application/pdf`
snapshots with a `.pdf` suffix like any other content type. This module covers what
comes after: pulling text out of that snapshot so it can be handed to a deterministic
parser or, per DESIGN.md §6.1, an LLM fallback for the manufacturers where a
deterministic parser isn't worth writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class ExtractedPage:
    """Plain text extracted from one page of a PDF."""

    page_number: int  # 1-indexed, matching how a human would refer to a page
    text: str


@dataclass(frozen=True)
class ExtractedPdf:
    """Plain text extracted from every page of a PDF snapshot."""

    file_path: Path
    pages: list[ExtractedPage]

    @property
    def text(self) -> str:
        """The whole document's text, with a blank line between pages."""
        return "\n\n".join(page.text for page in self.pages)

    def is_empty(self) -> bool:
        """True when extraction found no text at all.

        A price list scanned as images rather than exported as text would "succeed"
        here but yield nothing useful — treat this as a signal to fall back to an
        LLM with vision, not to a deterministic parser.
        """
        return not any(page.text.strip() for page in self.pages)


def extract_text(path: Path | str) -> ExtractedPdf:
    """Extract text from every page of a PDF file."""
    path = Path(path)
    reader = PdfReader(path)
    pages = [
        ExtractedPage(page_number=index, text=page.extract_text() or "")
        for index, page in enumerate(reader.pages, start=1)
    ]
    return ExtractedPdf(file_path=path, pages=pages)
