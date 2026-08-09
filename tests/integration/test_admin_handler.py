from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.bot.handlers.admin import cmd_add_rule
from app.core.database import async_session_maker
from app.models.sqlalchemy.business_rule import BusinessRule
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
    message.answer.assert_awaited_once_with("Правило добавлено.")
