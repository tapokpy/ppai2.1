from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.bot.middlewares.group_activity import GroupActivityMiddleware
from app.core.database import async_session_maker
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


def _fake_group_message(chat_id: int, text: str = "привет всем"):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id, type="supergroup"), text=text)


@pytest.mark.asyncio
async def test_logs_group_messages_regardless_of_mention(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=901, username="group_member")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    middleware = GroupActivityMiddleware()
    handler = AsyncMock(return_value="handled")
    event = _fake_group_message(chat_id=5555)
    data = {"db_user": user}

    result = await middleware(handler, event, data)

    assert result == "handled"
    handler.assert_awaited_once_with(event, data)

    async with async_session_maker() as session:
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert len(logs) == 1
    assert logs[0].chat_id == 5555
    assert logs[0].message_type == "group_message"


@pytest.mark.asyncio
async def test_skips_logging_for_private_chats(clean_db):
    middleware = GroupActivityMiddleware()
    handler = AsyncMock(return_value="handled")
    event = SimpleNamespace(chat=SimpleNamespace(id=1, type="private"), text="привет")

    await middleware(handler, event, {})

    async with async_session_maker() as session:
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert logs == []


@pytest.mark.asyncio
async def test_skips_logging_when_no_db_user(clean_db):
    middleware = GroupActivityMiddleware()
    handler = AsyncMock(return_value="handled")
    event = _fake_group_message(chat_id=6666)

    result = await middleware(handler, event, {})

    assert result == "handled"

    async with async_session_maker() as session:
        logs = (await session.execute(select(ActivityLog))).scalars().all()

    assert logs == []
