from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.cloud_llm import CloudLLMClient


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
