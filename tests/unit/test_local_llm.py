from unittest.mock import AsyncMock

import pytest

from app.services.local_llm import NEED_CLOUD_MARKER, LocalLLMClient


@pytest.mark.asyncio
async def test_generate_returns_message_content():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(return_value={"message": {"content": "Привет!"}})

    result = await client.generate("Привет")

    assert result == "Привет!"


@pytest.mark.asyncio
async def test_generate_escalates_to_cloud_on_error():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(side_effect=ConnectionError("unreachable"))

    result = await client.generate("Привет")

    assert result == NEED_CLOUD_MARKER


def test_needs_cloud_detects_marker():
    assert LocalLLMClient.needs_cloud(f"текст {NEED_CLOUD_MARKER}") is True
    assert LocalLLMClient.needs_cloud("обычный ответ") is False
