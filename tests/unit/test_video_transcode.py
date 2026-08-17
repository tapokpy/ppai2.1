from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.video_transcode import TranscodeError, transcode_to_h264_mp4


def _fake_process(returncode: int, stderr: bytes = b""):
    process = AsyncMock()
    process.communicate = AsyncMock(return_value=(b"", stderr))
    process.returncode = returncode
    return process


@pytest.mark.asyncio
async def test_transcode_success_does_not_raise():
    with patch(
        "app.services.video_transcode.asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_process(returncode=0)),
    ):
        await transcode_to_h264_mp4(Path("in.webm"), Path("out.mp4"))


@pytest.mark.asyncio
async def test_transcode_raises_on_nonzero_exit():
    with patch(
        "app.services.video_transcode.asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_process(returncode=1, stderr=b"Unknown encoder 'libx264'")),
    ):
        with pytest.raises(TranscodeError, match="libx264"):
            await transcode_to_h264_mp4(Path("in.webm"), Path("out.mp4"))


@pytest.mark.asyncio
async def test_transcode_uses_expected_ffmpeg_flags():
    exec_mock = AsyncMock(return_value=_fake_process(returncode=0))
    with patch("app.services.video_transcode.asyncio.create_subprocess_exec", exec_mock):
        await transcode_to_h264_mp4(Path("in.webm"), Path("out.mp4"))

    args = exec_mock.call_args.args
    assert args[0] == "ffmpeg"
    assert "libx264" in args
    assert "high" in args
    assert "yuv420p" in args
    assert "in.webm" in args
    assert "out.mp4" in args
