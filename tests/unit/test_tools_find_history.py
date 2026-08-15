from unittest.mock import AsyncMock, patch

import pytest

from app.services.tools import find_history_tool


@pytest.mark.asyncio
async def test_run_formats_matches():
    fake_message = type("M", (), {"prompt": "какой шаг пикселя у P2.5?", "response": "2.5 мм"})()
    with patch("app.services.tools.find_history_tool.search_messages", AsyncMock(return_value=[fake_message])):
        result = await find_history_tool.run(query="P2.5", user_id=7)

    assert result.success is True
    assert "P2.5" in result.text
    assert "2.5 мм" in result.text


@pytest.mark.asyncio
async def test_run_reports_no_matches():
    with patch("app.services.tools.find_history_tool.search_messages", AsyncMock(return_value=[])):
        result = await find_history_tool.run(query="несуществующее", user_id=7)

    assert "Ничего не нашёл" in result.text


@pytest.mark.asyncio
async def test_run_scopes_search_to_given_user_id():
    search_mock = AsyncMock(return_value=[])
    with patch("app.services.tools.find_history_tool.search_messages", search_mock):
        await find_history_tool.run(query="X", user_id=42)

    search_mock.assert_awaited_once_with(42, "X")


def test_tool_spec_needs_user_id():
    assert find_history_tool.TOOL_SPEC.needs_user_id is True
