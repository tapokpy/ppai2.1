from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.scheduler import ReminderScheduler
from app.models.sqlalchemy.reminder import Reminder
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_user() -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=888, username="scheduler_user")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_add_reminder_persists_to_db(clean_db):
    user = await _seed_user()
    send_callback = AsyncMock()
    scheduler = ReminderScheduler(send_reminder_callback=send_callback)

    reminder = await scheduler.add_reminder(
        {
            "chat_id": 12345,
            "creator_id": user.id,
            "target_username": "@nikolia",
            "task_text": "Скинуть смету",
            "notify_at": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
    )

    async with async_session_maker() as session:
        stored = await session.get(Reminder, reminder.id)

    assert stored is not None
    assert stored.task_text == "Скинуть смету"
    assert stored.is_completed is False


@pytest.mark.asyncio
async def test_check_and_send_reminders_sends_due_and_marks_completed(clean_db):
    user = await _seed_user()
    send_callback = AsyncMock()
    scheduler = ReminderScheduler(send_reminder_callback=send_callback)

    due_reminder = await scheduler.add_reminder(
        {
            "chat_id": 111,
            "creator_id": user.id,
            "task_text": "Просроченная задача",
            "notify_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
    )
    future_reminder = await scheduler.add_reminder(
        {
            "chat_id": 111,
            "creator_id": user.id,
            "task_text": "Будущая задача",
            "notify_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }
    )

    await scheduler.check_and_send_reminders()

    send_callback.assert_awaited_once()
    assert send_callback.call_args.args[0].id == due_reminder.id

    async with async_session_maker() as session:
        completed = await session.get(Reminder, due_reminder.id)
        still_pending = await session.get(Reminder, future_reminder.id)

    assert completed.is_completed is True
    assert still_pending.is_completed is False


@pytest.mark.asyncio
async def test_check_and_send_reminders_reschedules_cron_reminders(clean_db):
    user = await _seed_user()
    send_callback = AsyncMock()
    scheduler = ReminderScheduler(send_reminder_callback=send_callback)

    reminder = await scheduler.add_reminder(
        {
            "chat_id": 222,
            "creator_id": user.id,
            "task_text": "Еженедельная проверка",
            "notify_at": datetime.now(timezone.utc) - timedelta(minutes=1),
            "cron_rule": "0 17 * * 5",
        }
    )

    await scheduler.check_and_send_reminders()

    async with async_session_maker() as session:
        stored = await session.get(Reminder, reminder.id)

    assert stored.is_completed is False
    assert stored.notify_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_check_and_send_reminders_skips_failed_send_without_marking_completed(clean_db):
    user = await _seed_user()
    send_callback = AsyncMock(side_effect=RuntimeError("bot unreachable"))
    scheduler = ReminderScheduler(send_reminder_callback=send_callback)

    reminder = await scheduler.add_reminder(
        {
            "chat_id": 333,
            "creator_id": user.id,
            "task_text": "Не должно потеряться",
            "notify_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
    )

    await scheduler.check_and_send_reminders()

    async with async_session_maker() as session:
        stored = await session.get(Reminder, reminder.id)

    assert stored.is_completed is False
