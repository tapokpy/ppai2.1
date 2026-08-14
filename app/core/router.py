import re
import time
import uuid
from datetime import date

from loguru import logger
from redis.asyncio import Redis

from app.core.database import async_session_maker
from app.core.prompt_manager import (
    CONFIDENCE_INSTRUCTION,
    detect_prompt_type,
    get_system_prompt,
    is_capability_question,
)
from app.services.audit import log_action
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
        try:
            result = await self._process_query(user_id, prompt, use_cloud_override)
        except Exception as exc:
            await self._audit(user_id, prompt, decision="exception", status="error", detail={"error": str(exc)})
            raise

        result["elapsed_seconds"] = round(time.monotonic() - start, 2)
        await self._audit(user_id, prompt, decision=result["source"], status="success")
        return result

    @staticmethod
    async def _audit(user_id: int, prompt: str, decision: str, status: str, detail: dict | None = None) -> None:
        # Single choke point for both Telegram and web chat (both call
        # process_query) — see app/bot/handlers/chat.py and
        # app/api/v1/endpoints/chat.py. Best-effort: an audit failure must
        # never take down the actual chat response.
        try:
            async with async_session_maker() as session:
                await log_action(
                    session,
                    user_id=user_id,
                    command_text=prompt,
                    module="cascade_router",
                    decision=decision,
                    status=status,
                    detail=detail,
                )
        except Exception as exc:
            logger.warning(f"Audit logging failed for user {user_id}: {exc}")

    async def _process_query(self, user_id: int, prompt: str, use_cloud_override: bool) -> dict:
        # Per-phase timings (rag/local/cloud, in seconds) so the Telegram
        # metrics line can show *where* the total elapsed time actually went
        # instead of just the opaque total — the local model's own inference
        # (CPU-only Ollama) dominates almost every response, which the total
        # alone doesn't make obvious.
        timing: dict[str, float] = {}
        # Ordered pipeline trace (query_embedded/retrieval_started/... per
        # OPEN_SOURCE_STRATEGY.md §6.2) — powers the RAG visualization admin
        # panel's per-query timeline. One trace_id groups every event emitted
        # while answering this one prompt, regardless of which branch below
        # actually produced the answer.
        trace_id = str(uuid.uuid4())
        events: list[dict] = []

        if use_cloud_override:
            result = await self._call_cloud(
                user_id, prompt, context=None, rag_debug=None, timing=timing, events=events
            )
            result["rag_trace_id"] = trace_id
            return result

        base_system_prompt = get_system_prompt(detect_prompt_type(prompt)) + CONFIDENCE_INSTRUCTION

        self._emit(events, "retrieval_started", {"collection": self._rag.collection_name})
        rag_start = time.monotonic()
        if is_capability_question(prompt):
            # Skip RAG entirely for "умеешь ли ты...?" style questions —
            # a tangentially-matched project-doc chunk here was observed
            # live to confuse the local model into a garbled/non-Russian
            # answer instead of just listing capabilities.yaml's contents
            # (which get_system_prompt() already always includes).
            rag_result = {"found": False, "max_score": 0.0, "documents": [], "metadatas": [], "scores": []}
        else:
            rag_result = self._rag.query(prompt)
        timing["rag_seconds"] = round(time.monotonic() - rag_start, 2)
        self._emit(events, "query_embedded", {"model": self._rag.embedding_model_name, "query": prompt})
        self._emit(
            events,
            "retrieval_results",
            {
                "found": rag_result["found"],
                "max_score": rag_result["max_score"],
                "retrieved": [
                    {"snippet": doc[:200], "score": score, "metadata": meta}
                    for doc, score, meta in zip(
                        rag_result["documents"], rag_result["scores"], rag_result["metadatas"]
                    )
                ],
            },
        )
        context = None
        rag_debug = None

        if rag_result["found"]:
            context = "\n\n".join(rag_result["documents"])
            rag_debug = self._build_rag_debug(rag_result)
            self._emit(events, "chunks_selected", {"count": len(rag_result["documents"])})
            self._emit(events, "context_built", {"chunk_count": len(rag_result["documents"]), "char_count": len(context)})
            self._emit(events, "llm_called", {"model": self._local.model_name, "source": "local"})
            local_start = time.monotonic()
            text, llm_usage = await self._local.generate_with_usage(
                prompt, system_prompt=f"{base_system_prompt}\n\nКонтекст:\n{context}"
            )
            timing["local_seconds"] = round(time.monotonic() - local_start, 2)
            if text.strip() and not self._local.needs_cloud(text):
                clean_text, confidence = self._extract_confidence(text)
                # With cloud disabled, local is the terminal step of the
                # cascade — a low-confidence local answer is still more
                # useful to the user than discarding it for an escalation
                # that would just bounce off the disabled-cloud message.
                if confidence != "low" or not self._cloud_enabled:
                    self._emit(
                        events,
                        "answer_generated",
                        {"source": "rag", "confidence": confidence, "length": len(clean_text), "usage": llm_usage},
                    )
                    return {
                        "text": clean_text,
                        "source": "rag",
                        "context_used": True,
                        "rag_debug": rag_debug,
                        "confidence": confidence,
                        "llm_usage": llm_usage,
                        "timing": timing,
                        "rag_trace_id": trace_id,
                        "trace_events": events,
                    }
        else:
            self._emit(events, "llm_called", {"model": self._local.model_name, "source": "local"})
            local_start = time.monotonic()
            text, llm_usage = await self._local.generate_with_usage(prompt, system_prompt=base_system_prompt)
            timing["local_seconds"] = round(time.monotonic() - local_start, 2)
            if text.strip() and not self._local.needs_cloud(text):
                clean_text, confidence = self._extract_confidence(text)
                if confidence != "low" or not self._cloud_enabled:
                    self._emit(
                        events,
                        "answer_generated",
                        {"source": "local", "confidence": confidence, "length": len(clean_text), "usage": llm_usage},
                    )
                    return {
                        "text": clean_text,
                        "source": "local",
                        "context_used": False,
                        "rag_debug": None,
                        "confidence": confidence,
                        "llm_usage": llm_usage,
                        "timing": timing,
                        "rag_trace_id": trace_id,
                        "trace_events": events,
                    }

        result = await self._call_cloud(
            user_id, prompt, context=context, rag_debug=rag_debug, timing=timing, events=events
        )
        result["rag_trace_id"] = trace_id
        return result

    @staticmethod
    def _emit(events: list[dict], event_name: str, payload: dict) -> None:
        events.append({"seq": len(events) + 1, "event_name": event_name, "payload": payload})

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
        self,
        user_id: int,
        prompt: str,
        context: str | None,
        rag_debug: dict | None,
        timing: dict[str, float] | None = None,
        events: list[dict] | None = None,
    ) -> dict:
        timing = timing if timing is not None else {}
        events = events if events is not None else []

        if not self._cloud_enabled:
            self._emit(events, "answer_generated", {"source": "cloud_disabled"})
            return {
                "text": CLOUD_DISABLED_MESSAGE,
                "source": "cloud_disabled",
                "context_used": False,
                "rag_debug": rag_debug,
                "confidence": None,
                "llm_usage": None,
                "timing": timing,
                "trace_events": events,
            }

        if not await self._check_and_increment_rate_limit(user_id):
            self._emit(events, "answer_generated", {"source": "rate_limited"})
            return {
                "text": RATE_LIMIT_MESSAGE,
                "source": "rate_limited",
                "context_used": False,
                "rag_debug": None,
                "confidence": None,
                "llm_usage": None,
                "timing": timing,
                "trace_events": events,
            }

        self._emit(events, "llm_called", {"model": self._cloud.model_name, "source": "cloud"})
        cloud_start = time.monotonic()
        try:
            text, llm_usage = await self._cloud.generate_with_usage(prompt, context=context)
        except CloudUnavailableError as exc:
            timing["cloud_seconds"] = round(time.monotonic() - cloud_start, 2)
            logger.warning(f"Cloud LLM unavailable for user {user_id}: {exc}")
            self._emit(events, "answer_generated", {"source": "cloud_unavailable"})
            return {
                "text": CLOUD_UNAVAILABLE_MESSAGE,
                "source": "cloud_unavailable",
                "context_used": False,
                "rag_debug": rag_debug,
                "confidence": None,
                "llm_usage": None,
                "timing": timing,
                "trace_events": events,
            }
        timing["cloud_seconds"] = round(time.monotonic() - cloud_start, 2)
        self._emit(events, "answer_generated", {"source": "cloud", "length": len(text), "usage": llm_usage})

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
            "timing": timing,
            "trace_events": events,
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
