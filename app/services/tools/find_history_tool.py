from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.services.history_search import search_messages

_PREVIEW_LEN = 100


def _preview(text: str) -> str:
    return text[:_PREVIEW_LEN] + ("…" if len(text) > _PREVIEW_LEN else "")


async def run(query: str, user_id: int) -> ToolResult:
    matches = await search_messages(user_id, query)

    if not matches:
        return ToolResult(text=f"Ничего не нашёл по «{query}» в вашей истории.")

    lines = [f"🔎 Найдено по «{query}»:"]
    lines.extend(f"— «{_preview(m.prompt)}»\n   → {_preview(m.response)}" for m in matches)
    return ToolResult(text="\n".join(lines))


TOOL_SPEC = ToolSpec(
    name="find_history",
    description=(
        "Ищет по СВОЕЙ прошлой переписке этого пользователя с ботом (его прошлые сообщения и ответы бота на "
        "них) — личная память, а не база знаний. Использовать в том числе для вопросов о себе, если ответ мог "
        "прозвучать раньше в разговоре и сейчас не виден: «как меня зовут», «что я говорил о себе», "
        "«что я спрашивал про X», «напомни, что ты говорил про X», «найди в истории/базе переписки X». "
        "НЕ использовать для обычных вопросов по теме проекта, на которые можно ответить напрямую."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description=(
                "Одно короткое ключевое слово для поиска, а не вся фраза целиком. "
                'Например, для вопроса «как меня зовут» используй query="зовут", а не query="как меня зовут".'
            ),
        )
    ],
    handler=run,
    needs_user_id=True,
)
