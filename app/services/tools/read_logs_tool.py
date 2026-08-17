from pathlib import Path

from app.core.config import settings
from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec

_VALID_SERVICES = ("bot", "api")
_DEFAULT_LINES = 100
_MAX_LINES = 300


async def run(service: str = "bot", lines: int = _DEFAULT_LINES) -> ToolResult:
    service = (service or "bot").strip().lower()
    if service not in _VALID_SERVICES:
        return ToolResult(
            text=f"Неизвестный сервис «{service}». Доступны: {', '.join(_VALID_SERVICES)}.",
            success=False,
            error="unknown service",
        )

    lines = max(1, min(lines or _DEFAULT_LINES, _MAX_LINES))
    log_path = Path(settings.LOG_STORAGE_PATH) / f"{service}.log"
    if not log_path.exists():
        return ToolResult(text=f"Лог-файл {service}.log ещё не создан — сервис не писал в него ни разу.")

    all_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = all_lines[-lines:]
    if not tail:
        return ToolResult(text=f"Лог {service}.log пустой.")

    return ToolResult(text=f"Последние {len(tail)} строк {service}.log:\n" + "\n".join(tail))


TOOL_SPEC = ToolSpec(
    name="read_logs",
    description=(
        "Читает последние строки логов сервисов Папай (bot или api) — используй, когда "
        "пользователь спрашивает про ошибки, что в логах, что упало/сломалось. "
        "По умолчанию — последние 100 строк лога bot."
    ),
    parameters=[
        ToolParameter(
            name="service",
            type="string",
            description="Какой сервис: 'bot' или 'api'",
            required=False,
        ),
        ToolParameter(
            name="lines",
            type="integer",
            description="Сколько последних строк показать (по умолчанию 100, максимум 300)",
            required=False,
        ),
    ],
    handler=run,
    admin_only=True,
)
