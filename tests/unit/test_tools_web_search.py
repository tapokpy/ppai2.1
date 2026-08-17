from unittest.mock import AsyncMock, patch

import pytest

from app.services.tools import web_search_tool
from app.services.web_search import WebSearchError


@pytest.mark.asyncio
async def test_run_formats_results():
    spec = web_search_tool.build_tool_spec(api_key="fake-key")
    results = [{"title": "Заголовок", "url": "https://example.com", "snippet": "Описание результата"}]

    with patch("app.services.tools.web_search_tool.search_web", AsyncMock(return_value=results)):
        result = await spec.handler(query="что нового у NovaStar")

    assert result.success is True
    assert "Заголовок" in result.text
    assert "https://example.com" in result.text


@pytest.mark.asyncio
async def test_run_reports_no_results():
    spec = web_search_tool.build_tool_spec(api_key="fake-key")

    with patch("app.services.tools.web_search_tool.search_web", AsyncMock(return_value=[])):
        result = await spec.handler(query="несуществующий запрос")

    assert "Ничего не нашёл" in result.text


@pytest.mark.asyncio
async def test_run_reports_error_instead_of_raising():
    spec = web_search_tool.build_tool_spec(api_key="fake-key")

    with patch(
        "app.services.tools.web_search_tool.search_web",
        AsyncMock(side_effect=WebSearchError("Tavily API вернул ошибку 401.")),
    ):
        result = await spec.handler(query="вопрос")

    assert result.success is False
    assert "401" in result.error


def test_tool_spec_has_query_parameter():
    spec = web_search_tool.build_tool_spec(api_key="fake-key")

    assert [p.name for p in spec.parameters] == ["query"]
