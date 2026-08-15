from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.media_downloader import FormatOption, MediaDownloadError, MediaQuotaError, ProbeResult
from app.services.tools import download_youtube_tool


def _downloader(probe_result=None, probe_error=None, download_error=None, quota_error=None):
    downloader = MagicMock()
    if probe_error:
        downloader.probe = AsyncMock(side_effect=probe_error)
    else:
        downloader.probe = AsyncMock(return_value=probe_result)
    downloader.ensure_quota = AsyncMock(side_effect=quota_error) if quota_error else AsyncMock()
    if download_error:
        downloader.download = AsyncMock(side_effect=download_error)
    else:
        downloader.download = AsyncMock(
            return_value=SimpleNamespace(title="Видео", file_path="/data/media/abc.mp4")
        )
    return downloader


@pytest.mark.asyncio
async def test_run_downloads_and_returns_attachment():
    probe = ProbeResult(
        title="Видео",
        formats=[
            FormatOption(format_id="best", description="1080p · 30 МБ", filesize_bytes=30 * 1024 * 1024),
            FormatOption(format_id="worst", description="360p · 5 МБ", filesize_bytes=5 * 1024 * 1024),
        ],
    )
    downloader = _downloader(probe_result=probe)
    spec = download_youtube_tool.build_tool_spec(downloader)

    result = await spec.handler(url="https://youtu.be/abc")

    assert result.success is True
    assert result.attachment.file_path == "/data/media/abc.mp4"
    downloader.download.assert_awaited_once_with("https://youtu.be/abc", "best", "Видео")


@pytest.mark.asyncio
async def test_run_reports_error_when_probe_fails():
    downloader = _downloader(probe_error=MediaDownloadError("сайт не поддерживается"))
    spec = download_youtube_tool.build_tool_spec(downloader)

    result = await spec.handler(url="https://example.com/x")

    assert result.success is False
    assert "не поддерживается" in result.error


@pytest.mark.asyncio
async def test_run_reports_error_when_no_formats_available():
    downloader = _downloader(probe_result=ProbeResult(title="Видео", formats=[]))
    spec = download_youtube_tool.build_tool_spec(downloader)

    result = await spec.handler(url="https://youtu.be/abc")

    assert result.success is False


@pytest.mark.asyncio
async def test_run_reports_quota_error():
    probe = ProbeResult(
        title="Видео", formats=[FormatOption(format_id="best", description="x", filesize_bytes=10 * 1024 * 1024)]
    )
    downloader = _downloader(probe_result=probe, quota_error=MediaQuotaError("не хватает места"))
    spec = download_youtube_tool.build_tool_spec(downloader)

    result = await spec.handler(url="https://youtu.be/abc")

    assert result.success is False
    assert "места" in result.error


def test_pick_format_prefers_best_quality_under_telegram_limit():
    formats = [
        FormatOption(format_id="huge", description="4K", filesize_bytes=200 * 1024 * 1024),
        FormatOption(format_id="fits", description="720p", filesize_bytes=40 * 1024 * 1024),
        FormatOption(format_id="small", description="360p", filesize_bytes=5 * 1024 * 1024),
    ]

    chosen = download_youtube_tool._pick_format(formats)

    assert chosen.format_id == "fits"


def test_pick_format_falls_back_to_smallest_when_all_oversized():
    formats = [
        FormatOption(format_id="huge", description="4K", filesize_bytes=200 * 1024 * 1024),
        FormatOption(format_id="less_huge", description="1080p", filesize_bytes=100 * 1024 * 1024),
    ]

    chosen = download_youtube_tool._pick_format(formats)

    assert chosen.format_id == "less_huge"


def test_pick_format_falls_back_to_first_when_sizes_unknown():
    formats = [FormatOption(format_id="only", description="?", filesize_bytes=None)]

    assert download_youtube_tool._pick_format(formats).format_id == "only"


def test_pick_format_returns_none_for_empty_list():
    assert download_youtube_tool._pick_format([]) is None
