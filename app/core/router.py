from datetime import date

from redis.asyncio import Redis

from app.services.cloud_llm import CloudLLMClient
from app.services.local_llm import LocalLLMClient
from app.services.rag_engine import RAGEngine

CLOUD_RATE_LIMIT_KEY = "cloud_usage:{user_id}:{day}"
RATE_LIMIT_MESSAGE = (
    "Достигнут дневной лимит обращений к облачному ИИ. "
    "Попробуйте завтра или обратитесь к администратору."
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

    async def process_query(self, user_id: int, prompt: str, use_cloud_override: bool = False) -> dict:
        if use_cloud_override:
            return await self._call_cloud(user_id, prompt, context=None)

        rag_result = self._rag.query(prompt)
        context = None

        if rag_result["found"]:
            context = "\n\n".join(rag_result["documents"])
            text = await self._local.generate(
                prompt, system_prompt=f"Используй следующий контекст для ответа:\n{context}"
            )
            if text.strip() and not self._local.needs_cloud(text):
                return {"text": text, "source": "rag", "context_used": True}
        else:
            text = await self._local.generate(prompt)
            if text.strip() and not self._local.needs_cloud(text):
                return {"text": text, "source": "local", "context_used": False}

        return await self._call_cloud(user_id, prompt, context=context)

    async def _call_cloud(self, user_id: int, prompt: str, context: str | None) -> dict:
        if not await self._check_and_increment_rate_limit(user_id):
            return {"text": RATE_LIMIT_MESSAGE, "source": "rate_limited", "context_used": False}

        text = await self._cloud.generate(prompt, context=context)
        return {"text": text, "source": "cloud", "context_used": context is not None}

    async def _check_and_increment_rate_limit(self, user_id: int) -> bool:
        key = CLOUD_RATE_LIMIT_KEY.format(user_id=user_id, day=date.today().isoformat())
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 86400)
        return count <= self._cloud_daily_limit
