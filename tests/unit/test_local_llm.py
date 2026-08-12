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
async def test_generate_passes_generation_options_to_ollama():
    client = LocalLLMClient(
        base_url="http://localhost:11434",
        model="qwen2.5:7b",
        temperature=0.2,
        top_p=0.8,
        top_k=30,
        repeat_penalty=1.2,
        num_predict=256,
    )
    client._client.chat = AsyncMock(return_value={"message": {"content": "ответ"}})

    await client.generate("Привет")

    call_kwargs = client._client.chat.call_args.kwargs
    assert call_kwargs["options"] == {
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 30,
        "repeat_penalty": 1.2,
        "num_predict": 256,
    }


@pytest.mark.asyncio
async def test_generate_uses_lower_temperature_defaults():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(return_value={"message": {"content": "ответ"}})

    await client.generate("Привет")

    call_kwargs = client._client.chat.call_args.kwargs
    assert call_kwargs["options"]["temperature"] == 0.35
    assert call_kwargs["options"]["top_p"] == 0.85


@pytest.mark.asyncio
async def test_generate_with_usage_returns_token_counts():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(
        return_value={
            "message": {"content": "ответ"},
            "prompt_eval_count": 120,
            "eval_count": 45,
        }
    )

    text, usage = await client.generate_with_usage("Привет")

    assert text == "ответ"
    assert usage == {"prompt_tokens": 120, "completion_tokens": 45}


@pytest.mark.asyncio
async def test_generate_with_usage_returns_empty_usage_on_failure():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(side_effect=ConnectionError("unreachable"))

    text, usage = await client.generate_with_usage("Привет")

    assert text == NEED_CLOUD_MARKER
    assert usage == {}


@pytest.mark.asyncio
async def test_generate_escalates_to_cloud_on_error():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(side_effect=ConnectionError("unreachable"))

    result = await client.generate("Привет")

    assert result == NEED_CLOUD_MARKER


def test_needs_cloud_detects_marker():
    assert LocalLLMClient.needs_cloud(f"текст {NEED_CLOUD_MARKER}") is True
    assert LocalLLMClient.needs_cloud("обычный ответ") is False
