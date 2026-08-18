from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.sqlalchemy.showroom_media import ShowroomMedia
from app.services.media_downloader import (
    MediaDownloadError,
    MediaDownloader,
    MediaQuotaError,
)
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_media(title: str, size_bytes: int, is_pinned: bool = False, last_used_offset_days: int = 0) -> ShowroomMedia:
    async with async_session_maker() as session:
        media = ShowroomMedia(
            title=title,
            file_path=f"/app/data/media/{title}.mp4",
            file_size_bytes=size_bytes,
            is_pinned=is_pinned,
            last_used=datetime.now(timezone.utc) - timedelta(days=last_used_offset_days),
        )
        session.add(media)
        await session.commit()
        await session.refresh(media)
    return media


@pytest.mark.asyncio
async def test_probe_returns_title_and_video_formats(tmp_path):
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    fake_info = {
        "title": "Тестовое видео",
        "formats": [
            {"format_id": "137", "format_note": "1080p", "ext": "mp4", "filesize": 50_000_000, "vcodec": "avc1"},
            {"format_id": "251", "format_note": "audio", "ext": "webm", "filesize": 3_000_000, "vcodec": "none"},
        ],
    }
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = fake_info

    with patch("app.services.media_downloader.yt_dlp.YoutubeDL", return_value=mock_ydl):
        result = await downloader.probe("https://example.com/watch?v=abc")

    assert result.title == "Тестовое видео"
    assert len(result.formats) == 1  # audio-only variant excluded
    assert result.formats[0].format_id == "137"


@pytest.mark.asyncio
async def test_probe_disables_playlist_extraction(tmp_path):
    # A URL with both a video id and a playlist/radio id (e.g. YouTube's
    # auto-generated "RD..." mix playlists) must extract just that one
    # video, not the whole (potentially unbounded) playlist.
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = {"title": "x", "formats": []}

    with patch("app.services.media_downloader.yt_dlp.YoutubeDL", return_value=mock_ydl) as ydl_ctor:
        await downloader.probe("https://example.com/watch?v=abc&list=RDabc&start_radio=1")

    assert ydl_ctor.call_args.args[0]["noplaylist"] is True


@pytest.mark.asyncio
async def test_probe_raises_media_download_error_on_failure(tmp_path):
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.side_effect = Exception("Unsupported URL")

    with patch("app.services.media_downloader.yt_dlp.YoutubeDL", return_value=mock_ydl):
        with pytest.raises(MediaDownloadError):
            await downloader.probe("https://not-a-real-site.example/video")


@pytest.mark.asyncio
async def test_current_usage_bytes_sums_stored_media(clean_db, tmp_path):
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    await _seed_media("a", 1000)
    await _seed_media("b", 2000)

    usage = await downloader.current_usage_bytes()

    assert usage == 3000


@pytest.mark.asyncio
async def test_ensure_quota_noop_when_space_available(clean_db, tmp_path):
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    await _seed_media("a", 1000)

    await downloader.ensure_quota(needed_bytes=1000)  # should not raise

    async with async_session_maker() as session:
        remaining = (await session.execute(select(ShowroomMedia))).scalars().all()
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_ensure_quota_removes_oldest_unpinned_files_first(clean_db, tmp_path):
    quota_bytes = 10 * 1024 * 1024  # 10 MiB quota
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=quota_bytes / (1024 * 1024 * 1024))

    old_file = tmp_path / "old.mp4"
    old_file.write_bytes(b"x")
    new_file = tmp_path / "new.mp4"
    new_file.write_bytes(b"x")

    async with async_session_maker() as session:
        old_media = ShowroomMedia(
            title="old", file_path=str(old_file), file_size_bytes=8 * 1024 * 1024,
            last_used=datetime.now(timezone.utc) - timedelta(days=5),
        )
        new_media = ShowroomMedia(
            title="new", file_path=str(new_file), file_size_bytes=1 * 1024 * 1024,
            last_used=datetime.now(timezone.utc),
        )
        session.add_all([old_media, new_media])
        await session.commit()

    # Need 5 MiB more — only the older file needs to go.
    await downloader.ensure_quota(needed_bytes=5 * 1024 * 1024)

    async with async_session_maker() as session:
        remaining_titles = {m.title for m in (await session.execute(select(ShowroomMedia))).scalars().all()}

    assert remaining_titles == {"new"}
    assert not old_file.exists()
    assert new_file.exists()


@pytest.mark.asyncio
async def test_ensure_quota_never_removes_pinned_files(clean_db, tmp_path):
    quota_bytes = 5 * 1024 * 1024
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=quota_bytes / (1024 * 1024 * 1024))

    pinned_file = tmp_path / "pinned.mp4"
    pinned_file.write_bytes(b"x")

    async with async_session_maker() as session:
        session.add(
            ShowroomMedia(
                title="pinned", file_path=str(pinned_file), file_size_bytes=5 * 1024 * 1024, is_pinned=True,
            )
        )
        await session.commit()

    with pytest.raises(MediaQuotaError):
        await downloader.ensure_quota(needed_bytes=1 * 1024 * 1024)

    assert pinned_file.exists()


@pytest.mark.asyncio
async def test_download_saves_file_and_db_row(clean_db, tmp_path):
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    expected_path = tmp_path / "video123.mp4"

    def _fake_extract_info(url, download):
        expected_path.write_bytes(b"fake video content")
        return {"id": "video123", "ext": "mp4"}

    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.side_effect = _fake_extract_info
    mock_ydl.__enter__.return_value.prepare_filename.return_value = str(expected_path)

    with patch("app.services.media_downloader.yt_dlp.YoutubeDL", return_value=mock_ydl):
        media = await downloader.download("https://example.com/watch?v=video123", "137", "Тестовое видео")

    assert media.title == "Тестовое видео"
    assert media.file_size_bytes == len(b"fake video content")

    async with async_session_maker() as session:
        stored = (await session.execute(select(ShowroomMedia))).scalars().all()
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_download_disables_playlist_extraction(clean_db, tmp_path):
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    expected_path = tmp_path / "video123.mp4"

    def _fake_extract_info(url, download):
        expected_path.write_bytes(b"fake video content")
        return {"id": "video123", "ext": "mp4"}

    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.side_effect = _fake_extract_info
    mock_ydl.__enter__.return_value.prepare_filename.return_value = str(expected_path)

    with patch("app.services.media_downloader.yt_dlp.YoutubeDL", return_value=mock_ydl) as ydl_ctor:
        await downloader.download(
            "https://example.com/watch?v=video123&list=RDvideo123&start_radio=1", "137", "title"
        )

    assert ydl_ctor.call_args.args[0]["noplaylist"] is True


@pytest.mark.asyncio
async def test_download_raises_media_download_error_on_failure(clean_db, tmp_path):
    downloader = MediaDownloader(storage_dir=str(tmp_path), quota_gb=100)
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.side_effect = Exception("network error")

    with patch("app.services.media_downloader.yt_dlp.YoutubeDL", return_value=mock_ydl):
        with pytest.raises(MediaDownloadError):
            await downloader.download("https://example.com/watch?v=x", "137", "title")
