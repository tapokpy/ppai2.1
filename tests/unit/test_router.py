from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.router import CLOUD_UNAVAILABLE_MESSAGE, RATE_LIMIT_MESSAGE, CascadeRouter
from app.services.cloud_llm import CloudUnavailableError
from app.services.local_llm import LocalLLMClient


def make_router(
    rag_found: bool = False,
    rag_documents: list[str] | None = None,
    local_response: str = "ответ",
    cloud_response: str = "облачный ответ",
    daily_limit: int = 50,
    local_usage: dict | None = None,
    cloud_usage: dict | None = None,
):
    documents = rag_documents or []
    rag_engine = MagicMock()
    rag_engine.query.return_value = {
        "found": rag_found,
        "max_score": 0.9 if rag_found else 0.1,
        "documents": documents,
        "metadatas": [{} for _ in documents],
        "scores": [0.9 for _ in documents],
    }

    local_llm = MagicMock()
    local_llm.generate_with_usage = AsyncMock(return_value=(local_response, local_usage or {}))
    local_llm.needs_cloud = LocalLLMClient.needs_cloud

    cloud_llm = MagicMock()
    cloud_llm.generate_with_usage = AsyncMock(return_value=(cloud_response, cloud_usage or {}))

    redis_client = FakeRedis()

    router = CascadeRouter(
        rag_engine=rag_engine,
        local_llm=local_llm,
        cloud_llm=cloud_llm,
        redis_client=redis_client,
        cloud_daily_limit=daily_limit,
    )
    return router, rag_engine, local_llm, cloud_llm, redis_client


def test_exposes_rag_engine_and_local_llm_for_kb_harvesting():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router()

    assert router.rag_engine is rag_engine
    assert router.local_llm is local_llm


@pytest.mark.asyncio
async def test_uses_rag_when_context_found_and_local_can_answer():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True, rag_documents=["контекст документа"]
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["text"] == "ответ"
    assert result["source"] == "rag"
    assert result["context_used"] is True
    assert result["rag_debug"] == {
        "max_score": 0.9,
        "retrieved": [{"snippet": "контекст документа", "score": 0.9, "metadata": {}}],
    }
    assert isinstance(result["elapsed_seconds"], float)
    cloud_llm.generate_with_usage.assert_not_called()
    local_llm.generate_with_usage.assert_awaited_once()
    assert "контекст документа" in local_llm.generate_with_usage.call_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_falls_back_to_local_when_rag_not_found():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["text"] == "ответ"
    assert result["source"] == "local"
    assert result["context_used"] is False
    assert result["rag_debug"] is None
    cloud_llm.generate_with_usage.assert_not_called()


@pytest.mark.asyncio
async def test_escalates_to_cloud_when_local_signals_need_cloud():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]"
    )

    result = await router.process_query(user_id=1, prompt="сложный вопрос")

    assert result["text"] == "облачный ответ"
    assert result["source"] == "cloud"
    assert result["context_used"] is False
    assert result["rag_debug"] is None
    assert result["confidence"] is None


@pytest.mark.asyncio
async def test_escalates_to_cloud_with_rag_context_when_local_cannot_answer():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True, rag_documents=["контекст документа"], local_response="[NEED_CLOUD]"
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "cloud"
    assert result["context_used"] is True
    assert result["rag_debug"]["max_score"] == 0.9
    cloud_llm.generate_with_usage.assert_awaited_once_with("вопрос", context="контекст документа")


@pytest.mark.asyncio
async def test_use_cloud_override_skips_rag_and_local():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router()

    result = await router.process_query(user_id=1, prompt="вопрос", use_cloud_override=True)

    assert result["source"] == "cloud"
    rag_engine.query.assert_not_called()
    local_llm.generate_with_usage.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_rate_limit_blocks_after_daily_limit():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]", daily_limit=2
    )

    await router.process_query(user_id=42, prompt="q1")
    await router.process_query(user_id=42, prompt="q2")
    result = await router.process_query(user_id=42, prompt="q3")

    assert result["text"] == RATE_LIMIT_MESSAGE
    assert result["source"] == "rate_limited"
    assert result["context_used"] is False
    assert result["rag_debug"] is None
    assert result["llm_usage"] is None
    assert cloud_llm.generate_with_usage.call_count == 2


@pytest.mark.asyncio
async def test_cloud_unavailable_returns_friendly_message_without_raising():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]"
    )
    cloud_llm.generate_with_usage = AsyncMock(side_effect=CloudUnavailableError("missing API key"))

    result = await router.process_query(user_id=1, prompt="сложный вопрос")

    assert result["text"] == CLOUD_UNAVAILABLE_MESSAGE
    assert result["source"] == "cloud_unavailable"
    assert result["context_used"] is False
    assert result["rag_debug"] is None
    assert result["llm_usage"] is None


@pytest.mark.asyncio
async def test_process_query_reports_elapsed_seconds():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert isinstance(result["elapsed_seconds"], float)
    assert result["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_local_path_reports_llm_usage():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_usage={"prompt_tokens": 120, "completion_tokens": 45}
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["llm_usage"] == {"prompt_tokens": 120, "completion_tokens": 45}


@pytest.mark.asyncio
async def test_cloud_path_reports_llm_usage():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False,
        local_response="[NEED_CLOUD]",
        cloud_usage={"prompt_tokens": 300, "completion_tokens": 150, "estimated_cost_usd": 0.0032},
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["llm_usage"] == {
        "prompt_tokens": 300,
        "completion_tokens": 150,
        "estimated_cost_usd": 0.0032,
    }


@pytest.mark.asyncio
async def test_rate_limit_is_scoped_per_user():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]", daily_limit=1
    )

    await router.process_query(user_id=1, prompt="q1")
    result = await router.process_query(user_id=2, prompt="q1")

    assert result["source"] == "cloud"


@pytest.mark.asyncio
async def test_strips_confidence_marker_and_reports_it():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="Сечение кабеля 4 кв.мм [CONFIDENCE: high]"
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["text"] == "Сечение кабеля 4 кв.мм"
    assert result["confidence"] == "high"
    assert result["source"] == "local"


@pytest.mark.asyncio
async def test_low_confidence_local_answer_escalates_to_cloud():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="Наверное что-то [CONFIDENCE: low]"
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "cloud"
    assert result["text"] == "облачный ответ"
    cloud_llm.generate_with_usage.assert_awaited_once()


@pytest.mark.asyncio
async def test_low_confidence_rag_answer_escalates_to_cloud_with_context():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True,
        rag_documents=["контекст документа"],
        local_response="Наверное что-то [CONFIDENCE: low]",
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "cloud"
    cloud_llm.generate_with_usage.assert_awaited_once_with("вопрос", context="контекст документа")


@pytest.mark.asyncio
async def test_missing_confidence_marker_is_not_treated_as_low():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="Ответ без маркера уверенности"
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "local"
    assert result["confidence"] is None
    cloud_llm.generate_with_usage.assert_not_called()


@pytest.mark.asyncio
async def test_composes_system_prompt_from_detected_type_and_confidence_instruction():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    await router.process_query(user_id=1, prompt="рассчитай мощность экрана")

    system_prompt = local_llm.generate_with_usage.call_args.kwargs["system_prompt"]
    assert "калькулятор" in system_prompt.lower()
    assert "[CONFIDENCE:" in system_prompt
