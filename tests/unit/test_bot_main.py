from unittest.mock import AsyncMock, patch

import pytest

from app.bot.main import (
    RESTART_NOTIFICATION,
    _read_deploy_changelog,
    build_dispatcher,
    notify_admins_of_restart,
)


def test_build_dispatcher_registers_all_routers():
    dp = build_dispatcher()

    included_names = {router.name for router in dp.sub_routers}

    assert included_names == {
        "start", "admin", "group_chat", "engineer", "documents", "todo", "media", "showroom", "cad",
        "warehouse", "projects", "rag_memory", "chat",
    }


@pytest.mark.asyncio
async def test_notify_admins_of_restart_messages_every_admin():
    bot = AsyncMock()

    with (
        patch("app.bot.main.settings") as settings_mock,
        patch("app.bot.main._read_deploy_changelog", return_value=""),
    ):
        settings_mock.admin_ids = [111, 222]
        await notify_admins_of_restart(bot)

    assert bot.send_message.await_count == 2
    bot.send_message.assert_any_await(111, RESTART_NOTIFICATION)
    bot.send_message.assert_any_await(222, RESTART_NOTIFICATION)


@pytest.mark.asyncio
async def test_notify_admins_of_restart_one_failure_does_not_block_others():
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=[Exception("blocked the bot"), None])

    with (
        patch("app.bot.main.settings") as settings_mock,
        patch("app.bot.main._read_deploy_changelog", return_value=""),
    ):
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


@pytest.mark.asyncio
async def test_notify_admins_of_restart_appends_changelog_when_present():
    bot = AsyncMock()

    with (
        patch("app.bot.main.settings") as settings_mock,
        patch("app.bot.main._read_deploy_changelog", return_value="\n📝 Что нового:\n— abc123 fix bug"),
    ):
        settings_mock.admin_ids = [111]
        await notify_admins_of_restart(bot)

    sent_text = bot.send_message.call_args.args[1]
    assert sent_text.startswith(RESTART_NOTIFICATION)
    assert "abc123 fix bug" in sent_text


def test_read_deploy_changelog_returns_empty_when_file_missing(tmp_path):
    assert _read_deploy_changelog(tmp_path / "nope.txt") == ""


def test_read_deploy_changelog_returns_empty_when_file_empty(tmp_path):
    config = tmp_path / "DEPLOY_CHANGELOG.txt"
    config.write_text("", encoding="utf-8")

    assert _read_deploy_changelog(config) == ""


def test_read_deploy_changelog_formats_lines(tmp_path):
    config = tmp_path / "DEPLOY_CHANGELOG.txt"
    config.write_text("abc1234 Fix bug\ndef5678 Add feature\n", encoding="utf-8")

    result = _read_deploy_changelog(config)

    assert "— abc1234 Fix bug" in result
    assert "— def5678 Add feature" in result
    assert "Что нового" in result


def test_read_deploy_changelog_truncates_to_max_lines(tmp_path):
    config = tmp_path / "DEPLOY_CHANGELOG.txt"
    config.write_text("\n".join(f"commit{i}" for i in range(30)), encoding="utf-8")

    result = _read_deploy_changelog(config)

    assert result.count("—") == 15
    assert "commit14" in result
    assert "commit15" not in result
