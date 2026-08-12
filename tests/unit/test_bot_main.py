from unittest.mock import AsyncMock, patch

import pytest

from app.bot.main import RESTART_NOTIFICATION, build_dispatcher, notify_admins_of_restart


def test_build_dispatcher_registers_all_routers():
    dp = build_dispatcher()

    included_names = {router.name for router in dp.sub_routers}

    assert included_names == {"start", "admin", "group_chat", "engineer", "documents", "todo", "chat"}


@pytest.mark.asyncio
async def test_notify_admins_of_restart_messages_every_admin():
    bot = AsyncMock()

    with patch("app.bot.main.settings") as settings_mock:
        settings_mock.admin_ids = [111, 222]
        await notify_admins_of_restart(bot)

    assert bot.send_message.await_count == 2
    bot.send_message.assert_any_await(111, RESTART_NOTIFICATION)
    bot.send_message.assert_any_await(222, RESTART_NOTIFICATION)


@pytest.mark.asyncio
async def test_notify_admins_of_restart_one_failure_does_not_block_others():
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=[Exception("blocked the bot"), None])

    with patch("app.bot.main.settings") as settings_mock:
        settings_mock.admin_ids = [111, 222]
        await notify_admins_of_restart(bot)  # should not raise

    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_notify_admins_of_restart_no_admins_configured():
    bot = AsyncMock()

    with patch("app.bot.main.settings") as settings_mock:
        settings_mock.admin_ids = []
        await notify_admins_of_restart(bot)

    bot.send_message.assert_not_called()
