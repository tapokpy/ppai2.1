from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.bot.handlers.group_chat import (
    cmd_remind,
    cmd_today,
    reminder_done_callback,
    reminder_snooze_callback,
    send_reminder_message,
)
from app.core.database import async_session_maker
from app.core.scheduler import ReminderScheduler
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.reminder import Reminder
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_user() -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=444, username="group_admin")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_cmd_remind_requires_args(clean_db):
    user = await _seed_user()
    message = SimpleNamespace(chat=SimpleNamespace(id=1), answer=AsyncMock())
    command = SimpleNamespace(args=None)
    scheduler = ReminderScheduler(send_reminder_callback=AsyncMock())
    local_llm = AsyncMock()

    await cmd_remind(message, command, scheduler, local_llm, user)

    message.answer.assert_awaited_once_with("Использование: /remind 15:00 текст напоминания")


@pytest.mark.asyncio
async def test_cmd_remind_creates_reminder_via_regex(clean_db):
    user = await _seed_user()
    message = SimpleNamespace(chat=SimpleNamespace(id=2222), answer=AsyncMock())
    command = SimpleNamespace(args="15:00 Проверить блоки питания")
    scheduler = ReminderScheduler(send_reminder_callback=AsyncMock())
    local_llm = AsyncMock()

    await cmd_remind(message, command, scheduler, local_llm, user)

    message.answer.assert_awaited_once()
    assert "Проверить блоки питания" in message.answer.call_args.args[0]
    local_llm.generate.assert_not_called()

    async with async_session_maker() as session:
        reminders = (await session.execute(select(Reminder))).scalars().all()

    assert len(reminders) == 1
    assert reminders[0].chat_id == 2222


@pytest.mark.asyncio
async def test_cmd_remind_reports_when_unparseable(clean_db):
    user = await _seed_user()
    message = SimpleNamespace(chat=SimpleNamespace(id=3333), answer=AsyncMock())
    command = SimpleNamespace(args="что-то невнятное без времени")
    scheduler = ReminderScheduler(send_reminder_callback=AsyncMock())
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value="не JSON")

    await cmd_remind(message, command, scheduler, local_llm, user)

    message.answer.assert_awaited_once_with(
        "Не удалось распознать время напоминания. Попробуйте: /remind 15:00 текст"
    )


@pytest.mark.asyncio
async def test_reminder_done_callback_marks_completed(clean_db):
    user = await _seed_user()
    scheduler = ReminderScheduler(send_reminder_callback=AsyncMock())
    reminder = await scheduler.add_reminder(
        {
            "chat_id": 4444,
            "creator_id": user.id,
            "task_text": "Тест",
            "notify_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
    )

    callback = SimpleNamespace(data=f"reminder_done:{reminder.id}", answer=AsyncMock())
    await reminder_done_callback(callback)

    async with async_session_maker() as session:
        stored = await session.get(Reminder, reminder.id)

    assert stored.is_completed is True
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_reminder_snooze_callback_pushes_notify_at_forward(clean_db):
    user = await _seed_user()
    scheduler = ReminderScheduler(send_reminder_callback=AsyncMock())
    reminder = await scheduler.add_reminder(
        {
            "chat_id": 5555,
            "creator_id": user.id,
            "task_text": "Тест снуза",
            "notify_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
    )

    callback = SimpleNamespace(data=f"reminder_snooze:{reminder.id}", answer=AsyncMock())
    await reminder_snooze_callback(callback)

    async with async_session_maker() as session:
        stored = await session.get(Reminder, reminder.id)

    assert stored.is_completed is False
    assert stored.notify_at > datetime.now(timezone.utc) + timedelta(minutes=10)
    callback.answer.assert_awaited_once_with("Отложено на 15 минут")


@pytest.mark.asyncio
async def test_cmd_today_reports_no_activity(clean_db):
    message = SimpleNamespace(chat=SimpleNamespace(id=7777), answer=AsyncMock())
    local_llm = AsyncMock()

    await cmd_today(message, local_llm)

    message.answer.assert_awaited_once_with("Сегодня активности в чате ещё не было.")
    local_llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_today_summarizes_activity_via_llm(clean_db):
    user = await _seed_user()
    async with async_session_maker() as session:
        session.add(
            ActivityLog(user_id=user.id, chat_id=8888, message_type="group_message", summary="Обсудили экран")
        )
        await session.commit()

    message = SimpleNamespace(chat=SimpleNamespace(id=8888), answer=AsyncMock())
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value="Сегодня обсуждали экран для клиента.")

    await cmd_today(message, local_llm)

    local_llm.generate.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert "Сегодня обсуждали экран для клиента." in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_send_reminder_message_includes_target_username():
    bot = AsyncMock()
    reminder = SimpleNamespace(id=1, chat_id=999, task_text="Проверить блоки питания", target_username="@nikolia")

    await send_reminder_message(bot, reminder)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.call_args.kwargs["chat_id"] == 999
    assert "@nikolia" in bot.send_message.call_args.kwargs["text"]
    assert "Проверить блоки питания" in bot.send_message.call_args.kwargs["text"]
