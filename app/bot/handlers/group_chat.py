from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.reminder_parser import parse_reminder_with_llm_fallback
from app.core.scheduler import ReminderScheduler
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.reminder import Reminder
from app.models.sqlalchemy.user import User
from app.services.local_llm import LocalLLMClient

router = Router(name="group_chat")


def _reminder_actions(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"reminder_done:{reminder_id}"),
                InlineKeyboardButton(
                    text="🔁 Отложить на 15 мин", callback_data=f"reminder_snooze:{reminder_id}"
                ),
            ]
        ]
    )


async def send_reminder_message(bot: Bot, reminder: Reminder) -> None:
    text = f"⏰ Напоминание: {reminder.task_text}"
    if reminder.target_username:
        text = f"{reminder.target_username}, {text}"

    await bot.send_message(
        chat_id=reminder.chat_id, text=text, reply_markup=_reminder_actions(reminder.id)
    )


@router.message(Command("remind"))
async def cmd_remind(
    message: Message,
    command: CommandObject,
    scheduler: ReminderScheduler,
    local_llm: LocalLLMClient,
    db_user: User,
) -> None:
    if not command.args:
        await message.answer("Использование: /remind 15:00 текст напоминания")
        return

    parsed = await parse_reminder_with_llm_fallback(command.args, datetime.now(timezone.utc), local_llm)

    if not parsed.has_reminder or not parsed.datetime_iso:
        await message.answer("Не удалось распознать время напоминания. Попробуйте: /remind 15:00 текст")
        return

    reminder = await scheduler.add_reminder(
        {
            "chat_id": message.chat.id,
            "creator_id": db_user.id,
            "target_username": parsed.target_username,
            "task_text": parsed.task_text,
            "notify_at": datetime.fromisoformat(parsed.datetime_iso),
            "cron_rule": parsed.cron_expression,
        }
    )

    await message.answer(
        f"Напоминание создано на {reminder.notify_at.strftime('%d.%m %H:%M')}: {reminder.task_text}"
    )


@router.callback_query(F.data.startswith("reminder_done:"))
async def reminder_done_callback(callback: CallbackQuery) -> None:
    reminder_id = int(callback.data.split(":", 1)[1])

    async with async_session_maker() as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder:
            reminder.is_completed = True
            await session.commit()

    await callback.answer("Отмечено как выполненное")


@router.callback_query(F.data.startswith("reminder_snooze:"))
async def reminder_snooze_callback(callback: CallbackQuery) -> None:
    reminder_id = int(callback.data.split(":", 1)[1])

    async with async_session_maker() as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder:
            reminder.notify_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            reminder.is_completed = False
            await session.commit()

    await callback.answer("Отложено на 15 минут")


@router.message(Command("today"))
async def cmd_today(message: Message, local_llm: LocalLLMClient) -> None:
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session_maker() as session:
        result = await session.execute(
            select(ActivityLog)
            .where(ActivityLog.chat_id == message.chat.id, ActivityLog.created_at >= since)
            .order_by(ActivityLog.created_at)
        )
        logs = result.scalars().all()

    if not logs:
        await message.answer("Сегодня активности в чате ещё не было.")
        return

    activity_text = "\n".join(f"- {log.summary}" for log in logs)
    summary = await local_llm.generate(
        prompt=activity_text,
        system_prompt="Сформируй краткую сводку активности за день на русском языке (3-5 предложений).",
    )

    await message.answer(f"📋 Сводка за день:\n\n{summary}")
