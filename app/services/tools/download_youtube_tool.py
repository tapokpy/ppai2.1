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

    def _base_opts() -> dict:
        return {
            "outtmpl": str(download_dir / temp_basename) + ".%(ext)s",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            # Without this, a URL that carries both a video id and a
            # playlist/radio id (e.g. YouTube's auto-generated "RD..." mix
            # playlists) makes yt-dlp extract the WHOLE playlist instead of
            # just the one video that was actually linked — observed live
            # as the bot never replying at all (extraction ran long enough
            # it looked hung). Same fix as media_downloader.py's probe/download.
            "noplaylist": True,
        }

    def _download() -> tuple[str, str, bool]:
        # bestvideo+bestaudio/best (not a single fixed format_id): yt-dlp
        # picks the best available quality and muxes video+audio itself
        # (via its own ffmpeg call) — simpler and more robust than manually
        # probing/selecting a single format, since a single video-only
        # format_id would produce a silent file. The explicit re-encode
        # below is what actually guarantees the H.264/CRF profile, not this
        # format selector — this step only needs *a* usable source file.
        try:
            opts = {**_base_opts(), "format": "bestvideo+bestaudio/best"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info), info.get("title") or "video", False
        except yt_dlp.utils.DownloadError as exc:
            if "403" not in str(exc) and "Forbidden" not in str(exc):
                raise
            # The primary attempt can fail partway through an adaptive
            # stream it already started writing (e.g. the video track
            # succeeds, then the audio track 403s) — observed live as
            # orphaned .f*.mp4.part files left behind in the archive dir
            # on every 403. Clear anything under this run's temp_basename
            # before the fallback writes its own file under the same name.
            for leftover in download_dir.glob(f"{temp_basename}*"):
                leftover.unlink(missing_ok=True)

        # YouTube periodically breaks the signed URLs of adaptive (split
        # video+audio) streams while leaving the one remaining progressive
        # format (itag 18, 360p) untouched — observed live (2026-08-18):
        # every bestvideo+bestaudio attempt got HTTP 403 regardless of
        # player_client (web/tv_embedded/android_vr all failed identically
        # even on the latest yt-dlp release), while the "android" client's
        # single progressive format downloaded cleanly. This is YouTube-
        # side, not a stale-yt-dlp problem, and self-resolves on their end
        # eventually — a quality fallback beats a hard failure until then.
        opts = {
            **_base_opts(),
            "format": "best",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info), info.get("title") or "video", True

    try:
        downloaded_path_str, title, degraded_quality = await asyncio.to_thread(_download)
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
    if degraded_quality:
        text += "\n(YouTube сейчас блокирует высокое качество для этого видео — сохранено в 360p)"
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
