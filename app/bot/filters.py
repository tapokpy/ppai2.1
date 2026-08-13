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


SHOWROOM_TRIGGER_PATTERN = re.compile(r"\b(?:шоурум|showroom)3\b", re.IGNORECASE)


class ShowroomTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(SHOWROOM_TRIGGER_PATTERN.search(message.text))


CAD_TRIGGER_PATTERN = re.compile(r"\b(?:чертеж|чертёж|cad)3\b", re.IGNORECASE)


class CadTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(CAD_TRIGGER_PATTERN.search(message.text))


# "склад3" — read-only stock lookup ("путеводитель": "склад3 где модуль X"),
# open to any approved user. Adding stock ("остаток3") is a separate,
# admin-only trigger so the read path doesn't need an is_admin check at all.
WAREHOUSE_TRIGGER_PATTERN = re.compile(r"\b(?:склад|warehouse)3\b", re.IGNORECASE)


class WarehouseTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(WAREHOUSE_TRIGGER_PATTERN.search(message.text))


STOCK_ADD_TRIGGER_PATTERN = re.compile(r"\b(?:остаток|stock)3\b", re.IGNORECASE)


class StockAddTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(STOCK_ADD_TRIGGER_PATTERN.search(message.text))


PROJECT_TRIGGER_PATTERN = re.compile(r"\b(?:проект|project)3\b", re.IGNORECASE)


class ProjectTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(PROJECT_TRIGGER_PATTERN.search(message.text))


URL_PATTERN = re.compile(r"^\s*https?://\S+\s*$", re.IGNORECASE)


class MediaLinkFilter(BaseFilter):
    """The message is *just* a link, nothing else — the media downloader's
    trigger. Deliberately strict (not "contains a URL anywhere") so a
    normal question that happens to mention a link ("смотри вот это
    https://... что думаешь?") still goes to regular chat instead of being
    hijacked as a download request. Not scoped to specific sites — yt-dlp
    itself supports a very wide range of sources, and rejecting unsupported
    ones is handled downstream (MediaDownloadError), not by this filter."""

    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(URL_PATTERN.match(message.text))


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
