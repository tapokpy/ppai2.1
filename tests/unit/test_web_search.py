from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.web_search import WebSearchError, search_web


@pytest.mark.asyncio
async def test_search_raises_when_api_key_missing():
    with pytest.raises(WebSearchError, match="не настроен"):
        await search_web("вопрос", api_key="")


@pytest.mark.asyncio
async def test_search_returns_formatted_results_on_success():
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "results": [
            {"title": "Заголовок 1", "url": "https://example.com/1", "content": "Сниппет 1"},
            {"title": "Заголовок 2", "url": "https://example.com/2", "content": "Сниппет 2"},
        ]
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await search_web("вопрос", api_key="fake-key")

    assert results == [
        {"title": "Заголовок 1", "url": "https://example.com/1", "snippet": "Сниппет 1"},
        {"title": "Заголовок 2", "url": "https://example.com/2", "snippet": "Сниппет 2"},
    ]


@pytest.mark.asyncio
async def test_search_returns_empty_list_when_no_results():
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"results": []}
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await search_web("вопрос", api_key="fake-key")

    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_non_200():
    mock_response = MagicMock(status_code=401)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.web_search.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(WebSearchError, match="401"):
            await search_web("вопрос", api_key="fake-key")


@pytest.mark.asyncio
async def test_search_wraps_network_errors():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.web_search.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(WebSearchError):
            await search_web("вопрос", api_key="fake-key")
