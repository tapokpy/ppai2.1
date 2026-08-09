from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.router import RATE_LIMIT_MESSAGE, CascadeRouter
from app.services.local_llm import LocalLLMClient


def make_router(
    rag_found: bool = False,
    rag_documents: list[str] | None = None,
    local_response: str = "ответ",
    cloud_response: str = "облачный ответ",
    daily_limit: int = 50,
):
    rag_engine = MagicMock()
    rag_engine.query.return_value = {
        "found": rag_found,
        "max_score": 0.9 if rag_found else 0.1,
        "documents": rag_documents or [],
        "metadatas": [],
        "scores": [],
    }

    local_llm = MagicMock()
    local_llm.generate = AsyncMock(return_value=local_response)
    local_llm.needs_cloud = LocalLLMClient.needs_cloud

    cloud_llm = MagicMock()
    cloud_llm.generate = AsyncMock(return_value=cloud_response)

    redis_client = FakeRedis()

    router = CascadeRouter(
        rag_engine=rag_engine,
        local_llm=local_llm,
        cloud_llm=cloud_llm,
        redis_client=redis_client,
        cloud_daily_limit=daily_limit,
    )
    return router, rag_engine, local_llm, cloud_llm, redis_client


@pytest.mark.asyncio
async def test_uses_rag_when_context_found_and_local_can_answer():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True, rag_documents=["контекст документа"]
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result == {"text": "ответ", "source": "rag", "context_used": True}
    cloud_llm.generate.assert_not_called()
    local_llm.generate.assert_awaited_once()
    assert "контекст документа" in local_llm.generate.call_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_falls_back_to_local_when_rag_not_found():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result == {"text": "ответ", "source": "local", "context_used": False}
    cloud_llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_escalates_to_cloud_when_local_signals_need_cloud():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]"
    )

    result = await router.process_query(user_id=1, prompt="сложный вопрос")

    assert result == {"text": "облачный ответ", "source": "cloud", "context_used": False}


@pytest.mark.asyncio
async def test_escalates_to_cloud_with_rag_context_when_local_cannot_answer():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True, rag_documents=["контекст документа"], local_response="[NEED_CLOUD]"
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "cloud"
    assert result["context_used"] is True
    cloud_llm.generate.assert_awaited_once_with("вопрос", context="контекст документа")


@pytest.mark.asyncio
async def test_use_cloud_override_skips_rag_and_local():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router()

    result = await router.process_query(user_id=1, prompt="вопрос", use_cloud_override=True)

    assert result["source"] == "cloud"
    rag_engine.query.assert_not_called()
    local_llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_rate_limit_blocks_after_daily_limit():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]", daily_limit=2
    )

    await router.process_query(user_id=42, prompt="q1")
    await router.process_query(user_id=42, prompt="q2")
    result = await router.process_query(user_id=42, prompt="q3")

    assert result == {"text": RATE_LIMIT_MESSAGE, "source": "rate_limited", "context_used": False}
    assert cloud_llm.generate.call_count == 2


@pytest.mark.asyncio
async def test_rate_limit_is_scoped_per_user():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]", daily_limit=1
    )

    await router.process_query(user_id=1, prompt="q1")
    result = await router.process_query(user_id=2, prompt="q1")

    assert result["source"] == "cloud"
