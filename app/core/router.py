import re
import time
from datetime import date

from loguru import logger
from redis.asyncio import Redis

from app.core.prompt_manager import CONFIDENCE_INSTRUCTION, detect_prompt_type, get_system_prompt
from app.services.cloud_llm import CloudLLMClient, CloudUnavailableError
from app.services.local_llm import LocalLLMClient
from app.services.rag_engine import RAGEngine

CONFIDENCE_PATTERN = re.compile(r"\[CONFIDENCE:\s*(high|medium|low)\]", re.IGNORECASE)

CLOUD_RATE_LIMIT_KEY = "cloud_usage:{user_id}:{day}"
RATE_LIMIT_MESSAGE = (
    "Достигнут дневной лимит обращений к облачному ИИ. "
    "Попробуйте завтра или обратитесь к администратору."
)
CLOUD_UNAVAILABLE_MESSAGE = (
    "Расширенный облачный ответ сейчас недоступен. "
    "Попробуйте переформулировать вопрос или обратитесь позже."
)
CLOUD_DISABLED_MESSAGE = (
    "Облачный ИИ временно отключён администратором — отвечает только локальная модель."
)


class CascadeRouter:
    def __init__(
        self,
        rag_engine: RAGEngine,
        local_llm: LocalLLMClient,
        cloud_llm: CloudLLMClient,
        redis_client: Redis,
        cloud_daily_limit: int,
        cloud_enabled: bool = True,
    ):
        self._rag = rag_engine
        self._local = local_llm
        self._cloud = cloud_llm
        self._redis = redis_client
        self._cloud_daily_limit = cloud_daily_limit
        self._cloud_enabled = cloud_enabled

    @property
    def rag_engine(self) -> RAGEngine:
        return self._rag

    @property
    def local_llm(self) -> LocalLLMClient:
        return self._local

    async def process_query(self, user_id: int, prompt: str, use_cloud_override: bool = False) -> dict:
        start = time.monotonic()
        result = await self._process_query(user_id, prompt, use_cloud_override)
        result["elapsed_seconds"] = round(time.monotonic() - start, 2)
        return result

    async def _process_query(self, user_id: int, prompt: str, use_cloud_override: bool) -> dict:
        if use_cloud_override:
            return await self._call_cloud(user_id, prompt, context=None, rag_debug=None)

        base_system_prompt = get_system_prompt(detect_prompt_type(prompt)) + CONFIDENCE_INSTRUCTION

        rag_result = self._rag.query(prompt)
        context = None
        rag_debug = None

        if rag_result["found"]:
            context = "\n\n".join(rag_result["documents"])
            rag_debug = self._build_rag_debug(rag_result)
            text, llm_usage = await self._local.generate_with_usage(
                prompt, system_prompt=f"{base_system_prompt}\n\nКонтекст:\n{context}"
            )
            if text.strip() and not self._local.needs_cloud(text):
                clean_text, confidence = self._extract_confidence(text)
                # With cloud disabled, local is the terminal step of the
                # cascade — a low-confidence local answer is still more
                # useful to the user than discarding it for an escalation
                # that would just bounce off the disabled-cloud message.
                if confidence != "low" or not self._cloud_enabled:
                    return {
                        "text": clean_text,
                        "source": "rag",
                        "context_used": True,
                        "rag_debug": rag_debug,
                        "confidence": confidence,
                        "llm_usage": llm_usage,
                    }
        else:
            text, llm_usage = await self._local.generate_with_usage(prompt, system_prompt=base_system_prompt)
            if text.strip() and not self._local.needs_cloud(text):
                clean_text, confidence = self._extract_confidence(text)
                if confidence != "low" or not self._cloud_enabled:
                    return {
                        "text": clean_text,
                        "source": "local",
                        "context_used": False,
                        "rag_debug": None,
                        "confidence": confidence,
                        "llm_usage": llm_usage,
                    }

        return await self._call_cloud(user_id, prompt, context=context, rag_debug=rag_debug)

    @staticmethod
    def _extract_confidence(text: str) -> tuple[str, str | None]:
        """Strips the trailing [CONFIDENCE: x] marker the model was asked to
        append and returns (clean_text, confidence_level). confidence is None
        if the model didn't include the marker at all (treated as unknown,
        not escalated) rather than assuming the worst."""
        match = CONFIDENCE_PATTERN.search(text)
        if not match:
            return text.strip(), None

        clean_text = CONFIDENCE_PATTERN.sub("", text).strip()
        return clean_text, match.group(1).lower()

    async def _call_cloud(
        self, user_id: int, prompt: str, context: str | None, rag_debug: dict | None
    ) -> dict:
        if not self._cloud_enabled:
            return {
                "text": CLOUD_DISABLED_MESSAGE,
                "source": "cloud_disabled",
                "context_used": False,
                "rag_debug": rag_debug,
                "confidence": None,
                "llm_usage": None,
            }

        if not await self._check_and_increment_rate_limit(user_id):
            return {
                "text": RATE_LIMIT_MESSAGE,
                "source": "rate_limited",
                "context_used": False,
                "rag_debug": None,
                "confidence": None,
                "llm_usage": None,
            }

        try:
            text, llm_usage = await self._cloud.generate_with_usage(prompt, context=context)
        except CloudUnavailableError as exc:
            logger.warning(f"Cloud LLM unavailable for user {user_id}: {exc}")
            return {
                "text": CLOUD_UNAVAILABLE_MESSAGE,
                "source": "cloud_unavailable",
                "context_used": False,
                "rag_debug": rag_debug,
                "confidence": None,
                "llm_usage": None,
            }

        return {
            "text": text,
            "source": "cloud",
            "context_used": context is not None,
            "rag_debug": rag_debug,
            # Claude isn't asked for a self-reported confidence marker (that
            # instruction is only added to the local model's system prompt) —
            # it's already the trusted fallback tier of the cascade.
            "confidence": None,
            "llm_usage": llm_usage,
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
