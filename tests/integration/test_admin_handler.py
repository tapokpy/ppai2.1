from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.bot.handlers.admin import cmd_add_rule, cmd_add_user
from app.core.database import async_session_maker
from app.models.sqlalchemy.business_rule import BusinessRule
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_cmd_add_rule_creates_rule(clean_db):
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args="Новое правило")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_rule(message, command)

    async with async_session_maker() as session:
        rules = (await session.execute(select(BusinessRule))).scalars().all()

    assert len(rules) == 1
    assert rules[0].rule_text == "Новое правило"
    assert rules[0].conditions is None
    message.answer.assert_awaited_once_with("Правило добавлено.")


@pytest.mark.asyncio
async def test_cmd_add_rule_creates_conditional_rule(clean_db):
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args="pixel_pitch<2.5,width_m>10 ; Риск перегрева ; BLOCKING")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_rule(message, command)

    async with async_session_maker() as session:
        rules = (await session.execute(select(BusinessRule))).scalars().all()

    assert len(rules) == 1
    assert rules[0].rule_text == "Риск перегрева"
    assert rules[0].conditions == [
        {"field": "pixel_pitch", "operator": "<", "value": 2.5},
        {"field": "width_m", "operator": ">", "value": 10.0},
    ]
    assert rules[0].severity.value == "BLOCKING"


@pytest.mark.asyncio
async def test_cmd_add_user_approves_new_user(clean_db):
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args="777")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_user(message, command)

    async with async_session_maker() as session:
        user = (await session.execute(select(User).where(User.telegram_id == 777))).scalar_one()

    assert user.is_approved is True
    message.answer.assert_awaited_once_with("Пользователь 777 одобрен и может пользоваться ботом.")


@pytest.mark.asyncio
async def test_cmd_add_user_approves_existing_unapproved_user(clean_db):
    async with async_session_maker() as session:
        session.add(User(telegram_id=778, is_approved=False))
        await session.commit()

    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args="778")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_user(message, command)

    async with async_session_maker() as session:
        user = (await session.execute(select(User).where(User.telegram_id == 778))).scalar_one()

    assert user.is_approved is True
