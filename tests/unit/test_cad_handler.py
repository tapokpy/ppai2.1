from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.cad import MISSING_DIMENSIONS_REPLY, UNKNOWN_SHAPE_REPLY, handle_cad_command


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
async def test_generates_frame_and_sends_file(tmp_path):
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"shape": "frame", "width": 1000, "height": 500, "project_name": null}'
    )
    message = SimpleNamespace(text="чертеж3 рамка 1000х500", answer=AsyncMock(), answer_document=AsyncMock())
    session_maker, session = _mock_session_maker()
    cascade_router = MagicMock()

    with (
        patch("app.bot.handlers.cad.settings") as settings_mock,
        patch("app.bot.handlers.cad.async_session_maker", session_maker),
        patch("app.bot.handlers.cad.index_engineering_doc") as index_mock,
    ):
        settings_mock.CAD_STORAGE_PATH = str(tmp_path)
        await handle_cad_command(message, local_llm, cascade_router)

    message.answer.assert_awaited_once()
    message.answer_document.assert_awaited_once()
    session.add.assert_called_once()
    saved_doc = session.add.call_args.args[0]
    assert saved_doc.doc_type == "dxf"
    assert saved_doc.is_generated is True
    index_mock.assert_called_once_with(cascade_router.rag_engine, saved_doc)


@pytest.mark.asyncio
async def test_reports_unknown_shape():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"shape": null, "width": null, "height": null, "project_name": null}'
    )
    message = SimpleNamespace(text="чертеж3 что-то непонятное", answer=AsyncMock(), answer_document=AsyncMock())

    await handle_cad_command(message, local_llm, MagicMock())

    message.answer.assert_awaited_once_with(UNKNOWN_SHAPE_REPLY)
    message.answer_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_asks_for_dimensions_when_missing():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"shape": "frame", "width": null, "height": null, "project_name": null}'
    )
    message = SimpleNamespace(text="чертеж3 рамка", answer=AsyncMock(), answer_document=AsyncMock())

    await handle_cad_command(message, local_llm, MagicMock())

    message.answer.assert_awaited_once_with(MISSING_DIMENSIONS_REPLY)
    message.answer_document.assert_not_awaited()
