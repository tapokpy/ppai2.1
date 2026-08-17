from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.models.sqlalchemy.audit_log import AuditLog

_RESULT_LIMIT = 10
_PREVIEW_LEN = 100


async def run(user_id: int, query: str = "") -> ToolResult:
    async with async_session_maker() as session:
        stmt = select(AuditLog).where(AuditLog.user_id == user_id)
        if query:
            stmt = stmt.where(AuditLog.command_text.ilike(f"%{query}%"))
        stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(_RESULT_LIMIT)
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        text = f"Ничего не нашёл по «{query}» в недавних действиях." if query else "Недавних действий не найдено."
        return ToolResult(text=text)

    lines = ["🗂 Недавние действия:"]
    for row in rows:
        preview = row.command_text[:_PREVIEW_LEN] + ("…" if len(row.command_text) > _PREVIEW_LEN else "")
        lines.append(f"— «{preview}» → {row.module}/{row.decision} ({row.status})")
    return ToolResult(text="\n".join(lines))


TOOL_SPEC = ToolSpec(
    name="get_recent_activity",
    description=(
        "Показывает недавние действия этого пользователя в системе (что делалось, каким модулем, "
        "успешно или нет) — например «что я недавно делал», «что происходило с проектами». "
        "НЕ база знаний и НЕ история переписки (для истории переписки есть find_history)."
    ),
    parameters=[
        ToolParameter(
            name="query", type="string", description="Ключевое слово для фильтра, необязательно", required=False
        )
    ],
    handler=run,
    needs_user_id=True,
)
