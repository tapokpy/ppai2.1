from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardRemove

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я ассистент для расчётов и консультаций. Просто напишите вопрос или что нужно сделать.",
        reply_markup=ReplyKeyboardRemove(),
    )
