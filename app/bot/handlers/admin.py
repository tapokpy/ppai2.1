from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.config import settings
from app.core.database import async_session_maker
from app.services.business_rules import BusinessRulesEngine

router = Router(name="admin")

ACCESS_DENIED_MESSAGE = "Команда доступна только администраторам."


def is_admin(telegram_user_id: int) -> bool:
    return telegram_user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    await message.answer(
        "Панель администратора:\n"
        "/add_rule <текст> — добавить бизнес-правило\n"
        "/edit_prompt — изменить промпт роли\n"
        "/set_history_depth <N> — глубина истории диалога"
    )


@router.message(Command("add_rule"))
async def cmd_add_rule(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    if not command.args:
        await message.answer("Использование: /add_rule <текст правила>")
        return

    async with async_session_maker() as session:
        engine = BusinessRulesEngine(session)
        await engine.add_rule(command.args)

    await message.answer("Правило добавлено.")
