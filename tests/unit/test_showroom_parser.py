from unittest.mock import AsyncMock

import pytest

from app.core.showroom_parser import ClipCommand, PresetCommand, parse_showroom_command


@pytest.mark.asyncio
async def test_parses_preset_command():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"type": "preset", "preset": "Ночной режим"}')

    result = await parse_showroom_command("запусти ночной режим", local_llm, ["Экран"], ["Ночной режим"])

    assert result == PresetCommand(preset="Ночной режим")


@pytest.mark.asyncio
async def test_parses_clip_command_with_screen_and_column():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"type": "clip", "screen": "Главный фасад", "column": 3}'
    )

    result = await parse_showroom_command(
        "включи 3 колонку на главном фасаде", local_llm, ["Главный фасад"], []
    )

    assert result == ClipCommand(screen="Главный фасад", column=3)


@pytest.mark.asyncio
async def test_parses_clip_command_with_missing_screen():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"type": "clip", "screen": null, "column": 2}')

    result = await parse_showroom_command("включи 2 колонку", local_llm, ["Главный фасад"], [])

    assert result == ClipCommand(screen=None, column=2)


@pytest.mark.asyncio
async def test_returns_none_for_unparseable_response():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value="не json вообще")

    result = await parse_showroom_command("что-то непонятное", local_llm, [], [])

    assert result is None


@pytest.mark.asyncio
async def test_passes_screens_and_presets_into_system_prompt():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"type": "clip", "screen": null, "column": null}')

    await parse_showroom_command("текст", local_llm, ["Экран А", "Экран Б"], ["Пресет 1"])

    system_prompt = local_llm.generate.call_args.kwargs["system_prompt"]
    assert "Экран А" in system_prompt
    assert "Экран Б" in system_prompt
    assert "Пресет 1" in system_prompt
