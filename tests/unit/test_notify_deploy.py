from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from scripts.notify_deploy import _format_message, notify_deploy


def test_format_message_includes_bullets_and_services():
    message = _format_message(["- fixed X", "- added Y"], "bot,api")

    assert "- fixed X" in message
    assert "- added Y" in message
    assert "Деплой: bot,api" in message


def test_format_message_omits_services_line_when_not_given():
    message = _format_message(["- fixed X"], None)

    assert "Деплой:" not in message


@pytest.mark.asyncio
async def test_notify_deploy_messages_every_admin():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("scripts.notify_deploy.settings") as settings_mock,
        patch("scripts.notify_deploy.httpx.AsyncClient", return_value=mock_client),
    ):
        settings_mock.admin_ids = [111, 222]
        settings_mock.BOT_TOKEN = "test-token"
        await notify_deploy(["- fixed X"], services="bot")

    assert mock_client.post.await_count == 2
    urls = [call.args[0] for call in mock_client.post.await_args_list]
    assert all("test-token" in url for url in urls)


@pytest.mark.asyncio
async def test_notify_deploy_one_failure_does_not_block_others():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[httpx.ConnectError("boom"), mock_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("scripts.notify_deploy.settings") as settings_mock,
        patch("scripts.notify_deploy.httpx.AsyncClient", return_value=mock_client),
    ):
        settings_mock.admin_ids = [111, 222]
        settings_mock.BOT_TOKEN = "test-token"
        await notify_deploy(["- fixed X"])  # should not raise

    assert mock_client.post.await_count == 2


@pytest.mark.asyncio
async def test_notify_deploy_no_admins_configured():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("scripts.notify_deploy.settings") as settings_mock,
        patch("scripts.notify_deploy.httpx.AsyncClient", return_value=mock_client),
    ):
        settings_mock.admin_ids = []
        settings_mock.BOT_TOKEN = "test-token"
        await notify_deploy(["- fixed X"])

    mock_client.post.assert_not_called()
