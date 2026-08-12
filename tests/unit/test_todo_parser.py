from unittest.mock import AsyncMock

import pytest

from app.core.todo_parser import ParsedTodo, parse_todo_with_llm


@pytest.mark.asyncio
async def test_parses_valid_json_response():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"title": "Доработать расчёт потребления", "description": "Учесть КПД блоков питания"}'
    )

    result = await parse_todo_with_llm("тодолист3 доработать расчёт потребления", local_llm)

    assert result == ParsedTodo(
        title="Доработать расчёт потребления", description="Учесть КПД блоков питания"
    )


@pytest.mark.asyncio
async def test_description_defaults_to_none_when_absent():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"title": "Проверить блоки питания на складе"}')

    result = await parse_todo_with_llm("план3 проверить блоки питания на складе", local_llm)

    assert result.description is None


@pytest.mark.asyncio
async def test_falls_back_to_raw_text_on_invalid_json():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value="это не JSON")

    result = await parse_todo_with_llm("план3 сделать что-то важное", local_llm)

    assert result.title == "план3 сделать что-то важное"
    assert result.description is None


@pytest.mark.asyncio
async def test_falls_back_when_title_missing_or_empty():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"title": "", "description": "детали"}')

    result = await parse_todo_with_llm("план3 текст задачи", local_llm)

    assert result.title == "план3 текст задачи"


@pytest.mark.asyncio
async def test_project_context_is_interpolated_into_system_prompt():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"title": "Задача", "description": null}')

    await parse_todo_with_llm(
        "план3 задача", local_llm, project_context="Модуль power_cables.py считает автоматы"
    )

    system_prompt = local_llm.generate.call_args.kwargs["system_prompt"]
    assert "Модуль power_cables.py считает автоматы" in system_prompt


@pytest.mark.asyncio
async def test_missing_project_context_uses_placeholder():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"title": "Задача", "description": null}')

    await parse_todo_with_llm("план3 задача", local_llm)

    system_prompt = local_llm.generate.call_args.kwargs["system_prompt"]
    assert "дополнительный контекст отсутствует" in system_prompt
