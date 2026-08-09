from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.sqlalchemy.reminder import Reminder

SendReminderCallback = Callable[[Reminder], Awaitable[Any]]


class ReminderScheduler:
    def __init__(self, send_reminder_callback: SendReminderCallback):
        self._scheduler = AsyncIOScheduler()
        self._send_reminder_callback = send_reminder_callback

    def start(self) -> None:
        self._scheduler.add_job(
            self.check_and_send_reminders,
            trigger=IntervalTrigger(minutes=1),
            id="check_and_send_reminders",
            replace_existing=True,
        )
        self._scheduler.start()

    async def add_reminder(self, reminder_data: dict[str, Any]) -> Reminder:
        async with async_session_maker() as session:
            reminder = Reminder(
                chat_id=reminder_data["chat_id"],
                creator_id=reminder_data["creator_id"],
                target_username=reminder_data.get("target_username"),
                task_text=reminder_data["task_text"],
                notify_at=reminder_data["notify_at"],
                cron_rule=reminder_data.get("cron_rule"),
            )
            session.add(reminder)
            await session.commit()
            await session.refresh(reminder)

        return reminder

    async def check_and_send_reminders(self) -> None:
        now = datetime.now(timezone.utc)

        async with async_session_maker() as session:
            result = await session.execute(
                select(Reminder).where(Reminder.is_completed.is_(False), Reminder.notify_at <= now)
            )
            due_reminders = result.scalars().all()

            for reminder in due_reminders:
                try:
                    await self._send_reminder_callback(reminder)
                except Exception as exc:
                    logger.warning(f"Failed to send reminder {reminder.id}: {exc}")
                    continue

                if reminder.cron_rule:
                    trigger = CronTrigger.from_crontab(reminder.cron_rule, timezone=timezone.utc)
                    reminder.notify_at = trigger.get_next_fire_time(None, now)
                else:
                    reminder.is_completed = True

            await session.commit()
