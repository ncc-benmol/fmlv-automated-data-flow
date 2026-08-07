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


@dataclass(frozen=True)
class TextItem:
    """One run of text on a page, with the position it was drawn at.

    `x` increases left-to-right and `y` bottom-to-top, in PDF user-space points.
    """

    x: float
    y: float
    text: str


def extract_positioned_text(path: Path | str, page_number: int) -> list[TextItem]:
    """Every text run on one page, with coordinates, in the order the page draws them.

    `extract_text` is enough whenever reading order carries the meaning. Two things it
    loses, both of which a spec table needs:

    * **Where a run sits.** pypdf emits runs in content-stream order, which is not
      always left-to-right. Morelo's price list has pages where the two side-by-side
      model names are drawn right column first, so pairing names to value columns by
      reading order silently swaps two products' weights and prices. Coordinates are
      the only reliable way to recover the real column order — with the caveat that
      pypdf reports some runs at (0, 0) when it cannot place them, so callers should
      filter on `y` rather than trust every coordinate (see `docs/adapters/morelo.md`).
    * **Where one run ends and the next begins.** Joined into a line, `CLIFF 540 V` and
      `CLIFF 540` followed by `V` are indistinguishable. Sunlight's model headers are
      one run per model, so the runs themselves carry the split that the text cannot
      (see `docs/adapters/sunlight.md`).

    Order is the page's own, deliberately: it is the one thing that cannot be
    reconstructed afterwards, whereas any caller wanting left-to-right can sort on `x`
    — and should do so explicitly, since whether that is even correct depends on the
    document.
    """
    reader = PdfReader(Path(path))
    page = reader.pages[page_number - 1]

    items: list[TextItem] = []

    def visit(text: str, _cm: object, tm: list[float], *_rest: object) -> None:
        stripped = text.strip()
        if stripped:
            items.append(TextItem(x=tm[4], y=tm[5], text=stripped))

    page.extract_text(visitor_text=visit)
    return items
