from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.reply import main_menu

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я ассистент для расчётов и консультаций. "
        "Выберите действие в меню или просто задайте вопрос.",
        reply_markup=main_menu(),
    )
