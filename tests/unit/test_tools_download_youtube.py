from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yt_dlp

from app.core.tool_registry import ToolAttachment
from app.services.tools import download_youtube_tool
from app.services.video_transcode import TranscodeError


def _fake_ydl(info: dict, prepared_filename: str) -> MagicMock:
    ydl = MagicMock()
    ydl.__enter__ = MagicMock(return_value=ydl)
    ydl.__exit__ = MagicMock(return_value=False)
    ydl.extract_info.return_value = info
    ydl.prepare_filename.return_value = prepared_filename
    return ydl


class _FakeSessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_args):
        return False


def _fake_session():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_run_downloads_transcodes_and_saves(tmp_path):
    downloaded_source = tmp_path / ".tmp_abc.mp4"
    downloaded_source.write_bytes(b"fake source video")
    ydl = _fake_ydl(info={"title": "Крутое видео"}, prepared_filename=str(downloaded_source))

    async def fake_transcode(_input_path, output_path):
        Path(output_path).write_bytes(b"fake transcoded video")

    session = _fake_session()

    with (
        patch("app.services.tools.download_youtube_tool.settings.DOWNLOAD_STORAGE_PATH", str(tmp_path)),
        patch("app.services.tools.download_youtube_tool.yt_dlp.YoutubeDL", return_value=ydl) as ydl_ctor,
        patch("app.services.tools.download_youtube_tool.transcode_to_h264_mp4", fake_transcode),
        patch("app.services.tools.download_youtube_tool.async_session_maker", lambda: _FakeSessionCtx(session)),
    ):
        result = await download_youtube_tool.run(url="https://youtu.be/abc")

    assert result.success is True
    assert "Крутое видео" in result.text
    assert isinstance(result.attachment, ToolAttachment)
    saved_path = Path(result.attachment.file_path)
    assert saved_path.exists()
    assert saved_path.name == "Крутое видео.mp4"
    assert not downloaded_source.exists()
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    # A URL with both a video id and a playlist/radio id must extract just
    # that one video, not the whole (potentially unbounded) playlist.
    assert ydl_ctor.call_args.args[0]["noplaylist"] is True


@pytest.mark.asyncio
async def test_run_falls_back_to_android_360p_on_403(tmp_path):
    downloaded_source = tmp_path / ".tmp_abc.mp4"
    downloaded_source.write_bytes(b"fake source video")

    failing_ydl = MagicMock()
    failing_ydl.__enter__ = MagicMock(return_value=failing_ydl)
    failing_ydl.__exit__ = MagicMock(return_value=False)
    failing_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
        "ERROR: unable to download video data: HTTP Error 403: Forbidden"
    )
    succeeding_ydl = _fake_ydl(info={"title": "Крутое видео"}, prepared_filename=str(downloaded_source))

    async def fake_transcode(_input_path, output_path):
        Path(output_path).write_bytes(b"fake transcoded video")

    session = _fake_session()

    with (
        patch("app.services.tools.download_youtube_tool.settings.DOWNLOAD_STORAGE_PATH", str(tmp_path)),
        patch(
            "app.services.tools.download_youtube_tool.yt_dlp.YoutubeDL",
            side_effect=[failing_ydl, succeeding_ydl],
        ) as ydl_ctor,
        patch("app.services.tools.download_youtube_tool.transcode_to_h264_mp4", fake_transcode),
        patch("app.services.tools.download_youtube_tool.async_session_maker", lambda: _FakeSessionCtx(session)),
    ):
        result = await download_youtube_tool.run(url="https://youtu.be/abc")

    assert result.success is True
    assert "Крутое видео" in result.text
    assert "360p" in result.text
    assert ydl_ctor.call_count == 2
    fallback_opts = ydl_ctor.call_args_list[1].args[0]
    assert fallback_opts["extractor_args"] == {"youtube": {"player_client": ["android"]}}
    assert fallback_opts["format"] == "best"


@pytest.mark.asyncio
async def test_run_cleans_up_orphaned_partial_before_fallback(tmp_path):
    # The primary attempt can fail partway through an adaptive stream it
    # already started writing (e.g. video track succeeds, audio track
    # 403s) — this simulates that leftover .part file and checks the
    # fallback path clears it instead of leaving it as permanent clutter.
    fixed_uuid = MagicMock(hex="deadbeef")
    leftover = tmp_path / ".tmp_deadbeef.f401.mp4.part"
    leftover.write_bytes(b"orphaned partial video track")

    downloaded_source = tmp_path / ".tmp_deadbeef.mp4"
    downloaded_source.write_bytes(b"fake source video")

    failing_ydl = MagicMock()
    failing_ydl.__enter__ = MagicMock(return_value=failing_ydl)
    failing_ydl.__exit__ = MagicMock(return_value=False)
    failing_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
        "ERROR: unable to download video data: HTTP Error 403: Forbidden"
    )
    succeeding_ydl = _fake_ydl(info={"title": "Крутое видео"}, prepared_filename=str(downloaded_source))

    async def fake_transcode(_input_path, output_path):
        Path(output_path).write_bytes(b"fake transcoded video")

    session = _fake_session()

    with (
        patch("app.services.tools.download_youtube_tool.settings.DOWNLOAD_STORAGE_PATH", str(tmp_path)),
        patch("app.services.tools.download_youtube_tool.uuid4", return_value=fixed_uuid),
        patch(
            "app.services.tools.download_youtube_tool.yt_dlp.YoutubeDL",
            side_effect=[failing_ydl, succeeding_ydl],
        ),
        patch("app.services.tools.download_youtube_tool.transcode_to_h264_mp4", fake_transcode),
        patch("app.services.tools.download_youtube_tool.async_session_maker", lambda: _FakeSessionCtx(session)),
    ):
        result = await download_youtube_tool.run(url="https://youtu.be/abc")

    assert result.success is True
    assert not leftover.exists()


@pytest.mark.asyncio
async def test_run_does_not_fall_back_on_non_403_download_error(tmp_path):
    failing_ydl = MagicMock()
    failing_ydl.__enter__ = MagicMock(return_value=failing_ydl)
    failing_ydl.__exit__ = MagicMock(return_value=False)
    failing_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
        "ERROR: [youtube] abc: Video unavailable"
    )

    with (
        patch("app.services.tools.download_youtube_tool.settings.DOWNLOAD_STORAGE_PATH", str(tmp_path)),
        patch(
            "app.services.tools.download_youtube_tool.yt_dlp.YoutubeDL",
            return_value=failing_ydl,
        ) as ydl_ctor,
    ):
        result = await download_youtube_tool.run(url="https://youtu.be/abc")

    assert result.success is False
    assert "Video unavailable" in result.error
    assert ydl_ctor.call_count == 1


@pytest.mark.asyncio
async def test_run_reports_error_when_download_fails(tmp_path):
    with (
        patch("app.services.tools.download_youtube_tool.settings.DOWNLOAD_STORAGE_PATH", str(tmp_path)),
        patch(
            "app.services.tools.download_youtube_tool.yt_dlp.YoutubeDL",
            side_effect=RuntimeError("сайт не поддерживается"),
        ),
    ):
        result = await download_youtube_tool.run(url="https://example.com/x")

    assert result.success is False
    assert "не поддерживается" in result.error


@pytest.mark.asyncio
async def test_run_reports_error_when_transcode_fails_and_cleans_up_temp(tmp_path):
    downloaded_source = tmp_path / ".tmp_abc.webm"
    downloaded_source.write_bytes(b"fake source video")
    ydl = _fake_ydl(info={"title": "Видео"}, prepared_filename=str(downloaded_source))

    async def failing_transcode(_input_path, _output_path):
        raise TranscodeError("ffmpeg завершился с ошибкой: boom")

    with (
        patch("app.services.tools.download_youtube_tool.settings.DOWNLOAD_STORAGE_PATH", str(tmp_path)),
        patch("app.services.tools.download_youtube_tool.yt_dlp.YoutubeDL", return_value=ydl),
        patch("app.services.tools.download_youtube_tool.transcode_to_h264_mp4", failing_transcode),
    ):
        result = await download_youtube_tool.run(url="https://youtu.be/abc")

    assert result.success is False
    assert "ffmpeg" in result.error
    assert not downloaded_source.exists()


@pytest.mark.asyncio
async def test_run_skips_attachment_for_oversized_file(tmp_path):
    downloaded_source = tmp_path / ".tmp_abc.mp4"
    downloaded_source.write_bytes(b"fake source video")
    ydl = _fake_ydl(info={"title": "Большое видео"}, prepared_filename=str(downloaded_source))

    async def fake_transcode(_input_path, output_path):
        # 51 MB — over the 50 MB Telegram upload limit.
        Path(output_path).write_bytes(b"0" * (51 * 1024 * 1024))

    session = _fake_session()

    with (
        patch("app.services.tools.download_youtube_tool.settings.DOWNLOAD_STORAGE_PATH", str(tmp_path)),
        patch("app.services.tools.download_youtube_tool.yt_dlp.YoutubeDL", return_value=ydl),
        patch("app.services.tools.download_youtube_tool.transcode_to_h264_mp4", fake_transcode),
        patch("app.services.tools.download_youtube_tool.async_session_maker", lambda: _FakeSessionCtx(session)),
    ):
        result = await download_youtube_tool.run(url="https://youtu.be/abc")

    assert result.success is True
    assert result.attachment is None
    assert "50 МБ" in result.text


def test_sanitize_filename_strips_unsafe_characters():
    assert download_youtube_tool._sanitize_filename('a:b"c<d>e|f?g*h') == "a_b_c_d_e_f_g_h"


def test_sanitize_filename_strips_slashes():
    assert download_youtube_tool._sanitize_filename("AC/DC live") == "AC_DC live"


def test_sanitize_filename_falls_back_when_empty():
    assert download_youtube_tool._sanitize_filename("   ...   ") == "video"


def test_sanitize_filename_truncates_long_titles():
    long_title = "а" * 300
    assert len(download_youtube_tool._sanitize_filename(long_title)) == 150
