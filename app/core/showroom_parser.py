import json
from dataclasses import dataclass
from typing import Any

from app.services.local_llm import LocalLLMClient

LLM_SYSTEM_PROMPT = (
    "Ты помогаешь управлять видео-шоурумом через Resolume Arena. Разбери команду "
    "пользователя и верни строго JSON без пояснений одного из двух видов:\n"
    '1. Запуск пресета: {{"type": "preset", "preset": str}}\n'
    '2. Запуск ролика на экране: {{"type": "clip", "screen": str|null, "column": int|null}}\n'
    "screen — точное название экрана из списка ниже, если оно явно названо в команде, "
    "иначе null (не выдумывай название, если пользователь его не указал). "
    "column — номер колонки/ролика в Resolume, если указан явно, иначе null.\n\n"
    "Доступные экраны: {screens}\n"
    "Доступные пресеты: {presets}"
)


@dataclass
class PresetCommand:
    preset: str


@dataclass
class ClipCommand:
    screen: str | None
    column: int | None


async def parse_showroom_command(
    text: str, local_llm: LocalLLMClient, screen_names: list[str], preset_names: list[str]
) -> PresetCommand | ClipCommand | None:
    raw = await local_llm.generate(
        prompt=text,
        system_prompt=LLM_SYSTEM_PROMPT.format(
            screens=", ".join(screen_names) or "нет настроенных экранов",
            presets=", ".join(preset_names) or "нет настроенных пресетов",
        ),
    )

    data = _try_parse_json(raw)
    if data is None:
        return None

    if data.get("type") == "preset" and data.get("preset"):
        return PresetCommand(preset=str(data["preset"]))

    if data.get("type") == "clip":
        return ClipCommand(screen=_as_str_or_none(data.get("screen")), column=_as_int_or_none(data.get("column")))

    return None


def _as_str_or_none(value: Any) -> str | None:
    return str(value) if value else None


def _as_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
