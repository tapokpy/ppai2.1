import asyncio
import re
from pathlib import Path
from uuid import uuid4

import yt_dlp
from loguru import logger

from app.core.config import settings
from app.core.database import async_session_maker
from app.core.tool_registry import ToolAttachment, ToolParameter, ToolResult, ToolSpec
from app.models.sqlalchemy.showroom_media import ShowroomMedia
from app.services.video_transcode import TranscodeError, transcode_to_h264_mp4

# Telegram's standard Bot API upload limit (no local Bot API server is
# configured in this deployment). The archived file on disk is always kept
# regardless of size — this only decides whether it's also attached to the
# chat reply.
_TELEGRAM_UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_FILENAME_LENGTH = 150


def _sanitize_filename(title: str) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", title).strip(" .")
    return cleaned[:_MAX_FILENAME_LENGTH] or "video"


async def run(url: str) -> ToolResult:
    download_dir = Path(settings.DOWNLOAD_STORAGE_PATH)
    download_dir.mkdir(parents=True, exist_ok=True)
    temp_basename = f".tmp_{uuid4().hex}"

    def _download() -> tuple[str, str]:
        # bestvideo+bestaudio/best (not a single fixed format_id): yt-dlp
        # picks the best available quality and muxes video+audio itself
        # (via its own ffmpeg call) — simpler and more robust than manually
        # probing/selecting a single format, since a single video-only
        # format_id would produce a silent file. The explicit re-encode
        # below is what actually guarantees the H.264/CRF profile, not this
        # format selector — this step only needs *a* usable source file.
        opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": str(download_dir / temp_basename) + ".%(ext)s",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info), info.get("title") or "video"

    try:
        downloaded_path_str, title = await asyncio.to_thread(_download)
    except Exception as exc:
        return ToolResult(text=f"Не получилось скачать видео: {exc}", success=False, error=str(exc))

    downloaded_path = Path(downloaded_path_str)
    final_path = download_dir / f"{_sanitize_filename(title)}.mp4"

    try:
        await transcode_to_h264_mp4(downloaded_path, final_path)
    except TranscodeError as exc:
        logger.warning(f"Transcode failed for {url}: {exc}")
        return ToolResult(text=f"Скачал, но не удалось перекодировать видео: {exc}", success=False, error=str(exc))
    finally:
        downloaded_path.unlink(missing_ok=True)

    size_bytes = final_path.stat().st_size

    async with async_session_maker() as session:
        session.add(ShowroomMedia(title=title, file_path=str(final_path), file_size_bytes=size_bytes))
        await session.commit()

    text = f"«{title}» сохранено: {final_path}"
    attachment = None
    if size_bytes <= _TELEGRAM_UPLOAD_LIMIT_BYTES:
        attachment = ToolAttachment(file_path=str(final_path), kind="document")
    else:
        text += "\n(файл больше 50 МБ — в чат не отправляю, но сохранён на диске)"

    return ToolResult(text=text, attachment=attachment)


def build_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="download_youtube",
        description=(
            "Скачивает видео по ссылке (YouTube и другие поддерживаемые сайты), перекодирует в "
            "MP4/H.264 (высокое качество) и сохраняет в архив."
        ),
        parameters=[ToolParameter(name="url", type="string", description="Ссылка на видео")],
        handler=run,
    )
