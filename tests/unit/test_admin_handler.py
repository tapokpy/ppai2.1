from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.bot.handlers.admin import (
    ACCESS_DENIED_MESSAGE,
    DASHBOARD_UNAVAILABLE_MESSAGE,
    cmd_add_rule,
    cmd_add_user,
    cmd_admin,
    cmd_dashboard,
    is_admin,
)


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


@pytest.mark.asyncio
async def test_cmd_dashboard_denies_non_admin():
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [111]
        await cmd_dashboard(message)

    message.answer.assert_awaited_once_with(ACCESS_DENIED_MESSAGE)


@pytest.mark.asyncio
async def test_cmd_dashboard_sends_login_link_for_admin():
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())
    ott_response = MagicMock()
    ott_response.raise_for_status = MagicMock()
    ott_response.json.return_value = {"ott": "abc123", "expires_in": 300}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=ott_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.bot.handlers.admin.settings") as settings_mock,
        patch("app.bot.handlers.admin.httpx.AsyncClient", return_value=mock_client),
    ):
        settings_mock.admin_ids = [111]
        settings_mock.API_INTERNAL_BASE_URL = "http://api:8000/api/v1"
        settings_mock.WEB_DASHBOARD_URL = "http://localhost:8080"
        settings_mock.INTERNAL_API_TOKEN = "internal-secret"
        await cmd_dashboard(message)

    mock_client.post.assert_awaited_once_with(
        "http://api:8000/api/v1/auth/generate_ott",
        json={"telegram_id": 111},
        headers={"X-Internal-Token": "internal-secret"},
        timeout=10.0,
    )
    message.answer.assert_awaited_once()
    reply = message.answer.call_args.args[0]
    assert "http://localhost:8080/login?ott=abc123" in reply
    assert "300" in reply


@pytest.mark.asyncio
async def test_cmd_dashboard_reports_friendly_message_when_api_unreachable():
    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.bot.handlers.admin.settings") as settings_mock,
        patch("app.bot.handlers.admin.httpx.AsyncClient", return_value=mock_client),
    ):
        settings_mock.admin_ids = [111]
        await cmd_dashboard(message)

    message.answer.assert_awaited_once_with(DASHBOARD_UNAVAILABLE_MESSAGE)
