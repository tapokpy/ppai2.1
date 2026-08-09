from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message


class ShouldRespondFilter(BaseFilter):
    """Bot answers every private message, but in groups only on mention or reply-to-bot."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if message.chat.type == "private":
            return True

        if (
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == bot.id
        ):
            return True

        me = await bot.get_me()
        if me.username and message.text and f"@{me.username}" in message.text:
            return True

        return False
