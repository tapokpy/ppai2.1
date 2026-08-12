from datetime import date

from loguru import logger
from redis.asyncio import Redis

from app.services.cloud_llm import CloudLLMClient, CloudUnavailableError
from app.services.local_llm import LocalLLMClient
from app.services.rag_engine import RAGEngine

CLOUD_RATE_LIMIT_KEY = "cloud_usage:{user_id}:{day}"
RATE_LIMIT_MESSAGE = (
    "Достигнут дневной лимит обращений к облачному ИИ. "
    "Попробуйте завтра или обратитесь к администратору."
)
CLOUD_UNAVAILABLE_MESSAGE = (
    "Расширенный облачный ответ сейчас недоступен. "
    "Попробуйте переформулировать вопрос или обратитесь позже."
)


class CascadeRouter:
    def __init__(
        self,
        rag_engine: RAGEngine,
        local_llm: LocalLLMClient,
        cloud_llm: CloudLLMClient,
        redis_client: Redis,
        cloud_daily_limit: int,
    ):
        self._rag = rag_engine
        self._local = local_llm
        self._cloud = cloud_llm
        self._redis = redis_client
        self._cloud_daily_limit = cloud_daily_limit

    @property
    def rag_engine(self) -> RAGEngine:
        return self._rag

    @property
    def local_llm(self) -> LocalLLMClient:
        return self._local

    async def process_query(self, user_id: int, prompt: str, use_cloud_override: bool = False) -> dict:
        if use_cloud_override:
            return await self._call_cloud(user_id, prompt, context=None, rag_debug=None)

        rag_result = self._rag.query(prompt)
        context = None
        rag_debug = None

        if rag_result["found"]:
            context = "\n\n".join(rag_result["documents"])
            rag_debug = self._build_rag_debug(rag_result)
            text = await self._local.generate(
                prompt, system_prompt=f"Используй следующий контекст для ответа:\n{context}"
            )
            if text.strip() and not self._local.needs_cloud(text):
                return {"text": text, "source": "rag", "context_used": True, "rag_debug": rag_debug}
        else:
            text = await self._local.generate(prompt)
            if text.strip() and not self._local.needs_cloud(text):
                return {"text": text, "source": "local", "context_used": False, "rag_debug": None}

        return await self._call_cloud(user_id, prompt, context=context, rag_debug=rag_debug)

    async def _call_cloud(
        self, user_id: int, prompt: str, context: str | None, rag_debug: dict | None
    ) -> dict:
        if not await self._check_and_increment_rate_limit(user_id):
            return {
                "text": RATE_LIMIT_MESSAGE,
                "source": "rate_limited",
                "context_used": False,
                "rag_debug": None,
            }

        try:
            text = await self._cloud.generate(prompt, context=context)
        except CloudUnavailableError as exc:
            logger.warning(f"Cloud LLM unavailable for user {user_id}: {exc}")
            return {
                "text": CLOUD_UNAVAILABLE_MESSAGE,
                "source": "cloud_unavailable",
                "context_used": False,
                "rag_debug": rag_debug,
            }

        return {
            "text": text,
            "source": "cloud",
            "context_used": context is not None,
            "rag_debug": rag_debug,
        }

    @staticmethod
    def _build_rag_debug(rag_result: dict) -> dict:
        retrieved = [
            {"snippet": doc[:200], "score": score, "metadata": meta}
            for doc, score, meta in zip(
                rag_result["documents"], rag_result["scores"], rag_result["metadatas"]
            )
        ]
        return {"max_score": rag_result["max_score"], "retrieved": retrieved}

    async def _check_and_increment_rate_limit(self, user_id: int) -> bool:
        key = CLOUD_RATE_LIMIT_KEY.format(user_id=user_id, day=date.today().isoformat())
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 86400)
        return count <= self._cloud_daily_limit
