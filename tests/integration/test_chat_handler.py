from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.bot.handlers.chat import THINKING_PLACEHOLDER, handle_text, handle_voice
from app.core.database import async_session_maker
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


def _make_message(**kwargs) -> SimpleNamespace:
    """`.answer(...)` returns an object with an awaitable `.delete()`, since
    _process_and_reply now sends a thinking-placeholder message first and
    deletes it once the real answer is ready."""
    placeholder = SimpleNamespace(delete=AsyncMock())
    return SimpleNamespace(answer=AsyncMock(return_value=placeholder), **kwargs)


@pytest.mark.asyncio
async def test_handle_text_shows_and_removes_thinking_placeholder(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=563, username="engineer7")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Ответ бота",
        "source": "local",
        "context_used": False,
    }

    message = _make_message(text="Привет", message_id=17, chat=SimpleNamespace(id=1007, type="private"))

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = []
        await handle_text(message, cascade_router, user)

    assert message.answer.await_count == 2
    assert message.answer.await_args_list[0].args[0] == THINKING_PLACEHOLDER
    placeholder = message.answer.return_value
    placeholder.delete.assert_awaited_once()
    assert message.answer.await_args_list[1].args[0] == "Ответ бота"


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

    message = _make_message(text="Привет", message_id=7, chat=SimpleNamespace(id=999, type="private"))

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = []
        await handle_text(message, cascade_router, user)

    cascade_router.process_query.assert_awaited_once_with(user_id=user.id, prompt="Привет")
    # Every user (not just admins) sees the timing line before the answer.
    # No keyboard is attached (removed per explicit user request).
    assert message.answer.call_args.args[0] == "⏱ 1.23с\n\nОтвет бота"
    assert message.answer.call_args.kwargs == {}

    async with async_session_maker() as session:
        messages = (await session.execute(select(MessageModel))).scalars().all()
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert len(messages) == 1
    assert messages[0].source == "local"
    assert messages[0].prompt == "Привет"
    # DB stores the raw answer text; the metrics prefix is a display-only concern.
    assert messages[0].response == "Ответ бота"
    assert len(logs) == 1
    assert logs[0].chat_id == 999


@pytest.mark.asyncio
async def test_handle_text_shows_confidence_emoji_alongside_timing(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=560, username="engineer6")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Сечение кабеля 4 кв.мм",
        "source": "local",
        "context_used": False,
        "elapsed_seconds": 0.8,
        "confidence": "medium",
    }

    message = _make_message(
        text="какое сечение кабеля?", message_id=14, chat=SimpleNamespace(id=1004, type="private")
    )

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = []
        await handle_text(message, cascade_router, user)

    assert message.answer.call_args.args[0] == "⏱ 0.8с · ⚠️ medium\n\nСечение кабеля 4 кв.мм"


@pytest.mark.asyncio
async def test_handle_text_shows_extra_debug_line_to_admin(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=561, username="admin_engineer")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Сечение кабеля 4 кв.мм",
        "source": "rag",
        "context_used": True,
        "elapsed_seconds": 0.8,
        "confidence": "medium",
        "rag_debug": {"max_score": 0.91, "retrieved": []},
        "llm_usage": {"prompt_tokens": 120, "completion_tokens": 45},
    }

    message = _make_message(
        text="какое сечение кабеля?", message_id=15, chat=SimpleNamespace(id=1005, type="private")
    )

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [561]
        await handle_text(message, cascade_router, user)

    reply = message.answer.call_args.args[0]
    # Everyone-visible line first, then the admin-only diagnostic line, then the answer.
    assert reply == (
        "⏱ 0.8с · ⚠️ medium\n"
        "🔧 rag · score 0.91 · 120+45 ток\n\n"
        "Сечение кабеля 4 кв.мм"
    )


@pytest.mark.asyncio
async def test_handle_text_shows_timing_breakdown_to_admin(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=562, username="admin_engineer2")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    cascade_router = AsyncMock()
    cascade_router.process_query.return_value = {
        "text": "Сечение кабеля 4 кв.мм",
        "source": "rag",
        "context_used": True,
        "elapsed_seconds": 74.36,
        "confidence": "low",
        "rag_debug": {"max_score": 0.9, "retrieved": []},
        "llm_usage": None,
        "timing": {"rag_seconds": 0.02, "local_seconds": 74.3},
    }

    message = _make_message(
        text="какое сечение кабеля?", message_id=16, chat=SimpleNamespace(id=1006, type="private")
    )

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [562]
        await handle_text(message, cascade_router, user)

    reply = message.answer.call_args.args[0]
    assert reply == (
        "⏱ 74.36с · ❓ low\n"
        "🔧 rag · rag 0.02с + llm 74.3с · score 0.90\n\n"
        "Сечение кабеля 4 кв.мм"
    )


@pytest.mark.asyncio
async def test_handle_text_replies_without_prefix_when_no_metrics_present(clean_db):
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

    message = _make_message(text="Привет", message_id=13, chat=SimpleNamespace(id=1003, type="private"))

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = []
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

    message = _make_message(
        text="@bot Привет", message_id=8, chat=SimpleNamespace(id=1000, type="supergroup")
    )

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = []
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

    message = _make_message(
        voice=SimpleNamespace(file_id="abc"), message_id=9, chat=SimpleNamespace(id=1001, type="private")
    )

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = []
        await handle_voice(message, cascade_router, user, bot, transcriber)

    bot.get_file.assert_awaited_once_with("abc")
    transcriber.transcribe.assert_awaited_once()
    cascade_router.process_query.assert_awaited_once_with(
        user_id=user.id, prompt="Расскажи про шаг пикселя"
    )
    # Listening placeholder -> recognized-text message -> thinking placeholder -> answer.
    assert message.answer.await_count == 4
    assert message.answer.await_args_list[0].args[0] == "🎙 Распознаю голосовое сообщение..."
    assert message.answer.await_args_list[1].args[0] == "🎧 Распознано: «Расскажи про шаг пикселя»"
    assert message.answer.await_args_list[2].args[0] == THINKING_PLACEHOLDER
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

    message = _make_message(
        voice=SimpleNamespace(file_id="def"), message_id=10, chat=SimpleNamespace(id=1002, type="private")
    )

    await handle_voice(message, cascade_router, user, bot, transcriber)

    cascade_router.process_query.assert_not_awaited()
    # Listening placeholder still shown and cleaned up, but it returns
    # before calling _process_and_reply at all (nothing to transcribe).
    assert message.answer.await_count == 2
    assert message.answer.await_args_list[0].args[0] == "🎙 Распознаю голосовое сообщение..."
    placeholder = message.answer.return_value
    placeholder.delete.assert_awaited()
    assert "не удалось распознать" in message.answer.call_args.args[0].lower()

    async with async_session_maker() as session:
        messages = (await session.execute(select(MessageModel))).scalars().all()

    assert messages == []
