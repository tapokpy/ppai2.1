from unittest.mock import AsyncMock

import pytest

from app.core.cad_command_parser import DrawingRequest, parse_cad_command


@pytest.mark.asyncio
async def test_parses_frame_request_with_dimensions():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"shape": "frame", "width": 1000, "height": 500, "project_name": null}'
    )

    result = await parse_cad_command("создай чертеж рамки 1000х500", local_llm)

    assert result == DrawingRequest(shape="frame", width=1000.0, height=500.0, project_name=None)


@pytest.mark.asyncio
async def test_parses_plate_request_with_project_name():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value='{"shape": "plate", "width": 200, "height": 100, "project_name": "Крепление А"}'
    )

    result = await parse_cad_command("пластина 200 на 100 для проекта Крепление А", local_llm)

    assert result.shape == "plate"
    assert result.project_name == "Крепление А"


@pytest.mark.asyncio
async def test_returns_none_shape_when_unclear():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"shape": null, "width": null, "height": null, "project_name": null}')

    result = await parse_cad_command("что-то про чертёж", local_llm)

    assert result.shape is None


@pytest.mark.asyncio
async def test_returns_none_for_unparseable_response():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value="не json")

    result = await parse_cad_command("бла бла", local_llm)

    assert result is None


@pytest.mark.asyncio
async def test_mentions_supported_shapes_in_system_prompt():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value='{"shape": null, "width": null, "height": null, "project_name": null}')

    await parse_cad_command("текст", local_llm)

    system_prompt = local_llm.generate.call_args.kwargs["system_prompt"]
    assert "frame" in system_prompt
    assert "plate" in system_prompt
