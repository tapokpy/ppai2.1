from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.documents import handle_document


def _make_message(file_name: str, mime_type: str | None = "application/pdf"):
    return SimpleNamespace(
        document=SimpleNamespace(file_id="file123", file_name=file_name, mime_type=mime_type),
        answer=AsyncMock(),
    )


def _mock_session_maker():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_maker():
        yield session

    return session_maker, session


@pytest.mark.asyncio
async def test_handle_document_rejects_non_pdf():
    message = _make_message("report.docx", mime_type="application/vnd.openxmlformats")
    bot = SimpleNamespace(get_file=AsyncMock(), download_file=AsyncMock())
    cascade_router = MagicMock()
    db_user = SimpleNamespace(id=1)

    await handle_document(message, bot, cascade_router, db_user)

    bot.get_file.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert "PDF" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_handle_document_ingests_pdf_into_rag(tmp_path):
    message = _make_message("catalogue.pdf")
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="docs/file123.pdf")),
        download_file=AsyncMock(),
    )
    cascade_router = MagicMock()
    cascade_router.rag_engine.embedding_model_name = "all-MiniLM-L6-v2"
    db_user = SimpleNamespace(id=42)
    session_maker, session = _mock_session_maker()

    with (
        patch("app.bot.handlers.documents.extract_text", return_value="some extracted text"),
        patch("app.bot.handlers.documents.DOCUMENT_TEMP_DIR", tmp_path),
        patch("app.bot.handlers.documents.async_session_maker", session_maker),
    ):
        await handle_document(message, bot, cascade_router, db_user)

    bot.get_file.assert_awaited_once_with("file123")
    cascade_router.rag_engine.add_documents.assert_called_once()
    call_kwargs = cascade_router.rag_engine.add_documents.call_args.kwargs
    assert call_kwargs["texts"] == ["some extracted text"]
    assert call_kwargs["metadatas"][0]["source"] == "pdf_upload"
    assert call_kwargs["metadatas"][0]["filename"] == "catalogue.pdf"
    assert call_kwargs["metadatas"][0]["uploaded_by"] == "42"
    message.answer.assert_awaited_once()
    assert "1 фрагм" in message.answer.call_args.args[0]

    session.add.assert_called_once()
    document_row = session.add.call_args.args[0]
    assert document_row.source == "pdf_upload"
    assert document_row.filename == "catalogue.pdf"
    assert document_row.uploaded_by == 42
    assert document_row.chunk_count == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_document_reports_when_no_text_extracted(tmp_path):
    message = _make_message("blank.pdf")
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="docs/file123.pdf")),
        download_file=AsyncMock(),
    )
    cascade_router = MagicMock()
    db_user = SimpleNamespace(id=42)

    with (
        patch("app.bot.handlers.documents.extract_text", return_value=""),
        patch("app.bot.handlers.documents.DOCUMENT_TEMP_DIR", tmp_path),
    ):
        await handle_document(message, bot, cascade_router, db_user)

    cascade_router.rag_engine.add_documents.assert_not_called()
    message.answer.assert_awaited_once_with("Не удалось извлечь текст из документа.")
