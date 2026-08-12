import re

from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message

# Matches a todo/plan keyword immediately suffixed with the digit "3"
# (e.g. "тодолист3", "план3", "запиши в план3", "список задач3",
# "бэклог3"/"backlog3") — a deterministic, cheap trigger for the todo-
# capture handler that's very unlikely to fire on ordinary conversation.
TODO_TRIGGER_PATTERN = re.compile(
    r"\b(?:тодо\s*лист|тудулист|to-?do|бэклог|backlog|план|задач|таск|task)3\b",
    re.IGNORECASE,
)


class TodoTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(TODO_TRIGGER_PATTERN.search(message.text))


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
