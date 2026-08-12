from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.bot.handlers.chat import handle_text, handle_voice
from app.core.database import async_session_maker
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_handle_text_saves_history_and_replies(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=555, username="engineer")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Ответ бота",
        "source": "local",
        "context_used": False,
        "elapsed_seconds": 1.23,
    }

    message = SimpleNamespace(
        text="Привет",
        message_id=7,
        chat=SimpleNamespace(id=999, type="private"),
        answer=AsyncMock(),
    )

    await handle_text(message, cascade_router, user)

    cascade_router.process_query.assert_awaited_once_with(user_id=user.id, prompt="Привет")
    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == "⏱ 1.23с\n\nОтвет бота"

    async with async_session_maker() as session:
        messages = (await session.execute(select(MessageModel))).scalars().all()
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert len(messages) == 1
    assert messages[0].source == "local"
    assert messages[0].prompt == "Привет"
    # DB stores the raw answer text; the timing prefix is a display-only concern.
    assert messages[0].response == "Ответ бота"
    assert len(logs) == 1
    assert logs[0].chat_id == 999


@pytest.mark.asyncio
async def test_handle_text_replies_without_prefix_when_elapsed_seconds_missing(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=559, username="engineer5")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Ответ бота",
        "source": "local",
        "context_used": False,
    }

    message = SimpleNamespace(
        text="Привет",
        message_id=13,
        chat=SimpleNamespace(id=1003, type="private"),
        answer=AsyncMock(),
    )

    await handle_text(message, cascade_router, user)

    assert message.answer.call_args.args[0] == "Ответ бота"


@pytest.mark.asyncio
async def test_handle_text_skips_activity_log_for_group_chat(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=556, username="engineer2")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Ответ бота",
        "source": "local",
        "context_used": False,
    }

    message = SimpleNamespace(
        text="@bot Привет",
        message_id=8,
        chat=SimpleNamespace(id=1000, type="supergroup"),
        answer=AsyncMock(),
    )

    await handle_text(message, cascade_router, user)

    async with async_session_maker() as session:
        messages = (await session.execute(select(MessageModel))).scalars().all()
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert len(messages) == 1
    assert logs == []


@pytest.mark.asyncio
async def test_handle_voice_transcribes_and_replies(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=557, username="engineer3")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Ответ бота",
        "source": "local",
        "context_used": False,
        "elapsed_seconds": 3.5,
    }

    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="voice/file_1.ogg")),
        download_file=AsyncMock(),
    )
    transcriber = SimpleNamespace(transcribe=AsyncMock(return_value="Расскажи про шаг пикселя"))

    message = SimpleNamespace(
        voice=SimpleNamespace(file_id="abc"),
        message_id=9,
        chat=SimpleNamespace(id=1001, type="private"),
        answer=AsyncMock(),
    )

    await handle_voice(message, cascade_router, user, bot, transcriber)

    bot.get_file.assert_awaited_once_with("abc")
    transcriber.transcribe.assert_awaited_once()
    cascade_router.process_query.assert_awaited_once_with(
        user_id=user.id, prompt="Расскажи про шаг пикселя"
    )
    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == "⏱ 3.5с\n\nОтвет бота"

    async with async_session_maker() as session:
        messages = (await session.execute(select(MessageModel))).scalars().all()
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert len(messages) == 1
    assert messages[0].prompt == "Расскажи про шаг пикселя"
    assert len(logs) == 1
    assert logs[0].message_type == "voice"


@pytest.mark.asyncio
async def test_handle_voice_reports_when_transcription_empty(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=558, username="engineer4")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="voice/file_2.ogg")),
        download_file=AsyncMock(),
    )
    transcriber = SimpleNamespace(transcribe=AsyncMock(return_value=""))

    message = SimpleNamespace(
        voice=SimpleNamespace(file_id="def"),
        message_id=10,
        chat=SimpleNamespace(id=1002, type="private"),
        answer=AsyncMock(),
    )

    await handle_voice(message, cascade_router, user, bot, transcriber)

    cascade_router.process_query.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert "не удалось распознать" in message.answer.call_args.args[0].lower()

    async with async_session_maker() as session:
        messages = (await session.execute(select(MessageModel))).scalars().all()

    assert messages == []
