import asyncio
import secrets
import time
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from app.bot.filters import MediaLinkFilter, ShouldRespondFilter
from app.services.media_downloader import (
    FormatOption,
    MediaDownloadError,
    MediaDownloader,
    MediaQuotaError,
)

router = Router(name="media")

LINK_UNAVAILABLE_REPLY = "Не получилось обработать ссылку: {error}"
NO_FORMATS_REPLY = "Не нашёл видеодорожек по этой ссылке — сайт не поддерживается или это не видео."
REQUEST_EXPIRED_REPLY = "Запрос устарел, отправьте ссылку ещё раз."
QUOTA_EXCEEDED_REPLY = "Не хватает места на диске: {error}"
DOWNLOAD_FAILED_REPLY = "Загрузка не удалась: {error}"

_MAX_FORMAT_BUTTONS = 8
_PROGRESS_EDIT_INTERVAL_SECONDS = 3.0


@dataclass
class _PendingDownload:
    url: str
    title: str
    formats: dict[str, FormatOption]


# In-memory, not persisted — a format-choice request only needs to survive
# the few seconds between probing a link and the user tapping a button.
# Lost on bot restart, same tradeoff as any other short-lived UI state.
_pending: dict[str, _PendingDownload] = {}


def _formats_keyboard(token: str, formats: list[FormatOption]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f.description, callback_data=f"media_dl:{token}:{f.format_id}")]
        for f in formats[:_MAX_FORMAT_BUTTONS]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(MediaLinkFilter(), ShouldRespondFilter())
async def handle_media_link(message: Message, media_downloader: MediaDownloader) -> None:
    url = message.text.strip()

    try:
        probe = await media_downloader.probe(url)
    except MediaDownloadError as exc:
        logger.warning(f"Failed to probe media link {url}: {exc}")
        await message.answer(LINK_UNAVAILABLE_REPLY.format(error=str(exc)[:200]))
        return

    if not probe.formats:
        await message.answer(NO_FORMATS_REPLY)
        return

    token = secrets.token_hex(4)
    _pending[token] = _PendingDownload(
        url=url, title=probe.title, formats={f.format_id: f for f in probe.formats}
    )

    await message.answer(f"«{probe.title}» — выберите качество:", reply_markup=_formats_keyboard(token, probe.formats))


async def _run_download(
    bot: Bot,
    chat_id: int,
    message_id: int,
    pending: _PendingDownload,
    format_id: str,
    media_downloader: MediaDownloader,
) -> None:
    """Runs off the callback handler so a slow download never risks the
    Telegram callback-query timeout. progress_hook fires from yt-dlp's own
    worker thread (download runs via asyncio.to_thread), so it hops back
    onto the bot's event loop via run_coroutine_threadsafe — a plain
    `await` from inside the hook would be invalid off-loop."""
    loop = asyncio.get_running_loop()
    last_edit_at = 0.0

    def progress_hook(d: dict) -> None:
        nonlocal last_edit_at
        if d.get("status") != "downloading":
            return
        now = time.monotonic()
        if now - last_edit_at < _PROGRESS_EDIT_INTERVAL_SECONDS:
            return
        last_edit_at = now
        percent = (d.get("_percent_str") or "").strip()
        asyncio.run_coroutine_threadsafe(
            bot.edit_message_text(f"⏳ Загружаю «{pending.title}»... {percent}", chat_id=chat_id, message_id=message_id),
            loop,
        )

    try:
        chosen = pending.formats.get(format_id)
        if chosen and chosen.filesize_bytes:
            await media_downloader.ensure_quota(chosen.filesize_bytes)
        media = await media_downloader.download(pending.url, format_id, pending.title, progress_hook=progress_hook)
    except MediaQuotaError as exc:
        await bot.edit_message_text(QUOTA_EXCEEDED_REPLY.format(error=str(exc)), chat_id=chat_id, message_id=message_id)
        return
    except MediaDownloadError as exc:
        logger.warning(f"Failed to download {pending.url}: {exc}")
        await bot.edit_message_text(
            DOWNLOAD_FAILED_REPLY.format(error=str(exc)[:200]), chat_id=chat_id, message_id=message_id
        )
        return

    await bot.edit_message_text(
        f"✅ «{media.title}» загружено и добавлено в библиотеку шоурума.", chat_id=chat_id, message_id=message_id
    )


@router.callback_query(F.data.startswith("media_dl:"))
async def handle_format_choice(callback: CallbackQuery, bot: Bot, media_downloader: MediaDownloader) -> None:
    _, token, format_id = callback.data.split(":", 2)
    pending = _pending.pop(token, None)

    if pending is None:
        await callback.answer(REQUEST_EXPIRED_REPLY, show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(f"⏳ Загружаю «{pending.title}»...")

    asyncio.create_task(
        _run_download(bot, callback.message.chat.id, callback.message.message_id, pending, format_id, media_downloader)
    )
