from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.router import CLOUD_DISABLED_MESSAGE, CLOUD_UNAVAILABLE_MESSAGE, RATE_LIMIT_MESSAGE, CascadeRouter
from app.core.tool_registry import ToolParameter, ToolRegistry, ToolResult, ToolSpec
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
    cloud_enabled: bool = True,
    tool_registry: ToolRegistry | None = None,
    local_tool_calls: list[dict] | None = None,
):
    documents = rag_documents or []
    rag_engine = MagicMock()
    rag_engine.collection_name = "knowledge_base"
    rag_engine.embedding_model_name = "all-MiniLM-L6-v2"
    rag_engine.query.return_value = {
        "found": rag_found,
        "max_score": 0.9 if rag_found else 0.1,
        "documents": documents,
        "metadatas": [{} for _ in documents],
        "scores": [0.9 for _ in documents],
    }

    local_llm = MagicMock()
    local_llm.model_name = "qwen2.5:7b"
    local_llm.generate_with_usage = AsyncMock(return_value=(local_response, local_usage or {}))
    local_llm.generate_with_tools = AsyncMock(
        return_value=(local_response, local_tool_calls or [], local_usage or {})
    )
    local_llm.needs_cloud = LocalLLMClient.needs_cloud

    cloud_llm = MagicMock()
    cloud_llm.model_name = "claude-3-5-sonnet-20241022"
    cloud_llm.generate_with_usage = AsyncMock(return_value=(cloud_response, cloud_usage or {}))

    redis_client = FakeRedis()

    router = CascadeRouter(
        rag_engine=rag_engine,
        local_llm=local_llm,
        cloud_llm=cloud_llm,
        redis_client=redis_client,
        cloud_daily_limit=daily_limit,
        cloud_enabled=cloud_enabled,
        tool_registry=tool_registry,
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
async def test_capability_question_answered_deterministically_no_rag_no_llm(tmp_path):
    # rag_found=True would normally inject "контекст документа" as grounding,
    # and local_llm would normally get called — a capability question must
    # skip BOTH: answered straight from capabilities.yaml (see
    # app/core/capabilities.py::format_capabilities_for_user), since asking
    # the local LLM to just relay that list was tried first and failed live
    # (it answered from its own generic priors instead, sometimes in Chinese).
    config = tmp_path / "capabilities.yaml"
    config.write_text(
        "capabilities:\n  - name: Чертежи\n    description: Умею читать .dxf/.dwg.\n", encoding="utf-8"
    )
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True, rag_documents=["не относящийся к делу текст"]
    )

    with patch("app.core.router.settings") as settings_mock:
        settings_mock.CAPABILITIES_PATH = str(config)
        result = await router.process_query(user_id=1, prompt="умеешь ли ты работать с чертежами")

    rag_engine.query.assert_not_called()
    local_llm.generate_with_usage.assert_not_awaited()
    assert result["source"] == "capabilities"
    assert result["context_used"] is False
    assert result["confidence"] == "high"
    assert "Чертежи" in result["text"]
    assert "не относящийся к делу текст" not in result["text"]


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
    # history is [] here: no real Postgres behind async_session_maker() in
    # this unit test, so _load_recent_history's best-effort DB fetch fails
    # and degrades to no memory for the turn (see test_router memory tests
    # further down for the case where it's actually populated).
    cloud_llm.generate_with_usage.assert_awaited_once_with("вопрос", context="контекст документа", history=[])


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
    cloud_llm.generate_with_usage.assert_awaited_once_with("вопрос", context="контекст документа", history=[])


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
async def test_local_only_path_reports_rag_and_local_timing():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert set(result["timing"].keys()) == {"rag_seconds", "local_seconds"}
    assert result["timing"]["rag_seconds"] >= 0
    assert result["timing"]["local_seconds"] >= 0


@pytest.mark.asyncio
async def test_rag_path_reports_rag_and_local_timing():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True, rag_documents=["контекст документа"]
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert set(result["timing"].keys()) == {"rag_seconds", "local_seconds"}


@pytest.mark.asyncio
async def test_cloud_escalation_adds_cloud_timing_on_top_of_rag_and_local():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]"
    )

    result = await router.process_query(user_id=1, prompt="сложный вопрос")

    assert set(result["timing"].keys()) == {"rag_seconds", "local_seconds", "cloud_seconds"}


@pytest.mark.asyncio
async def test_use_cloud_override_reports_only_cloud_timing():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router()

    result = await router.process_query(user_id=1, prompt="вопрос", use_cloud_override=True)

    assert set(result["timing"].keys()) == {"cloud_seconds"}


@pytest.mark.asyncio
async def test_cloud_disabled_returns_low_confidence_local_answer_instead_of_escalating():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="Наверное что-то [CONFIDENCE: low]", cloud_enabled=False
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "local"
    assert result["text"] == "Наверное что-то"
    assert result["confidence"] == "low"
    cloud_llm.generate_with_usage.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_disabled_returns_low_confidence_rag_answer_instead_of_escalating():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True,
        rag_documents=["контекст документа"],
        local_response="Наверное что-то [CONFIDENCE: low]",
        cloud_enabled=False,
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "rag"
    assert result["confidence"] == "low"
    cloud_llm.generate_with_usage.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_disabled_returns_friendly_message_when_local_truly_fails():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]", cloud_enabled=False
    )

    result = await router.process_query(user_id=1, prompt="сложный вопрос")

    assert result["text"] == CLOUD_DISABLED_MESSAGE
    assert result["source"] == "cloud_disabled"
    cloud_llm.generate_with_usage.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_disabled_blocks_use_cloud_override_too():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(cloud_enabled=False)

    result = await router.process_query(user_id=1, prompt="вопрос", use_cloud_override=True)

    assert result["text"] == CLOUD_DISABLED_MESSAGE
    assert result["source"] == "cloud_disabled"
    cloud_llm.generate_with_usage.assert_not_called()


@pytest.mark.asyncio
async def test_rag_success_emits_full_event_sequence_with_trace_id():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=True, rag_documents=["контекст документа"]
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["rag_trace_id"]
    event_names = [e["event_name"] for e in result["trace_events"]]
    assert event_names == [
        "retrieval_started",
        "query_embedded",
        "retrieval_results",
        "chunks_selected",
        "context_built",
        "llm_called",
        "answer_generated",
    ]
    assert [e["seq"] for e in result["trace_events"]] == list(range(1, 8))
    assert result["trace_events"][1]["payload"]["model"] == "all-MiniLM-L6-v2"
    assert result["trace_events"][5]["payload"]["model"] == "qwen2.5:7b"
    assert result["trace_events"][6]["payload"]["source"] == "rag"


@pytest.mark.asyncio
async def test_local_only_path_skips_chunk_events():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    result = await router.process_query(user_id=1, prompt="вопрос")

    event_names = [e["event_name"] for e in result["trace_events"]]
    assert event_names == [
        "retrieval_started",
        "query_embedded",
        "retrieval_results",
        "llm_called",
        "answer_generated",
    ]


@pytest.mark.asyncio
async def test_cloud_escalation_appends_cloud_events_after_local_attempt():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]"
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    event_names = [e["event_name"] for e in result["trace_events"]]
    assert event_names == [
        "retrieval_started",
        "query_embedded",
        "retrieval_results",
        "llm_called",
        "llm_called",
        "answer_generated",
    ]
    assert result["trace_events"][-2]["payload"]["model"] == "claude-3-5-sonnet-20241022"
    assert result["trace_events"][-1]["payload"]["source"] == "cloud"


@pytest.mark.asyncio
async def test_use_cloud_override_emits_only_cloud_events():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router()

    result = await router.process_query(user_id=1, prompt="вопрос", use_cloud_override=True)

    event_names = [e["event_name"] for e in result["trace_events"]]
    assert event_names == ["llm_called", "answer_generated"]
    assert result["rag_trace_id"]


@pytest.mark.asyncio
async def test_cloud_disabled_trace_ends_with_answer_generated():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]", cloud_enabled=False
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["trace_events"][-1] == {
        "seq": len(result["trace_events"]),
        "event_name": "answer_generated",
        "payload": {"source": "cloud_disabled"},
    }


@pytest.mark.asyncio
async def test_rate_limited_trace_ends_with_answer_generated():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]", daily_limit=0
    )

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["source"] == "rate_limited"
    assert result["trace_events"][-1]["payload"] == {"source": "rate_limited"}
    # Only the local model's llm_called fires (before escalation) — the
    # rate limit blocks before a cloud llm_called would ever be emitted.
    event_names = [e["event_name"] for e in result["trace_events"]]
    assert event_names.count("llm_called") == 1


@pytest.mark.asyncio
async def test_cloud_unavailable_trace_ends_with_answer_generated():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, local_response="[NEED_CLOUD]"
    )
    cloud_llm.generate_with_usage = AsyncMock(side_effect=CloudUnavailableError("missing API key"))

    result = await router.process_query(user_id=1, prompt="вопрос")

    assert result["trace_events"][-1]["payload"] == {"source": "cloud_unavailable"}


@pytest.mark.asyncio
async def test_composes_system_prompt_from_detected_type_and_confidence_instruction():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    await router.process_query(user_id=1, prompt="рассчитай мощность экрана")

    system_prompt = local_llm.generate_with_usage.call_args.kwargs["system_prompt"]
    assert "калькулятор" in system_prompt.lower()
    assert "[CONFIDENCE:" in system_prompt


def _fake_tool_registry(admin_only: bool = False, success: bool = True) -> tuple[ToolRegistry, AsyncMock]:
    handler = AsyncMock(
        return_value=ToolResult(
            text="Готово: 20 модулей",
            success=success,
            error=None if success else "boom",
            structured_data={"kind": "power_calculation"} if success else None,
        )
    )
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="calculate_power",
            description="test",
            parameters=[ToolParameter(name="module_count", type="integer", description="x")],
            handler=handler,
            admin_only=admin_only,
        )
    )
    return registry, handler


@pytest.mark.asyncio
async def test_tools_disabled_by_default_never_calls_generate_with_tools():
    registry, handler = _fake_tool_registry()
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, tool_registry=registry
    )

    result = await router.process_query(user_id=1, prompt="посчитай питание для 20 модулей")

    local_llm.generate_with_tools.assert_not_called()
    local_llm.generate_with_usage.assert_awaited_once()
    handler.assert_not_called()
    assert result["source"] == "local"


@pytest.mark.asyncio
async def test_native_tool_call_dispatches_to_registered_handler():
    registry, handler = _fake_tool_registry()
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False,
        tool_registry=registry,
        local_tool_calls=[{"name": "calculate_power", "arguments": {"module_count": 20}}],
    )

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", True),
    ):
        result = await router.process_query(user_id=1, prompt="посчитай питание для 20 модулей")

    handler.assert_awaited_once_with(module_count=20)
    local_llm.generate_with_tools.assert_awaited_once()
    cloud_llm.generate_with_usage.assert_not_called()
    assert result["source"] == "tool"
    assert result["text"] == "Готово: 20 модулей"
    assert result["structured_data"] == {"kind": "power_calculation"}


@pytest.mark.asyncio
async def test_tool_call_naming_admin_only_tool_is_denied_for_non_admin():
    # Two tools registered — a public one (so the catalog shown to the
    # model isn't empty and generate_with_tools actually fires) plus an
    # admin-only one the model "hallucinates" a call to despite it never
    # being in the schema it was shown. Exercises the server-side re-check
    # (app/core/router.py::_dispatch_tool_call) as defense in depth.
    registry, public_handler = _fake_tool_registry()
    admin_handler = AsyncMock(return_value=ToolResult(text="секрет", success=True))
    registry.register(
        ToolSpec(
            name="admin_tool",
            description="test",
            parameters=[],
            handler=admin_handler,
            admin_only=True,
        )
    )
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False,
        tool_registry=registry,
        local_tool_calls=[{"name": "admin_tool", "arguments": {}}],
    )

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", True),
    ):
        result = await router.process_query(user_id=1, prompt="посчитай", is_admin=False)

    admin_handler.assert_not_called()
    public_handler.assert_not_called()
    assert result["source"] == "tool_denied"


@pytest.mark.asyncio
async def test_tool_call_naming_admin_only_tool_dispatches_for_admin():
    registry, handler = _fake_tool_registry(admin_only=True)
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False,
        tool_registry=registry,
        local_tool_calls=[{"name": "calculate_power", "arguments": {"module_count": 20}}],
    )

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", True),
    ):
        result = await router.process_query(user_id=1, prompt="посчитай", is_admin=True)

    handler.assert_awaited_once()
    assert result["source"] == "tool"


@pytest.mark.asyncio
async def test_tool_handler_failure_is_reported_without_raising():
    registry, handler = _fake_tool_registry(success=False)
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False,
        tool_registry=registry,
        local_tool_calls=[{"name": "calculate_power", "arguments": {"module_count": 0}}],
    )

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", True),
    ):
        result = await router.process_query(user_id=1, prompt="посчитай")

    assert result["source"] == "tool"
    assert result["structured_data"] is None


@pytest.mark.asyncio
async def test_fallback_prompt_json_path_dispatches_when_native_disabled():
    registry, handler = _fake_tool_registry()
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False,
        tool_registry=registry,
        local_response='{"tool": "calculate_power", "arguments": {"module_count": 20}}',
    )

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", False),
    ):
        result = await router.process_query(user_id=1, prompt="посчитай питание для 20 модулей")

    local_llm.generate_with_tools.assert_not_called()
    local_llm.generate_with_usage.assert_awaited_once()
    assert "calculate_power" in local_llm.generate_with_usage.call_args.kwargs["system_prompt"]
    handler.assert_awaited_once_with(module_count=20)
    assert result["source"] == "tool"


@pytest.mark.asyncio
async def test_fallback_path_treats_non_json_response_as_plain_text():
    registry, handler = _fake_tool_registry()
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False, tool_registry=registry, local_response="Обычный текстовый ответ"
    )

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", False),
    ):
        result = await router.process_query(user_id=1, prompt="вопрос")

    handler.assert_not_called()
    assert result["source"] == "local"
    assert result["text"] == "Обычный текстовый ответ"


@pytest.mark.asyncio
async def test_needs_user_id_tool_receives_real_user_id_not_model_supplied_one():
    handler = AsyncMock(return_value=ToolResult(text="результат"))
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="find_history",
            description="test",
            parameters=[ToolParameter(name="query", type="string", description="x")],
            handler=handler,
            needs_user_id=True,
        )
    )
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(
        rag_found=False,
        tool_registry=registry,
        # Model tries to smuggle a different user_id in its own arguments —
        # the router must overwrite it with the real calling user, not trust it.
        local_tool_calls=[{"name": "find_history", "arguments": {"query": "x", "user_id": 999}}],
    )

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", True),
    ):
        await router.process_query(user_id=1, prompt="найди в истории X")

    handler.assert_awaited_once_with(query="x", user_id=1)


@pytest.mark.asyncio
async def test_no_tools_registered_skips_tool_path_even_when_enabled():
    router, rag_engine, local_llm, cloud_llm, redis_client = make_router(rag_found=False)

    with (
        patch("app.core.router.settings.TOOLS_ENABLED", True),
        patch("app.core.router.settings.TOOLS_USE_NATIVE_OLLAMA", True),
    ):
        result = await router.process_query(user_id=1, prompt="вопрос")

    local_llm.generate_with_tools.assert_not_called()
    local_llm.generate_with_usage.assert_awaited_once()
    assert result["source"] == "local"
