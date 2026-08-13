import json
from dataclasses import dataclass
from typing import Any

from app.services.cad_parser import SUPPORTED_SHAPES
from app.services.local_llm import LocalLLMClient

LLM_SYSTEM_PROMPT = (
    "Ты помогаешь генерировать простые технические чертежи. Разбери запрос "
    "пользователя и верни строго JSON без пояснений: "
    '{{"shape": str|null, "width": number|null, "height": number|null, "project_name": str|null}}\n'
    "shape — один из: {shapes}, или null, если не указано/неясно. "
    "width/height — размеры в миллиметрах, если явно указаны в запросе, иначе null. "
    "project_name — короткое название для файла, если явно указано, иначе null."
)


@dataclass
class DrawingRequest:
    shape: str | None
    width: float | None
    height: float | None
    project_name: str | None


async def parse_cad_command(text: str, local_llm: LocalLLMClient) -> DrawingRequest | None:
    raw = await local_llm.generate(
        prompt=text, system_prompt=LLM_SYSTEM_PROMPT.format(shapes=", ".join(SUPPORTED_SHAPES))
    )

    data = _try_parse_json(raw)
    if data is None:
        return None

    return DrawingRequest(
        shape=_as_str_or_none(data.get("shape")),
        width=_as_float_or_none(data.get("width")),
        height=_as_float_or_none(data.get("height")),
        project_name=_as_str_or_none(data.get("project_name")),
    )


def _as_str_or_none(value: Any) -> str | None:
    return str(value) if value else None


def _as_float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
