from pathlib import Path

import fitz  # PyMuPDF
import ocrmypdf
import pdfplumber
from loguru import logger

# Below this average characters-per-page, a PDF is treated as a scan with no
# extractable text layer and routed through OCR.
MIN_CHARS_PER_PAGE_FOR_DIGITAL_TEXT = 20

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


def _extract_page_texts(path: str) -> list[str]:
    with fitz.open(path) as document:
        return [page.get_text().strip() for page in document]


def _looks_scanned(page_texts: list[str]) -> bool:
    if not page_texts:
        return True
    chars_per_page = sum(len(text) for text in page_texts) / len(page_texts)
    return chars_per_page < MIN_CHARS_PER_PAGE_FOR_DIGITAL_TEXT


def _ocr_to_searchable_pdf(input_path: str, output_path: str, language: str) -> bool:
    try:
        ocrmypdf.ocr(input_path, output_path, language=language, force_ocr=True, progress_bar=False)
        return True
    except Exception as exc:
        logger.warning(f"OCR failed for {input_path}, falling back to whatever text was extracted: {exc}")
        return False


def _extract_tables(path: str) -> list[str]:
    tables_text = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    rows = ["\t".join(cell or "" for cell in row) for row in table]
                    if rows:
                        tables_text.append("\n".join(rows))
    except Exception as exc:
        logger.warning(f"Table extraction failed for {path}: {exc}")

    return tables_text


def extract_text(path: str, ocr_language: str = "rus+eng") -> str:
    """Extract text from a PDF, OCR-ing it first if it looks like a scan.

    Digital-text PDFs are read directly with PyMuPDF. If the average
    extractable text per page is too small (a scanned document with no text
    layer), the file is OCR'd via OCRmyPDF into a searchable copy and
    re-extracted. Tables detected by pdfplumber are appended separately,
    since PyMuPDF's plain text extraction often mangles tabular layout.
    """
    page_texts = _extract_page_texts(path)

    if _looks_scanned(page_texts):
        ocr_output_path = f"{path}.ocr.pdf"
        if _ocr_to_searchable_pdf(path, ocr_output_path, ocr_language):
            ocr_page_texts = _extract_page_texts(ocr_output_path)
            Path(ocr_output_path).unlink(missing_ok=True)
            if not _looks_scanned(ocr_page_texts):
                page_texts = ocr_page_texts

    sections = [text for text in page_texts if text]
    sections.extend(_extract_tables(path))

    return "\n\n".join(sections)


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks suitable for embedding/RAG ingestion."""
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap

    return chunks
