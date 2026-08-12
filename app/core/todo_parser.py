import json
from dataclasses import dataclass
from typing import Any

from app.services.local_llm import LocalLLMClient

LLM_SYSTEM_PROMPT = (
    "Ты помогаешь вести список задач (план доработок) проекта. Извлеки из сообщения "
    "пользователя формулировку задачи и верни строго JSON без пояснений: "
    '{{"title": str, "description": str|null}}. '
    "title — краткая формулировка задачи одним предложением (до 80 символов), "
    "без служебных слов вроде «тодолист3», «план3», «запиши», «добавь». "
    "description — дополнительные детали из сообщения, если они есть, иначе null. "
    "Если в контексте проекта ниже есть релевантная информация (существующие функции, "
    "модули, ограничения), используй её, чтобы сформулировать задачу точнее и конкретнее, "
    "но не выдумывай ничего, чего нет в сообщении пользователя.\n\n"
    "Контекст проекта:\n{project_context}"
)


@dataclass
class ParsedTodo:
    title: str
    description: str | None = None


async def parse_todo_with_llm(
    text: str, local_llm: LocalLLMClient, project_context: str = ""
) -> ParsedTodo:
    raw = await local_llm.generate(
        prompt=text,
        system_prompt=LLM_SYSTEM_PROMPT.format(
            project_context=project_context or "дополнительный контекст отсутствует"
        ),
    )

    data = _try_parse_json(raw)
    if data is None or not str(data.get("title", "")).strip():
        return ParsedTodo(title=text.strip()[:80] or "Новая задача", description=None)

    return ParsedTodo(
        title=str(data["title"]).strip()[:200],
        description=(data.get("description") or None),
    )


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
