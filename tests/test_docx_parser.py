"""Tests for Phase 34: DOCX document parser and validator updates."""

import tempfile
from pathlib import Path
from unittest import TestCase

from docx import Document

from app.ingestion.docx_parser import (
    DOCXExtractionError,
    PAGE_CHAR_LIMIT,
    extract_docx_pages,
)
from app.utils.validators import validate_file_header, validate_upload_metadata


def _create_docx(paragraphs: list[str], path: Path) -> Path:
    """Create a real .docx file with the given paragraphs."""
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(str(path))
    return path


class DOCXParserTests(TestCase):
    """Verify the DOCX paragraph extractor."""

    def test_simple_document_returns_one_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _create_docx(["Hello world", "Second paragraph"], Path(tmp) / "test.docx")
            pages = extract_docx_pages(path)
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0]["page_number"], 1)
            self.assertIn("Hello world", pages[0]["text"])
            self.assertIn("Second paragraph", pages[0]["text"])

    def test_long_document_creates_multiple_pages(self) -> None:
        # Create paragraphs that exceed PAGE_CHAR_LIMIT
        paragraph = "x" * 1000
        paragraphs = [paragraph] * 10  # 10,000 chars total
        with tempfile.TemporaryDirectory() as tmp:
            path = _create_docx(paragraphs, Path(tmp) / "long.docx")
            pages = extract_docx_pages(path)
            self.assertGreater(len(pages), 1)
            # All pages should have sequential numbers
            for i, page in enumerate(pages, start=1):
                self.assertEqual(page["page_number"], i)

    def test_empty_paragraphs_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _create_docx(["Content", "", "   ", "More content"], Path(tmp) / "sparse.docx")
            pages = extract_docx_pages(path)
            self.assertEqual(len(pages), 1)
            self.assertNotIn("   ", pages[0]["text"])

    def test_empty_document_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _create_docx([], Path(tmp) / "empty.docx")
            with self.assertRaises(DOCXExtractionError) as ctx:
                extract_docx_pages(path)
            self.assertIn("no extractable text", str(ctx.exception))

    def test_missing_file_raises_error(self) -> None:
        with self.assertRaises(DOCXExtractionError) as ctx:
            extract_docx_pages(Path("nonexistent.docx"))
        self.assertIn("does not exist", str(ctx.exception))

    def test_invalid_file_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "fake.docx"
            fake_path.write_text("This is not a DOCX file")
            with self.assertRaises(DOCXExtractionError):
                extract_docx_pages(fake_path)

    def test_page_grouping_boundary(self) -> None:
        # Create paragraphs that exactly hit the limit
        paragraph = "a" * PAGE_CHAR_LIMIT
        with tempfile.TemporaryDirectory() as tmp:
            path = _create_docx([paragraph, "extra"], Path(tmp) / "boundary.docx")
            pages = extract_docx_pages(path)
            self.assertEqual(len(pages), 2)
            self.assertEqual(pages[0]["page_number"], 1)
            self.assertEqual(pages[1]["page_number"], 2)
            self.assertEqual(pages[1]["text"], "extra")


class DOCXValidatorTests(TestCase):
    """Verify the validator updates for DOCX support."""

    def test_docx_extension_is_accepted(self) -> None:
        filename, ext = validate_upload_metadata(
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(ext, ".docx")
        self.assertEqual(filename, "report.docx")

    def test_docx_wrong_mime_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_upload_metadata("report.docx", "text/plain")
        self.assertIn("MIME type", str(ctx.exception))

    def test_docx_header_pk_passes(self) -> None:
        # DOCX files are ZIP archives that start with PK
        validate_file_header(".docx", b"PK\x03\x04" + b"\x00" * 100)

    def test_docx_header_non_pk_fails(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_file_header(".docx", b"\x00\x00\x00" + b"not a zip")
        self.assertIn("not a valid DOCX", str(ctx.exception))

    def test_unsupported_extension_error_mentions_docx(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_upload_metadata("data.csv", "text/csv")
        self.assertIn("DOCX", str(ctx.exception))


class DOCXPipelineIntegrationTests(TestCase):
    """Verify DOCX is wired into the ingestion pipeline."""

    def test_pipeline_load_document_supports_docx(self) -> None:
        from app.ingestion.pipeline import load_document

        with tempfile.TemporaryDirectory() as tmp:
            path = _create_docx(["Test content for pipeline"], Path(tmp) / "pipe.docx")
            result = load_document({
                "file_type": "docx",
                "file_path": path,
            })
            self.assertIn("pages", result)
            self.assertEqual(len(result["pages"]), 1)
            self.assertIn("Test content", result["pages"][0]["text"])


if __name__ == "__main__":
    import unittest

    unittest.main()
