import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yt_dlp
from loguru import logger
from sqlalchemy import func, select

from app.core.database import async_session_maker
from app.models.sqlalchemy.showroom_media import ShowroomMedia


class MediaDownloadError(Exception):
    """Raised when yt-dlp can't probe or download a URL — bad link, network
    failure, unsupported site. Callers should show a friendly message
    rather than crash the handler."""


class MediaQuotaError(Exception):
    """Raised when a file won't fit even after freeing every non-pinned
    file in the library — the caller must report this rather than silently
    blocking forever."""


@dataclass
class FormatOption:
    format_id: str
    description: str
    filesize_bytes: int | None


@dataclass
class ProbeResult:
    title: str
    formats: list[FormatOption]


def _human_size(num_bytes: int | None) -> str:
    if not num_bytes:
        return "размер неизвестен"
    mb = num_bytes / (1024 * 1024)
    if mb < 1024:
        return f"{mb:.0f} МБ"
    return f"{mb / 1024:.1f} ГБ"


class MediaDownloader:
    def __init__(self, storage_dir: str, quota_gb: float):
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._quota_bytes = int(quota_gb * 1024 * 1024 * 1024)

    async def probe(self, url: str) -> ProbeResult:
        """Fetches the title and available video formats without
        downloading. Runs the blocking yt-dlp call in a thread so it
        doesn't stall the bot's event loop."""

        def _probe() -> dict:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await asyncio.to_thread(_probe)
        except Exception as exc:
            raise MediaDownloadError(str(exc)) from exc

        formats = info.get("formats") or []
        options = [
            FormatOption(
                format_id=f["format_id"],
                description=f"{f.get('format_note') or f.get('ext', '?')} · "
                f"{_human_size(f.get('filesize') or f.get('filesize_approx'))}",
                filesize_bytes=f.get("filesize") or f.get("filesize_approx"),
            )
            for f in formats
            if f.get("vcodec") not in (None, "none")  # skip audio-only variants
        ]
        return ProbeResult(title=info.get("title") or url, formats=options)

    async def current_usage_bytes(self) -> int:
        async with async_session_maker() as session:
            total = (
                await session.execute(select(func.coalesce(func.sum(ShowroomMedia.file_size_bytes), 0)))
            ).scalar_one()
        return int(total)

    async def ensure_quota(self, needed_bytes: int) -> None:
        """Frees space via LRU cleanup (oldest last_used first, is_pinned
        excluded) until `needed_bytes` fits under the quota. Raises
        MediaQuotaError if it still doesn't fit once every non-pinned file
        is gone — e.g. pinned files alone already exceed the quota."""
        usage = await self.current_usage_bytes()
        if usage + needed_bytes <= self._quota_bytes:
            return

        async with async_session_maker() as session:
            candidates = (
                await session.execute(
                    select(ShowroomMedia)
                    .where(ShowroomMedia.is_pinned.is_(False))
                    .order_by(ShowroomMedia.last_used)
                )
            ).scalars().all()

            freed = 0
            for media in candidates:
                if usage + needed_bytes - freed <= self._quota_bytes:
                    break
                Path(media.file_path).unlink(missing_ok=True)
                freed += media.file_size_bytes
                logger.info(
                    f"Showroom LRU cleanup: removed '{media.title}' ({_human_size(media.file_size_bytes)})"
                )
                await session.delete(media)
            await session.commit()

        if usage + needed_bytes - freed > self._quota_bytes:
            raise MediaQuotaError(
                f"Нужно {_human_size(needed_bytes)}, но после очистки всех незакреплённых "
                f"файлов свободно только {_human_size(self._quota_bytes - usage + freed)}."
            )

    async def download(
        self,
        url: str,
        format_id: str,
        title: str,
        progress_hook: Callable[[dict], None] | None = None,
    ) -> ShowroomMedia:
        destination_template = str(self._storage_dir / "%(id)s.%(ext)s")

        def _run() -> str:
            opts = {
                "format": format_id,
                "outtmpl": destination_template,
                "quiet": True,
                "no_warnings": True,
            }
            if progress_hook:
                opts["progress_hooks"] = [progress_hook]
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        try:
            file_path = await asyncio.to_thread(_run)
        except Exception as exc:
            raise MediaDownloadError(str(exc)) from exc

        size_bytes = Path(file_path).stat().st_size

        async with async_session_maker() as session:
            media = ShowroomMedia(title=title, file_path=file_path, file_size_bytes=size_bytes)
            session.add(media)
            await session.commit()
            await session.refresh(media)
        return media
