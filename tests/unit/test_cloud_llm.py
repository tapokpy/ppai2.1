from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anthropic
import httpx
import pytest

from app.services.cloud_llm import CloudLLMClient, CloudUnavailableError


@pytest.mark.asyncio
async def test_generate_concatenates_text_blocks():
    client = CloudLLMClient(api_key="test-key", model="claude-3-5-sonnet-20241022")

    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Ответ "),
            SimpleNamespace(type="text", text="от Claude"),
        ]
    )
    client._client.messages.create = AsyncMock(return_value=response)

    result = await client.generate("Вопрос")

    assert result == "Ответ от Claude"
    client._client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_includes_context_when_provided():
    client = CloudLLMClient(api_key="test-key", model="claude-3-5-sonnet-20241022")
    create_mock = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])
    )
    client._client.messages.create = create_mock

    await client.generate("Вопрос", context="Справочный контекст")

    sent_content = create_mock.call_args.kwargs["messages"][0]["content"]
    assert "Справочный контекст" in sent_content
    assert "Вопрос" in sent_content


@pytest.mark.asyncio
async def test_generate_raises_cloud_unavailable_on_api_error():
    client = CloudLLMClient(api_key="", model="claude-3-5-sonnet-20241022")
    api_error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    client._client.messages.create = AsyncMock(side_effect=api_error)

    with pytest.raises(CloudUnavailableError):
        await client.generate("Вопрос")


def test_no_proxy_by_default():
    with patch("app.services.cloud_llm.anthropic.AsyncAnthropic") as anthropic_cls:
        CloudLLMClient(api_key="test-key", model="claude-3-5-sonnet-20241022")

    assert anthropic_cls.call_args.kwargs["http_client"] is None


def test_proxy_url_routes_through_http_client():
    with (
        patch("app.services.cloud_llm.anthropic.AsyncAnthropic") as anthropic_cls,
        patch("app.services.cloud_llm.httpx.AsyncClient") as async_client_cls,
    ):
        CloudLLMClient(api_key="test-key", model="claude-3-5-sonnet-20241022", proxy_url="http://gluetun:8888")

    async_client_cls.assert_called_once_with(proxy="http://gluetun:8888")
    assert anthropic_cls.call_args.kwargs["http_client"] is async_client_cls.return_value
