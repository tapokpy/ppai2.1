import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers.media import (
    LINK_UNAVAILABLE_REPLY,
    NO_FORMATS_REPLY,
    REQUEST_EXPIRED_REPLY,
    _pending,
    handle_format_choice,
    handle_media_link,
)
from app.services.media_downloader import DownloadOutcome, FormatOption, MediaDownloadError, ProbeResult


@pytest.fixture(autouse=True)
def _clear_pending():
    _pending.clear()
    yield
    _pending.clear()


@pytest.mark.asyncio
async def test_handle_media_link_shows_format_keyboard_on_success():
    media_downloader = AsyncMock()
    media_downloader.probe = AsyncMock(
        return_value=ProbeResult(
            title="Крутое видео",
            formats=[FormatOption(format_id="137", description="1080p · 50 МБ", filesize_bytes=50_000_000)],
        )
    )
    message = SimpleNamespace(text="https://example.com/watch?v=abc", answer=AsyncMock())

    await handle_media_link(message, media_downloader)

    message.answer.assert_awaited_once()
    assert "Крутое видео" in message.answer.call_args.args[0]
    keyboard = message.answer.call_args.kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 1
    assert len(_pending) == 1


@pytest.mark.asyncio
async def test_handle_media_link_shows_largest_formats_first():
    # yt-dlp returns formats ascending (smallest/worst quality first) — the
    # keyboard must show the biggest/best options, not just the first N in
    # that order (which was the bug: only tiny 144p/240p options ever showed).
    media_downloader = AsyncMock()
    media_downloader.probe = AsyncMock(
        return_value=ProbeResult(
            title="Видео",
            formats=[
                FormatOption(format_id="144p", description="144p", filesize_bytes=1_000_000),
                FormatOption(format_id="240p", description="240p", filesize_bytes=5_000_000),
                FormatOption(format_id="720p", description="720p", filesize_bytes=50_000_000),
                FormatOption(format_id="360p", description="360p", filesize_bytes=15_000_000),
            ],
        )
    )
    message = SimpleNamespace(text="https://example.com/watch?v=abc", answer=AsyncMock())

    await handle_media_link(message, media_downloader)

    keyboard = message.answer.call_args.kwargs["reply_markup"]
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert button_texts == ["720p", "360p", "240p", "144p"]


@pytest.mark.asyncio
async def test_handle_media_link_reports_probe_failure():
    media_downloader = AsyncMock()
    media_downloader.probe = AsyncMock(side_effect=MediaDownloadError("Unsupported URL"))
    message = SimpleNamespace(text="https://not-a-real-site.example/video", answer=AsyncMock())

    await handle_media_link(message, media_downloader)

    assert message.answer.call_args.args[0] == LINK_UNAVAILABLE_REPLY.format(error="Unsupported URL")


@pytest.mark.asyncio
async def test_handle_media_link_reports_no_video_formats():
    media_downloader = AsyncMock()
    media_downloader.probe = AsyncMock(return_value=ProbeResult(title="x", formats=[]))
    message = SimpleNamespace(text="https://example.com/audio-only", answer=AsyncMock())

    await handle_media_link(message, media_downloader)

    message.answer.assert_awaited_once_with(NO_FORMATS_REPLY)


@pytest.mark.asyncio
async def test_handle_format_choice_reports_expired_request():
    callback = SimpleNamespace(data="media_dl:deadbeef:137", answer=AsyncMock(), message=MagicMock())
    bot = AsyncMock()
    media_downloader = AsyncMock()

    await handle_format_choice(callback, bot, media_downloader, MagicMock())

    callback.answer.assert_awaited_once_with(REQUEST_EXPIRED_REPLY, show_alert=True)


@pytest.mark.asyncio
async def test_handle_format_choice_starts_background_download():
    from app.bot.handlers.media import _PendingDownload

    token = "abc12345"
    _pending[token] = _PendingDownload(
        url="https://example.com/watch?v=x",
        title="Видео",
        formats={"137": FormatOption(format_id="137", description="1080p", filesize_bytes=1000)},
    )

    callback_message = MagicMock()
    callback_message.chat.id = 1
    callback_message.message_id = 2
    callback_message.edit_text = AsyncMock()
    callback = SimpleNamespace(data=f"media_dl:{token}:137", answer=AsyncMock(), message=callback_message)
    bot = AsyncMock()
    media_downloader = AsyncMock()
    media_downloader.ensure_quota = AsyncMock()
    media_downloader.download = AsyncMock(
        return_value=DownloadOutcome(media=MagicMock(id=1, title="Видео"), degraded_quality=False)
    )
    cascade_router = MagicMock()

    await handle_format_choice(callback, bot, media_downloader, cascade_router)
    await asyncio.sleep(0.05)  # let the spawned background task run

    callback.answer.assert_awaited_once()
    callback_message.edit_text.assert_awaited_once()
    assert token not in _pending
    media_downloader.download.assert_awaited_once()
    final_text = bot.edit_message_text.call_args_list[-1].args[0]
    assert "360p" not in final_text


@pytest.mark.asyncio
async def test_handle_format_choice_reports_quality_downgrade():
    from app.bot.handlers.media import _PendingDownload

    token = "abc12345"
    _pending[token] = _PendingDownload(
        url="https://example.com/watch?v=x",
        title="Видео",
        formats={"137": FormatOption(format_id="137", description="1080p", filesize_bytes=1000)},
    )

    callback_message = MagicMock()
    callback_message.chat.id = 1
    callback_message.message_id = 2
    callback_message.edit_text = AsyncMock()
    callback = SimpleNamespace(data=f"media_dl:{token}:137", answer=AsyncMock(), message=callback_message)
    bot = AsyncMock()
    media_downloader = AsyncMock()
    media_downloader.ensure_quota = AsyncMock()
    media_downloader.download = AsyncMock(
        return_value=DownloadOutcome(media=MagicMock(id=1, title="Видео"), degraded_quality=True)
    )
    cascade_router = MagicMock()

    await handle_format_choice(callback, bot, media_downloader, cascade_router)
    await asyncio.sleep(0.05)  # let the spawned background task run

    final_text = bot.edit_message_text.call_args_list[-1].args[0]
    assert "360p" in final_text
