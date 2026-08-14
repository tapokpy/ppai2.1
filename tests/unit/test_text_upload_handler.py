from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.documents import _decode_text_file, handle_document


def _make_message(file_name: str, mime_type: str | None = "text/plain"):
    return SimpleNamespace(
        document=SimpleNamespace(file_id="file123", file_name=file_name, mime_type=mime_type),
        caption=None,
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


def test_decode_text_file_prefers_utf8():
    assert _decode_text_file("Привет".encode("utf-8")) == "Привет"


def test_decode_text_file_falls_back_to_cp1251():
    assert _decode_text_file("Привет".encode("cp1251")) == "Привет"


@pytest.mark.asyncio
async def test_txt_upload_ingests_into_rag(tmp_path):
    message = _make_message("notes.txt")
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="docs/file123.txt")),
        download_file=AsyncMock(),
    )
    cascade_router = MagicMock()
    cascade_router.rag_engine.embedding_model_name = "all-MiniLM-L6-v2"
    db_user = SimpleNamespace(id=7)
    session_maker, session = _mock_session_maker()

    async def _fake_download(file_path, destination):
        destination.write_text("Инструкция по настройке контроллера NovaStar.", encoding="utf-8")

    bot.download_file.side_effect = _fake_download

    with (
        patch("app.bot.handlers.documents.DOCUMENT_TEMP_DIR", tmp_path),
        patch("app.bot.handlers.documents.async_session_maker", session_maker),
    ):
        await handle_document(message, bot, cascade_router, db_user)

    cascade_router.rag_engine.add_documents.assert_called_once()
    call_kwargs = cascade_router.rag_engine.add_documents.call_args.kwargs
    assert "NovaStar" in call_kwargs["texts"][0]
    assert call_kwargs["metadatas"][0]["source"] == "text_upload"
    assert call_kwargs["metadatas"][0]["filename"] == "notes.txt"

    session.add.assert_called_once()
    document_row = session.add.call_args.args[0]
    assert document_row.source == "text_upload"
    assert document_row.filename == "notes.txt"

    message.answer.assert_awaited_once()
    assert "notes.txt" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_md_upload_recognized_by_extension(tmp_path):
    message = _make_message("README.md", mime_type="application/octet-stream")
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="docs/file123.md")),
        download_file=AsyncMock(),
    )
    cascade_router = MagicMock()
    cascade_router.rag_engine.embedding_model_name = "all-MiniLM-L6-v2"
    db_user = SimpleNamespace(id=7)
    session_maker, _ = _mock_session_maker()

    async def _fake_download(file_path, destination):
        destination.write_text("# Заголовок\n\nСодержимое.", encoding="utf-8")

    bot.download_file.side_effect = _fake_download

    with (
        patch("app.bot.handlers.documents.DOCUMENT_TEMP_DIR", tmp_path),
        patch("app.bot.handlers.documents.async_session_maker", session_maker),
    ):
        await handle_document(message, bot, cascade_router, db_user)

    cascade_router.rag_engine.add_documents.assert_called_once()


@pytest.mark.asyncio
async def test_empty_text_file_reports_nothing_to_add(tmp_path):
    message = _make_message("empty.txt")
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="docs/file123.txt")),
        download_file=AsyncMock(),
    )
    cascade_router = MagicMock()
    db_user = SimpleNamespace(id=7)

    async def _fake_download(file_path, destination):
        destination.write_text("", encoding="utf-8")

    bot.download_file.side_effect = _fake_download

    with patch("app.bot.handlers.documents.DOCUMENT_TEMP_DIR", tmp_path):
        await handle_document(message, bot, cascade_router, db_user)

    cascade_router.rag_engine.add_documents.assert_not_called()
    assert "пуст" in message.answer.call_args.args[0].lower()
