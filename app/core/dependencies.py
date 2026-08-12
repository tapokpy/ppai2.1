from redis.asyncio import Redis

from app.core.config import settings
from app.core.router import CascadeRouter
from app.services.cloud_llm import CloudLLMClient
from app.services.embeddings import default_embedding_function
from app.services.github_planning import GitHubPlanningClient
from app.services.local_llm import LocalLLMClient
from app.services.rag_engine import RAGEngine
from app.services.stt import Transcriber


def build_transcriber() -> Transcriber:
    return Transcriber(
        model_size=settings.WHISPER_MODEL_SIZE,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        language=settings.WHISPER_LANGUAGE,
    )


def build_github_planning_client() -> GitHubPlanningClient:
    return GitHubPlanningClient(
        token=settings.GITHUB_TOKEN,
        repo=settings.GITHUB_REPO,
        file_path=settings.GITHUB_PLANNING_FILE_PATH,
        branch=settings.GITHUB_PLANNING_BRANCH,
    )


def build_cascade_router() -> CascadeRouter:
    rag_engine = RAGEngine(
        persist_dir=settings.CHROMA_PERSIST_DIR,
        score_threshold=settings.RAG_SCORE_THRESHOLD,
        embedding_function=default_embedding_function(settings.EMBEDDING_MODEL_NAME),
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
    )
