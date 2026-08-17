from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.models.sqlalchemy.showroom_media import ShowroomMedia

_RESULT_LIMIT = 10
_RECENT_LIMIT = 5


def _human_size(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    if mb < 1024:
        return f"{mb:.0f} МБ"
    return f"{mb / 1024:.1f} ГБ"


async def run(query: str = "") -> ToolResult:
    async with async_session_maker() as session:
        stmt = select(ShowroomMedia)
        if query:
            stmt = stmt.where(ShowroomMedia.title.ilike(f"%{query}%"))
        stmt = stmt.order_by(ShowroomMedia.created_at.desc()).limit(_RESULT_LIMIT if query else _RECENT_LIMIT)
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        text = f"Не нашёл скачанных файлов по «{query}»." if query else "Скачанных файлов пока нет."
        return ToolResult(text=text)

    header = f"📁 Найдено по «{query}»:" if query else "📁 Последние скачанные файлы:"
    lines = [header]
    lines.extend(f"— «{m.title}» ({_human_size(m.file_size_bytes)}) — {m.file_path}" for m in rows)
    return ToolResult(text="\n".join(lines))


TOOL_SPEC = ToolSpec(
    name="find_downloaded_file",
    description=(
        "Показывает уже скачанные видео/файлы и путь к ним на диске — например «где файл про X», "
        "«куда сохранился этот файл», «что мы вообще скачивали», «что скачали недавно». Если пользователь "
        "не назвал конкретное название — вызови без query, вернутся последние скачанные файлы."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description="Название или часть названия файла, если оно известно",
            required=False,
        )
    ],
    handler=run,
)
