from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.models.sqlalchemy.showroom_media import ShowroomMedia

_RESULT_LIMIT = 10


def _human_size(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    if mb < 1024:
        return f"{mb:.0f} МБ"
    return f"{mb / 1024:.1f} ГБ"


async def run(query: str) -> ToolResult:
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(ShowroomMedia)
                .where(ShowroomMedia.title.ilike(f"%{query}%"))
                .order_by(ShowroomMedia.created_at.desc())
                .limit(_RESULT_LIMIT)
            )
        ).scalars().all()

    if not rows:
        return ToolResult(text=f"Не нашёл скачанных файлов по «{query}».")

    lines = [f"📁 Найдено по «{query}»:"]
    lines.extend(f"— «{m.title}» ({_human_size(m.file_size_bytes)}) — {m.file_path}" for m in rows)
    return ToolResult(text="\n".join(lines))


TOOL_SPEC = ToolSpec(
    name="find_downloaded_file",
    description=(
        "Ищет уже скачанные видео/файлы в медиатеке по названию и показывает путь к файлу на диске и его "
        "размер — например «где файл про X», «какой путь у скачанного видео Y», «что уже скачано про Z»."
    ),
    parameters=[ToolParameter(name="query", type="string", description="Название или часть названия файла")],
    handler=run,
)
