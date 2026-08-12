from pathlib import Path
from unittest.mock import patch

import fitz
import pytest

from app.services.pdf_parser import chunk_text, extract_text


def _make_digital_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(str(path))
    document.close()


def _make_blank_pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page()
    document.save(str(path))
    document.close()


def test_extract_text_reads_digital_pdf_without_ocr(tmp_path):
    pdf_path = tmp_path / "spec.pdf"
    _make_digital_pdf(pdf_path, "Modulnyi ekran P2.5 dlya fasada zdaniya")

    with patch("app.services.pdf_parser.ocrmypdf.ocr") as ocr_mock:
        text = extract_text(str(pdf_path))

    ocr_mock.assert_not_called()
    assert "Modulnyi ekran P2.5" in text


def test_extract_text_falls_back_to_original_when_ocr_fails(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _make_blank_pdf(pdf_path)

    with patch("app.services.pdf_parser.ocrmypdf.ocr", side_effect=RuntimeError("tesseract missing")):
        text = extract_text(str(pdf_path))

    assert text == ""


def test_extract_text_uses_ocr_output_when_it_adds_text(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _make_blank_pdf(pdf_path)

    def fake_ocr(input_path, output_path, **kwargs):
        _make_digital_pdf(Path(output_path), "Raspoznanny tekst so skana")

    with patch("app.services.pdf_parser.ocrmypdf.ocr", side_effect=fake_ocr):
        text = extract_text(str(pdf_path))

    assert "Raspoznanny tekst so skana" in text


def test_chunk_text_splits_long_text_with_overlap():
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=100)

    assert len(chunks) == 3
    assert all(len(c) <= 1000 for c in chunks)
    # Consecutive chunks overlap by the configured amount.
    assert chunks[0][-100:] == chunks[1][:100]


def test_chunk_text_empty_input_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short_text_returns_single_chunk():
    assert chunk_text("short text", chunk_size=1000, overlap=100) == ["short text"]
