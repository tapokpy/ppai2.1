from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.tool_registry import ToolResult, ToolSpec
from app.models.sqlalchemy.project import Project

_RESULT_LIMIT = 20


async def run() -> ToolResult:
    async with async_session_maker() as session:
        projects = (
            await session.execute(select(Project).order_by(Project.created_at.desc()).limit(_RESULT_LIMIT))
        ).scalars().all()

    if not projects:
        return ToolResult(text="Проектов пока нет.")

    lines = [f"#{p.id} «{p.name}»" + (f" — {p.customer}" if p.customer else "") for p in projects]
    return ToolResult(text="\n".join(lines))


TOOL_SPEC = ToolSpec(
    name="list_projects",
    description="Показывает список рабочих проектов (кабинетов) — например «какие у нас проекты», «покажи список проектов».",
    parameters=[],
    handler=run,
)
