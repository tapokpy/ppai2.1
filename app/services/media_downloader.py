import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

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


@dataclass
class DownloadOutcome:
    media: ShowroomMedia
    # True when the caller's chosen format_id 403'd and download() had to
    # retry with the guaranteed-working 360p fallback (see download()) —
    # callers should tell the user their picked quality wasn't honored,
    # not silently hand back a lower-res file under the quality they asked for.
    degraded_quality: bool


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
            # noplaylist=True — without it, a URL that carries both a video
            # id and a playlist/radio id (e.g. YouTube's auto-generated
            # "RD..." mix playlists, which can be dozens of videos or
            # effectively unbounded) makes yt-dlp extract the WHOLE
            # playlist instead of just the one video the user actually
            # linked — observed live as the bot never replying at all
            # (extraction ran long enough it looked hung). The user sent
            # one link, they meant one video.
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
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
    ) -> DownloadOutcome:
        # A per-call temp name (not the final "%(id)s.%(ext)s" convention)
        # so a 403 partway through can be cleaned up by glob before the
        # fallback retry writes under the same name — the final id isn't
        # known until extract_info() succeeds, so there'd otherwise be
        # nothing to scope a cleanup glob to. Renamed to the real
        # "{id}.{ext}" convention (unchanged for every other caller) once
        # a download actually succeeds.
        temp_basename = f".tmp_{uuid4().hex}"

        def _base_opts() -> dict:
            opts: dict = {
                "outtmpl": str(self._storage_dir / temp_basename) + ".%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            if progress_hook:
                opts["progress_hooks"] = [progress_hook]
            return opts

        def _run() -> tuple[str, str, bool]:
            try:
                opts = {**_base_opts(), "format": format_id}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return ydl.prepare_filename(info), info.get("id") or temp_basename.lstrip("."), False
            except yt_dlp.utils.DownloadError as exc:
                if "403" not in str(exc) and "Forbidden" not in str(exc):
                    raise
                # The chosen format can 403 partway through (e.g. the video
                # track downloads fine, the audio track doesn't) — clear
                # anything this call wrote under its own temp_basename
                # before the fallback writes its own file under the same
                # name. Scoped to temp_basename specifically, not to
                # every *.part file, since handle_format_choice
                # (app/bot/handlers/media.py) fires downloads as bare
                # asyncio.create_task calls with no lock — several
                # downloads can be in flight at once, and a broader glob
                # risks deleting another concurrent download's legitimate
                # partial file.
                for leftover in self._storage_dir.glob(f"{temp_basename}*"):
                    leftover.unlink(missing_ok=True)

            # YouTube periodically breaks the signed URLs of adaptive
            # (split video+audio) streams while leaving the one remaining
            # progressive format (itag 18, 360p) untouched — same root
            # cause and fallback as download_youtube_tool.py's _download().
            # The format the user picked from the quality buttons is no
            # longer obtainable once it's 403'd, so retry with "best"
            # instead of the same format_id.
            opts = {
                **_base_opts(),
                "format": "best",
                "extractor_args": {"youtube": {"player_client": ["android"]}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info), info.get("id") or temp_basename.lstrip("."), True

        try:
            temp_path_str, video_id, degraded_quality = await asyncio.to_thread(_run)
        except Exception as exc:
            raise MediaDownloadError(str(exc)) from exc

        temp_path = Path(temp_path_str)
        final_path = self._storage_dir / f"{video_id}{temp_path.suffix}"
        temp_path.replace(final_path)

        size_bytes = final_path.stat().st_size

        async with async_session_maker() as session:
            media = ShowroomMedia(title=title, file_path=str(final_path), file_size_bytes=size_bytes)
            session.add(media)
            await session.commit()
            await session.refresh(media)
        return DownloadOutcome(media=media, degraded_quality=degraded_quality)
