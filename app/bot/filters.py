import re

from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message

# Matches a todo/plan keyword suffixed with the digit "3" (e.g.
# "тодолист3", "план3", "запиши в план3", "список задач3",
# "бэклог3"/"backlog3") — a deterministic, cheap trigger for the todo-
# capture handler that's very unlikely to fire on ordinary conversation.
# "3" stays required here (unlike the showroom trigger below) because
# "план"/"задача"/"таск" are common words in ordinary conversation —
# dropping the digit would false-trigger constantly. \s* before the 3
# (not a bare 3\b) is still needed though: a voice message transcribed
# by Whisper always inserts a space between a spoken word and a spoken
# digit ("план 3"), so the digit can never be glued onto the word the
# way someone types it — observed live with the showroom trigger, which
# had the exact same bug (see SHOWROOM_TRIGGER_PATTERN's history).
TODO_TRIGGER_PATTERN = re.compile(
    r"\b(?:тодо\s*лист|тудулист|to-?do|бэклог|backlog|план|задач|таск|task)\s*3\b",
    re.IGNORECASE,
)


class TodoTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(TODO_TRIGGER_PATTERN.search(message.text))


# "3" is optional here (unlike the other X3 triggers in this file) —
# "шоурум"/"showroom" alone is specific enough to this domain that it's
# very unlikely to false-trigger on ordinary conversation, and requiring
# the digit made this trigger effectively impossible to say out loud:
# Whisper transcribes spoken "шоурум три" as "шоурум 3" (a space, never
# glued), so the strict \bшоурум3\b never matched a real voice message.
# "шурум" (dropped unstressed "о") is included too — confirmed live,
# Whisper actually transcribed a real voice message as "Шурум 3,
# переключи ролик 6", which fell through to plain chat instead of the
# showroom handler until both this and the space issue were fixed.
SHOWROOM_TRIGGER_PATTERN = re.compile(r"\b(?:шоурум|шурум|showroom)(?:\s*3)?\b", re.IGNORECASE)


class ShowroomTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(SHOWROOM_TRIGGER_PATTERN.search(message.text))


# \s*3, not bare 3\b — see TODO_TRIGGER_PATTERN's comment on why (voice
# transcription always inserts a space before the digit).
CAD_TRIGGER_PATTERN = re.compile(r"\b(?:чертеж|чертёж|cad)\s*3\b", re.IGNORECASE)


class CadTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(CAD_TRIGGER_PATTERN.search(message.text))


# "склад3" — read-only stock lookup ("путеводитель": "склад3 где модуль X"),
# open to any approved user. Adding stock ("остаток3") is a separate,
# admin-only trigger so the read path doesn't need an is_admin check at all.
# \s*3, not bare 3\b — see TODO_TRIGGER_PATTERN's comment on why (voice
# transcription always inserts a space before the digit).
WAREHOUSE_TRIGGER_PATTERN = re.compile(r"\b(?:склад|warehouse)\s*3\b", re.IGNORECASE)


class WarehouseTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(WAREHOUSE_TRIGGER_PATTERN.search(message.text))


# \s*3, not bare 3\b — see TODO_TRIGGER_PATTERN's comment on why (voice
# transcription always inserts a space before the digit).
STOCK_ADD_TRIGGER_PATTERN = re.compile(r"\b(?:остаток|stock)\s*3\b", re.IGNORECASE)


class StockAddTriggerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and bool(STOCK_ADD_TRIGGER_PATTERN.search(message.text))


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
