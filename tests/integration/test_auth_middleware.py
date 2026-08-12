from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.bot.middlewares.auth import ACCESS_PENDING_MESSAGE, AuthMiddleware
from app.core.database import async_session_maker
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


def _fake_telegram_user(user_id: int):
    return SimpleNamespace(id=user_id, username="ivan", full_name="Ivan Petrov")


def _fake_event(user_id: int):
    return SimpleNamespace(answer=AsyncMock())


@pytest.mark.asyncio
async def test_creates_unapproved_user_and_blocks_handler(clean_db):
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")
    event = _fake_event(111)
    data = {"event_from_user": _fake_telegram_user(111)}

    with patch("app.bot.middlewares.auth.settings") as settings_mock:
        settings_mock.admin_ids = []
        result = await middleware(handler, event, data)

    assert result is None
    handler.assert_not_awaited()
    event.answer.assert_awaited_once_with(ACCESS_PENDING_MESSAGE)

    async with async_session_maker() as session:
        db_result = await session.execute(select(User).where(User.telegram_id == 111))
        user = db_result.scalar_one()
        assert user.username == "ivan"
        assert user.is_approved is False


@pytest.mark.asyncio
async def test_auto_approves_admin(clean_db):
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")
    event = _fake_event(999)
    data = {"event_from_user": _fake_telegram_user(999)}

    with patch("app.bot.middlewares.auth.settings") as settings_mock:
        settings_mock.admin_ids = [999]
        result = await middleware(handler, event, data)

    assert result == "ok"
    handler.assert_awaited_once_with(event, data)
    assert data["db_user"].is_approved is True


@pytest.mark.asyncio
async def test_approved_user_reaches_handler(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=222, username="ivan", is_approved=True)
        session.add(user)
        await session.commit()

    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")
    event = _fake_event(222)
    data = {"event_from_user": _fake_telegram_user(222)}

    with patch("app.bot.middlewares.auth.settings") as settings_mock:
        settings_mock.admin_ids = []
        result = await middleware(handler, event, data)

    assert result == "ok"
    handler.assert_awaited_once_with(event, data)
    assert data["db_user"].telegram_id == 222

    async with async_session_maker() as session:
        db_result = await session.execute(select(User).where(User.telegram_id == 222))
        users = db_result.scalars().all()

    assert len(users) == 1


@pytest.mark.asyncio
async def test_passes_through_when_no_telegram_user(clean_db):
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")
    data = {}

    result = await middleware(handler, object(), data)

    assert result == "ok"
    assert "db_user" not in data
