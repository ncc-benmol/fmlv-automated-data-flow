"""Tests for PDF text extraction.

Builds a minimal valid PDF by hand rather than taking a PDF-generation library as a
test-only dependency — the format for a single Helvetica text run is simple enough,
and the builder is verified against `pypdf` itself below.
"""

from __future__ import annotations

from pathlib import Path

from fmlv_automated_data_flow.fetch import pdf


def build_minimal_pdf(text: str) -> bytes:
    """The smallest valid single-page PDF containing `text`, for tests only."""
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    content_stream = f"BT /F1 18 Tf 10 50 Td ({escaped}) Tj ET".encode("latin-1")

    obj_bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (
            b"<< /Type /Page /Parent 2 0 R "
            b"/Resources << /Font << /F1 4 0 R >> >> "
            b"/MediaBox [0 0 200 100] /Contents 5 0 R >>"
        ),
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        5: (
            f"<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
            + content_stream
            + b"\nendstream"
        ),
    }

    buffer = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(obj_bodies):
        offsets[number] = len(buffer)
        buffer += f"{number} 0 obj\n".encode("latin-1")
        buffer += obj_bodies[number]
        buffer += b"\nendobj\n"

    xref_offset = len(buffer)
    count = len(obj_bodies) + 1
    buffer += f"xref\n0 {count}\n".encode("latin-1")
    buffer += b"0000000000 65535 f \n"
    for number in sorted(obj_bodies):
        buffer += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")

    buffer += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode("latin-1")

    return bytes(buffer)


def build_empty_pdf() -> bytes:
    """A single blank page with no text content, for the is_empty() case."""
    obj_bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] >>",
    }
    buffer = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(obj_bodies):
        offsets[number] = len(buffer)
        buffer += f"{number} 0 obj\n".encode("latin-1")
        buffer += obj_bodies[number]
        buffer += b"\nendobj\n"

    xref_offset = len(buffer)
    count = len(obj_bodies) + 1
    buffer += f"xref\n0 {count}\n".encode("latin-1")
    buffer += b"0000000000 65535 f \n"
    for number in sorted(obj_bodies):
        buffer += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")

    buffer += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode("latin-1")

    return bytes(buffer)


def test_extracts_text_from_a_single_page(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    path.write_bytes(build_minimal_pdf("Adria Supreme 640 SLB - RRP 75950"))

    extracted = pdf.extract_text(path)

    assert len(extracted.pages) == 1
    assert extracted.pages[0].page_number == 1
    assert "Adria Supreme 640 SLB" in extracted.pages[0].text
    assert "75950" in extracted.text
    assert extracted.is_empty() is False


def test_is_empty_for_a_page_with_no_text(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    path.write_bytes(build_empty_pdf())

    extracted = pdf.extract_text(path)

    assert extracted.is_empty() is True


def test_text_property_joins_pages(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    path.write_bytes(build_minimal_pdf("single page content"))

    extracted = pdf.extract_text(path)

    assert extracted.text == extracted.pages[0].text
