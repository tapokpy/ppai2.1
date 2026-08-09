from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.bot.handlers.chat import handle_text
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
    }

    message = SimpleNamespace(
        text="Привет",
        message_id=7,
        chat=SimpleNamespace(id=999),
        answer=AsyncMock(),
    )

    await handle_text(message, cascade_router, user)

    cascade_router.process_query.assert_awaited_once_with(user_id=user.id, prompt="Привет")
    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == "Ответ бота"

    async with async_session_maker() as session:
        messages = (await session.execute(select(MessageModel))).scalars().all()
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert len(messages) == 1
    assert messages[0].source == "local"
    assert messages[0].prompt == "Привет"
    assert len(logs) == 1
    assert logs[0].chat_id == 999
