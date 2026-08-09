from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.bot.middlewares.auth import AuthMiddleware
from app.core.database import async_session_maker
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


def _fake_telegram_user(user_id: int):
    return SimpleNamespace(id=user_id, username="ivan", full_name="Ivan Petrov")


@pytest.mark.asyncio
async def test_creates_new_user_on_first_contact(clean_db):
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")
    event = object()
    data = {"event_from_user": _fake_telegram_user(111)}

    result = await middleware(handler, event, data)

    assert result == "ok"
    assert data["db_user"].telegram_id == 111
    handler.assert_awaited_once_with(event, data)

    async with async_session_maker() as session:
        db_result = await session.execute(select(User).where(User.telegram_id == 111))
        assert db_result.scalar_one().username == "ivan"


@pytest.mark.asyncio
async def test_reuses_existing_user(clean_db):
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")

    await middleware(handler, object(), {"event_from_user": _fake_telegram_user(222)})
    second_data = {"event_from_user": _fake_telegram_user(222)}
    await middleware(handler, object(), second_data)

    async with async_session_maker() as session:
        db_result = await session.execute(select(User).where(User.telegram_id == 222))
        users = db_result.scalars().all()

    assert len(users) == 1
    assert second_data["db_user"].telegram_id == 222


@pytest.mark.asyncio
async def test_passes_through_when_no_telegram_user(clean_db):
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")
    data = {}

    result = await middleware(handler, object(), data)

    assert result == "ok"
    assert "db_user" not in data
