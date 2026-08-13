import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.documents import _handle_cad_upload, _process_cad_upload
from app.services.cad_parser import generate_frame


def _mock_session_maker():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    @asynccontextmanager
    async def session_maker():
        yield session

    return session_maker, session


@pytest.mark.asyncio
async def test_handle_cad_upload_acks_immediately_and_backgrounds_processing(tmp_path):
    message = SimpleNamespace(
        document=SimpleNamespace(file_id="f1", file_name="frame_1000x500.dxf"),
        answer=AsyncMock(),
        answer_document=AsyncMock(),
    )
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="remote/f1.dxf")),
        download_file=AsyncMock(),
    )
    cascade_router = MagicMock()

    with (
        patch("app.bot.handlers.documents.DOCUMENT_TEMP_DIR", tmp_path),
        patch("app.bot.handlers.documents.asyncio.create_task") as create_task_mock,
    ):
        await _handle_cad_upload(message, bot, ".dxf", cascade_router)

    bot.download_file.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert "принят" in message.answer.call_args.args[0]
    # The actual parse/render work is scheduled, not awaited inline —
    # the handler must return as soon as the ack is sent.
    create_task_mock.assert_called_once()
    message.answer_document.assert_not_awaited()
    # Mocking create_task means the coroutine it was given never actually
    # runs — close it explicitly so pytest doesn't warn about it being GC'd
    # unawaited (harmless here, just noisy).
    create_task_mock.call_args.args[0].close()


@pytest.mark.asyncio
async def test_process_cad_upload_success_saves_doc_and_indexes(tmp_path):
    dxf_path = tmp_path / "input.dxf"
    generate_frame(width=1000, height=500).saveas(str(dxf_path))

    message = SimpleNamespace(answer=AsyncMock(), answer_document=AsyncMock())
    cascade_router = MagicMock()
    session_maker, session = _mock_session_maker()

    with (
        patch("app.bot.handlers.documents.settings") as settings_mock,
        patch("app.bot.handlers.documents.async_session_maker", session_maker),
        patch("app.bot.handlers.documents.index_engineering_doc") as index_mock,
    ):
        settings_mock.CAD_STORAGE_PATH = str(tmp_path / "storage")
        settings_mock.ODA_FILE_CONVERTER_PATH = ""
        await _process_cad_upload(message, dxf_path, "frame_1000x500", cascade_router)

    assert not dxf_path.exists()  # cleaned up
    session.add.assert_called_once()
    saved_doc = session.add.call_args.args[0]
    assert saved_doc.project_name == "frame_1000x500"
    assert saved_doc.doc_type == "dxf"
    assert saved_doc.is_generated is False
    index_mock.assert_called_once_with(cascade_router.rag_engine, saved_doc)

    message.answer.assert_awaited_once()
    assert "разобран" in message.answer.call_args.args[0]
    message.answer_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_cad_upload_reports_parse_error_and_cleans_up_temp_file(tmp_path):
    bad_path = tmp_path / "broken.dxf"
    bad_path.write_text("not a real dxf file", encoding="utf-8")

    message = SimpleNamespace(answer=AsyncMock(), answer_document=AsyncMock())
    cascade_router = MagicMock()

    with patch("app.bot.handlers.documents.settings") as settings_mock:
        settings_mock.ODA_FILE_CONVERTER_PATH = ""
        await _process_cad_upload(message, bad_path, "broken", cascade_router)

    assert not bad_path.exists()
    message.answer.assert_awaited_once()
    message.answer_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_cad_upload_end_to_end_via_real_background_task(tmp_path):
    """Lets the real asyncio.create_task run (no mocking it out) to check
    the ack -> background -> final-message sequence actually happens in
    that order end to end."""
    message = SimpleNamespace(
        document=SimpleNamespace(file_id="f1", file_name="plate_200x100.dxf"),
        answer=AsyncMock(),
        answer_document=AsyncMock(),
    )

    async def _fake_download(file_path, destination):
        generate_frame(width=200, height=100).saveas(str(destination))

    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="remote/f1.dxf")),
        download_file=AsyncMock(side_effect=_fake_download),
    )
    cascade_router = MagicMock()
    session_maker, session = _mock_session_maker()

    with (
        patch("app.bot.handlers.documents.DOCUMENT_TEMP_DIR", tmp_path),
        patch("app.bot.handlers.documents.settings") as settings_mock,
        patch("app.bot.handlers.documents.async_session_maker", session_maker),
        patch("app.bot.handlers.documents.index_engineering_doc"),
    ):
        settings_mock.CAD_STORAGE_PATH = str(tmp_path / "storage")
        settings_mock.ODA_FILE_CONVERTER_PATH = ""
        await _handle_cad_upload(message, bot, ".dxf", cascade_router)
        await asyncio.sleep(0.3)  # let the background task finish

    assert message.answer.await_count == 2  # ack, then final summary
    assert "принят" in message.answer.call_args_list[0].args[0]
    assert "разобран" in message.answer.call_args_list[1].args[0]
    message.answer_document.assert_awaited_once()
