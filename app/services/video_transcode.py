import asyncio
from pathlib import Path


class TranscodeError(Exception):
    pass


async def transcode_to_h264_mp4(input_path: Path, output_path: Path) -> None:
    """Re-encodes to a fixed archival profile — H.264 High, CRF 18
    (visually lossless), yuv420p (no alpha channel), AAC audio — regardless
    of whatever container/codec the source actually used. Per explicit user
    spec ("MP4, H.264 High bitrate No Alpha"): the guarantee needs to hold
    for every download, not just ones where yt-dlp happened to already
    serve H.264. ffmpeg is already installed in the bot image (Dockerfile.bot,
    originally for yt-dlp's own internal audio+video muxing) — this is a
    second, explicit invocation on top of that, not a new dependency.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", "libx264", "-profile:v", "high", "-crf", "18", "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise TranscodeError(f"ffmpeg завершился с ошибкой: {stderr.decode(errors='replace')[-500:]}")
