from unittest.mock import AsyncMock

import pytest

from app.services.local_llm import NEED_CLOUD_MARKER, LocalLLMClient


@pytest.mark.asyncio
async def test_generate_returns_message_content():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(return_value={"message": {"content": "Привет!"}})

    result = await client.generate("Привет")

    assert result == "Привет!"


def test_model_name_is_exposed():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")

    assert client.model_name == "qwen2.5:7b"


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


@pytest.mark.asyncio
async def test_generate_with_usage_inserts_history_between_system_and_prompt():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(return_value={"message": {"content": "ответ"}})
    history = [
        {"role": "user", "content": "меня зовут Коля"},
        {"role": "assistant", "content": "Приятно познакомиться, Коля!"},
    ]

    await client.generate_with_usage("как меня зовут?", system_prompt="Ты ассистент.", history=history)

    messages = client._client.chat.call_args.kwargs["messages"]
    assert messages == [
        {"role": "system", "content": "Ты ассистент."},
        {"role": "user", "content": "меня зовут Коля"},
        {"role": "assistant", "content": "Приятно познакомиться, Коля!"},
        {"role": "user", "content": "как меня зовут?"},
    ]


@pytest.mark.asyncio
async def test_generate_with_tools_passes_tools_schema_to_ollama():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(return_value={"message": {"content": "", "tool_calls": []}})
    tools = [{"type": "function", "function": {"name": "calculate_power"}}]

    await client.generate_with_tools("посчитай", tools=tools, system_prompt="Ты ассистент.")

    call_kwargs = client._client.chat.call_args.kwargs
    assert call_kwargs["tools"] == tools
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "Ты ассистент."},
        {"role": "user", "content": "посчитай"},
    ]


@pytest.mark.asyncio
async def test_generate_with_tools_normalizes_tool_call_response():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(
        return_value={
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "calculate_power", "arguments": {"module_count": 20}}}],
            },
            "prompt_eval_count": 100,
            "eval_count": 10,
        }
    )

    text, tool_calls, usage = await client.generate_with_tools("посчитай", tools=[{}])

    assert text == ""
    assert tool_calls == [{"name": "calculate_power", "arguments": {"module_count": 20}}]
    assert usage == {"prompt_tokens": 100, "completion_tokens": 10}


@pytest.mark.asyncio
async def test_generate_with_tools_returns_empty_tool_calls_for_plain_answer():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(return_value={"message": {"content": "Привет!", "tool_calls": None}})

    text, tool_calls, _usage = await client.generate_with_tools("привет", tools=[{}])

    assert text == "Привет!"
    assert tool_calls == []


@pytest.mark.asyncio
async def test_generate_with_tools_escalates_to_cloud_on_error():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(side_effect=ConnectionError("unreachable"))

    text, tool_calls, usage = await client.generate_with_tools("привет", tools=[{}])

    assert text == NEED_CLOUD_MARKER
    assert tool_calls == []
    assert usage == {}


@pytest.mark.asyncio
async def test_generate_with_usage_omits_history_key_when_not_given():
    client = LocalLLMClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    client._client.chat = AsyncMock(return_value={"message": {"content": "ответ"}})

    await client.generate_with_usage("Привет", system_prompt="Ты ассистент.")

    messages = client._client.chat.call_args.kwargs["messages"]
    assert messages == [
        {"role": "system", "content": "Ты ассистент."},
        {"role": "user", "content": "Привет"},
    ]
