from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.core.tool_registry import ToolParameter, ToolRegistry, ToolResult, ToolSpec
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.services.local_llm import LocalLLMClient
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_user(telegram_id: int) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="tools", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def _seed_message(user_id: int, prompt: str, response: str, source: str = "local") -> None:
    async with async_session_maker() as session:
        session.add(
            MessageModel(user_id=user_id, prompt=prompt, response=response, source=source, context_used=False)
        )
        await session.commit()


def _make_router_with_tool(tool_call_arguments: dict) -> tuple[CascadeRouter, AsyncMock]:
    handler = AsyncMock(return_value=ToolResult(text="Питание посчитано: 20 модулей", success=True))
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="calculate_power",
            description="test",
            parameters=[ToolParameter(name="module_count", type="integer", description="x")],
            handler=handler,
        )
    )

    rag_engine = MagicMock()
    rag_engine.collection_name = "knowledge_base"
    rag_engine.embedding_model_name = "all-MiniLM-L6-v2"
    rag_engine.query.return_value = {
        "found": False, "max_score": 0.1, "documents": [], "metadatas": [], "scores": []
    }

    local_llm = MagicMock()
    local_llm.model_name = "qwen2.5:7b"
    local_llm.needs_cloud = LocalLLMClient.needs_cloud
    local_llm.generate_with_tools = AsyncMock(
        return_value=("", [{"name": "calculate_power", "arguments": tool_call_arguments}], {})
    )
    # The second process_query call in the history test runs with
    # TOOLS_ENABLED left at its real (False) default, so it takes the plain
    # generate_with_usage path instead — needs to be a real awaitable too.
    local_llm.generate_with_usage = AsyncMock(return_value=("ответ", {}))

    router = CascadeRouter(
        rag_engine=rag_engine,
        local_llm=local_llm,
        cloud_llm=MagicMock(),
        redis_client=FakeRedis(),
        cloud_daily_limit=50,
        cloud_enabled=False,
        tool_registry=registry,
    )
    return router, handler


@pytest.mark.asyncio
async def test_tool_call_result_is_returned_with_source_tool(clean_db):
    user = await _seed_user(40)
    router, handler = _make_router_with_tool({"module_count": 20})

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", True),
    ):
        result = await router.process_query(user_id=user.id, prompt="посчитай питание для 20 модулей")

    handler.assert_awaited_once_with(module_count=20)
    assert result["source"] == "tool"
    assert result["text"] == "Питание посчитано: 20 модулей"


@pytest.mark.asyncio
async def test_persisted_tool_response_is_replayed_as_history_on_next_turn(clean_db):
    # Mirrors how app/bot/handlers/chat.py persists CascadeRouter's result —
    # the router itself doesn't write to the messages table.
    user = await _seed_user(41)
    await _seed_message(user.id, "посчитай питание для 20 модулей", "Питание посчитано: 20 модулей", source="tool")
    router, _handler = _make_router_with_tool({"module_count": 1})

    await router.process_query(user_id=user.id, prompt="а сколько будет для 30?")

    if router._local.generate_with_tools.call_args is not None:
        history = router._local.generate_with_tools.call_args.kwargs["history"]
    else:
        history = router._local.generate_with_usage.call_args.kwargs["history"]
    assert {"role": "assistant", "content": "Питание посчитано: 20 модулей"} in history
