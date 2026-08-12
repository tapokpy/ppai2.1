from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.sqlalchemy.user import User
from app.services.business_rules import BusinessRulesEngine, RuleParseError

router = Router(name="admin")

ACCESS_DENIED_MESSAGE = "Команда доступна только администраторам."
ADD_RULE_USAGE = (
    "Использование:\n"
    "/add_rule <текст правила> — простое текстовое правило (предупреждение по совпадению слов)\n"
    "/add_rule <условие>[,<условие>...] ; <сообщение> [; INFO|WARNING|BLOCKING]\n"
    "Пример: /add_rule pixel_pitch<2.5,width_m>10 ; Мелкий шаг пикселя на большом экране — риск перегрева ; BLOCKING\n"
    "Доступные поля: pixel_pitch, width_m, height_m, module_count, module_power_w"
)


def is_admin(telegram_user_id: int) -> bool:
    return telegram_user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    await message.answer(
        "Панель администратора:\n"
        "/add_user <telegram_id> — одобрить доступ пользователю\n"
        "/add_rule <условие> — добавить бизнес-правило\n"
        "/edit_prompt — изменить промпт роли\n"
        "/set_history_depth <N> — глубина истории диалога"
    )


@router.message(Command("add_user"))
async def cmd_add_user(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    if not command.args:
        await message.answer("Использование: /add_user <telegram_id>")
        return

    try:
        telegram_id = int(command.args.strip().split()[0])
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(telegram_id=telegram_id, is_approved=True)
            session.add(user)
        else:
            user.is_approved = True

        await session.commit()

    await message.answer(f"Пользователь {telegram_id} одобрен и может пользоваться ботом.")


@router.message(Command("add_rule"))
async def cmd_add_rule(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    if not command.args:
        await message.answer(ADD_RULE_USAGE)
        return

    async with async_session_maker() as session:
        engine = BusinessRulesEngine(session)
        try:
            await engine.add_rule_from_text(command.args)
        except RuleParseError as exc:
            await message.answer(f"Не удалось разобрать правило: {exc}\n\n{ADD_RULE_USAGE}")
            return

    await message.answer("Правило добавлено.")
