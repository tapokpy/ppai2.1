from unittest.mock import patch

from app.core.dependencies import build_cascade_router, build_tool_registry, build_transcriber
from app.core.router import CascadeRouter
from app.services.stt import Transcriber


def test_build_cascade_router_wires_dependencies():
    with (
        patch("app.core.dependencies.RAGEngine") as rag_cls,
        patch("app.core.dependencies.default_embedding_function"),
        patch("app.core.dependencies.default_reranker") as reranker_fn,
        patch("app.core.dependencies.LocalLLMClient") as local_cls,
        patch("app.core.dependencies.CloudLLMClient") as cloud_cls,
        patch("app.core.dependencies.Redis") as redis_cls,
    ):
        router = build_cascade_router()

    assert isinstance(router, CascadeRouter)
    rag_cls.assert_called_once()
    reranker_fn.assert_called_once()
    assert rag_cls.call_args.kwargs["reranker"] is reranker_fn.return_value
    local_cls.assert_called_once()
    cloud_cls.assert_called_once()
    redis_cls.from_url.assert_called_once()


def test_build_cascade_router_skips_reranker_when_disabled():
    with (
        patch("app.core.dependencies.RAGEngine") as rag_cls,
        patch("app.core.dependencies.default_embedding_function"),
        patch("app.core.dependencies.default_reranker") as reranker_fn,
        patch("app.core.dependencies.LocalLLMClient"),
        patch("app.core.dependencies.CloudLLMClient"),
        patch("app.core.dependencies.Redis"),
        patch("app.core.dependencies.settings.RERANKER_ENABLED", False),
    ):
        build_cascade_router()

    reranker_fn.assert_not_called()
    assert rag_cls.call_args.kwargs["reranker"] is None


def test_build_transcriber_returns_transcriber_instance():
    transcriber = build_transcriber()

    assert isinstance(transcriber, Transcriber)


def test_build_tool_registry_registers_all_tools_by_default():
    # Explicitly empty regardless of the real .env this test process
    # happens to load — the point of this test is which tools are
    # unconditionally registered, not what optional keys are configured
    # in whatever environment it runs in.
    with (
        patch("app.core.dependencies.settings.TAVILY_API_KEY", ""),
        patch("app.core.dependencies.settings.GOOGLE_SHEETS_API_KEY", ""),
    ):
        registry = build_tool_registry()

    names = {t.name for t in registry.list_for(is_admin=True)}
    assert names == {
        "calculate_power",
        "download_youtube",
        "find_history",
        "get_recent_activity",
        "find_downloaded_file",
        "warehouse_lookup",
        "calculate_modules",
        "list_projects",
        "read_google_doc",
    }


def test_build_tool_registry_skips_disabled_tools():
    with patch("app.core.dependencies.settings.TOOLS_DISABLED", "warehouse_lookup,list_projects"):
        registry = build_tool_registry()

    names = {t.name for t in registry.list_for(is_admin=True)}
    assert "warehouse_lookup" not in names
    assert "list_projects" not in names
    assert "calculate_power" in names


def test_build_tool_registry_excludes_web_search_without_api_key():
    with patch("app.core.dependencies.settings.TAVILY_API_KEY", ""):
        registry = build_tool_registry()

    assert registry.get("web_search") is None


def test_build_tool_registry_includes_web_search_with_api_key():
    with patch("app.core.dependencies.settings.TAVILY_API_KEY", "fake-key"):
        registry = build_tool_registry()

    assert registry.get("web_search") is not None


def test_build_tool_registry_excludes_read_google_sheet_without_api_key():
    with patch("app.core.dependencies.settings.GOOGLE_SHEETS_API_KEY", ""):
        registry = build_tool_registry()

    assert registry.get("read_google_sheet") is None


def test_build_tool_registry_includes_read_google_sheet_with_api_key():
    with patch("app.core.dependencies.settings.GOOGLE_SHEETS_API_KEY", "fake-key"):
        registry = build_tool_registry()

    assert registry.get("read_google_sheet") is not None
