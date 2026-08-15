from redis.asyncio import Redis

from app.core.config import settings
from app.core.router import CascadeRouter
from app.core.tool_registry import ToolRegistry
from app.services.cloud_llm import CloudLLMClient
from app.services.embeddings import default_embedding_function
from app.services.local_llm import LocalLLMClient
from app.services.media_downloader import MediaDownloader
from app.services.rag_engine import RAGEngine
from app.services.resolume_controller import ResolumeController, ScreensMap
from app.services.stt import Transcriber
from app.services.tools import calculate_power_tool, download_youtube_tool


def build_transcriber() -> Transcriber:
    return Transcriber(
        model_size=settings.WHISPER_MODEL_SIZE,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        language=settings.WHISPER_LANGUAGE,
    )


def build_media_downloader() -> MediaDownloader:
    return MediaDownloader(
        storage_dir=settings.MEDIA_STORAGE_PATH,
        quota_gb=settings.MEDIA_STORAGE_QUOTA_GB,
    )


def build_resolume_controller() -> ResolumeController:
    return ResolumeController(
        osc_host=settings.RESOLUME_OSC_HOST,
        osc_port=settings.RESOLUME_OSC_PORT,
        rest_base_url=settings.RESOLUME_REST_BASE_URL,
    )


def build_screens_map() -> ScreensMap:
    return ScreensMap.load(settings.SCREENS_MAP_PATH)


def build_tool_registry(media_downloader: MediaDownloader) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(calculate_power_tool.TOOL_SPEC)
    registry.register(download_youtube_tool.build_tool_spec(media_downloader))
    # generate_image/create_chart join here once a provider is chosen /
    # the chart service is built — see the tool-calling plan, Фаза 4.
    return registry


def build_cascade_router(tool_registry: ToolRegistry | None = None) -> CascadeRouter:
    rag_engine = RAGEngine(
        persist_dir=settings.CHROMA_PERSIST_DIR,
        score_threshold=settings.RAG_SCORE_THRESHOLD,
        embedding_function=default_embedding_function(settings.EMBEDDING_MODEL_NAME),
        embedding_model_name=settings.EMBEDDING_MODEL_NAME,
    )
    local_llm = LocalLLMClient(
        base_url=settings.OLLAMA_URL,
        model=settings.OLLAMA_MODEL,
        temperature=settings.OLLAMA_TEMPERATURE,
        top_p=settings.OLLAMA_TOP_P,
        top_k=settings.OLLAMA_TOP_K,
        repeat_penalty=settings.OLLAMA_REPEAT_PENALTY,
        num_predict=settings.OLLAMA_NUM_PREDICT,
    )
    cloud_llm = CloudLLMClient(
        api_key=settings.ANTHROPIC_API_KEY,
        model=settings.CLOUD_MODEL_NAME,
        proxy_url=settings.ANTHROPIC_PROXY_URL or None,
    )
    redis_client = Redis.from_url(settings.REDIS_URL)

    return CascadeRouter(
        rag_engine=rag_engine,
        local_llm=local_llm,
        cloud_llm=cloud_llm,
        redis_client=redis_client,
        cloud_daily_limit=settings.CLOUD_DAILY_LIMIT_PER_USER,
        cloud_enabled=settings.CLOUD_ENABLED,
        tool_registry=tool_registry,
    )
