from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, cmd_add_rule, cmd_add_user, cmd_admin, is_admin


def test_is_admin_checks_settings_admin_ids():
    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111, 222]
        assert is_admin(111) is True
        assert is_admin(999) is False


@pytest.mark.asyncio
async def test_cmd_admin_denies_non_admin():
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_admin(message)

    message.answer.assert_awaited_once_with(ACCESS_DENIED_MESSAGE)


@pytest.mark.asyncio
async def test_cmd_admin_shows_panel_for_admin():
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_admin(message)

    message.answer.assert_awaited_once()
    assert "Панель администратора" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_add_rule_denies_non_admin():
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())
    command = SimpleNamespace(args="текст правила")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_rule(message, command)

    message.answer.assert_awaited_once_with(ACCESS_DENIED_MESSAGE)


@pytest.mark.asyncio
async def test_cmd_add_rule_requires_args():
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args=None)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_rule(message, command)

    message.answer.assert_awaited_once()
    assert "Использование" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_add_user_denies_non_admin():
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())
    command = SimpleNamespace(args="123")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_user(message, command)

    message.answer.assert_awaited_once_with(ACCESS_DENIED_MESSAGE)


@pytest.mark.asyncio
async def test_cmd_add_user_requires_args():
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args=None)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_user(message, command)

    message.answer.assert_awaited_once_with("Использование: /add_user <telegram_id>")


@pytest.mark.asyncio
async def test_cmd_add_user_rejects_non_numeric_id():
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    command = SimpleNamespace(args="not_a_number")

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_add_user(message, command)

    message.answer.assert_awaited_once_with("telegram_id должен быть числом.")
