from app.core.tool_registry import ToolAttachment, ToolParameter, ToolResult, ToolSpec
from app.services.media_downloader import MediaDownloadError, MediaDownloader, MediaQuotaError

# Telegram's standard Bot API upload limit (no local Bot API server is
# configured in this deployment) — a tool call has no inline "pick your
# quality" UI like app/bot/handlers/media.py's button flow, so it must pick
# one format on its own; this keeps that automatic pick actually sendable.
_MAX_SENDABLE_BYTES = 50 * 1024 * 1024


def _pick_format(formats: list) -> "object | None":
    """Best quality that still fits under the Telegram upload limit; if none
    fit (or sizes are unknown), falls back to the smallest known format
    rather than silently picking something oversized."""
    if not formats:
        return None

    sized = [f for f in formats if f.filesize_bytes]
    fitting = [f for f in sized if f.filesize_bytes <= _MAX_SENDABLE_BYTES]
    if fitting:
        return max(fitting, key=lambda f: f.filesize_bytes)
    if sized:
        return min(sized, key=lambda f: f.filesize_bytes)
    return formats[0]


def build_tool_spec(downloader: MediaDownloader) -> ToolSpec:
    async def run(url: str) -> ToolResult:
        try:
            probe = await downloader.probe(url)
        except MediaDownloadError as exc:
            return ToolResult(text=f"Не получилось обработать ссылку: {exc}", success=False, error=str(exc))

        chosen = _pick_format(probe.formats)
        if chosen is None:
            error = "Не нашёл видеодорожек по этой ссылке."
            return ToolResult(text=error, success=False, error=error)

        try:
            if chosen.filesize_bytes:
                await downloader.ensure_quota(chosen.filesize_bytes)
            media = await downloader.download(url, chosen.format_id, probe.title)
        except MediaQuotaError as exc:
            return ToolResult(text=f"Не хватает места на диске: {exc}", success=False, error=str(exc))
        except MediaDownloadError as exc:
            return ToolResult(text=f"Загрузка не удалась: {exc}", success=False, error=str(exc))

        return ToolResult(
            text=f"«{media.title}» загружено.",
            attachment=ToolAttachment(file_path=media.file_path, kind="document"),
        )

    return ToolSpec(
        name="download_youtube",
        description="Скачивает видео по ссылке (YouTube и другие поддерживаемые сайты) и отправляет файл пользователю.",
        parameters=[ToolParameter(name="url", type="string", description="Ссылка на видео")],
        handler=run,
    )
