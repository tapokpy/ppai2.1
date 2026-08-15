import re
import time
import uuid
from datetime import date

from loguru import logger
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.capabilities import format_capabilities_for_user
from app.core.config import settings
from app.core.database import async_session_maker
from app.core.prompt_manager import (
    CONFIDENCE_INSTRUCTION,
    detect_prompt_type,
    get_system_prompt,
    is_capability_question,
)
from app.core.tool_registry import ToolRegistry, ToolResult, try_parse_json
from app.models.sqlalchemy.message import Message as MessageModel
from app.services.audit import log_action
from app.services.cloud_llm import CloudLLMClient, CloudUnavailableError
from app.services.local_llm import LocalLLMClient
from app.services.rag_engine import RAGEngine

CONFIDENCE_PATTERN = re.compile(r"\[CONFIDENCE:\s*(high|medium|low)\]", re.IGNORECASE)

# How many of the user's own past turns (each contributing a user+assistant
# message pair) get replayed to the LLM as conversation memory. Kept small —
# local inference is CPU-only and already the dominant cost in every
# response, so this trades some recall depth for not making every message
# noticeably slower. Each past response is truncated (below) so one verbose
# answer (e.g. the full capabilities list, or a BOM table) doesn't crowd out
# everything else in the window.
HISTORY_TURNS = 8
HISTORY_RESPONSE_CHAR_LIMIT = 500

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
        tool_registry: ToolRegistry | None = None,
    ):
        self._rag = rag_engine
        self._local = local_llm
        self._cloud = cloud_llm
        self._redis = redis_client
        self._cloud_daily_limit = cloud_daily_limit
        self._cloud_enabled = cloud_enabled
        self._tools = tool_registry or ToolRegistry()

    @property
    def rag_engine(self) -> RAGEngine:
        return self._rag

    @property
    def local_llm(self) -> LocalLLMClient:
        return self._local

    async def process_query(
        self, user_id: int, prompt: str, use_cloud_override: bool = False, is_admin: bool = False
    ) -> dict:
        start = time.monotonic()
        try:
            result = await self._process_query(user_id, prompt, use_cloud_override, is_admin)
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

    @staticmethod
    async def _load_recent_history(user_id: int) -> list[dict]:
        """The last HISTORY_TURNS (prompt, response) rows for this user,
        replayed as alternating user/assistant messages so the LLM sees
        actual prior conversation instead of treating every message as a
        cold start (e.g. "меня зовут Коля" -> next message "как меня
        зовут?" previously had nothing to go on). Scoped to user_id, not a
        specific chat — the messages table has no chat_id column, so this
        is a user's whole history across every chat/DM they've used the
        bot in, not just the current one.

        Best-effort like _audit: any DB failure degrades to no memory for
        this turn rather than breaking the response, and lets this be
        exercised by unit tests that mock the LLM clients but have no real
        database behind async_session_maker()."""
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(MessageModel)
                    .where(MessageModel.user_id == user_id)
                    .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                    .limit(HISTORY_TURNS)
                )
                rows = list(reversed(result.scalars().all()))
        except Exception as exc:
            logger.warning(f"Failed to load conversation history for user {user_id}: {exc}")
            return []

        history: list[dict] = []
        for row in rows:
            history.append({"role": "user", "content": row.prompt})
            history.append({"role": "assistant", "content": row.response[:HISTORY_RESPONSE_CHAR_LIMIT]})
        return history

    async def _generate_with_optional_tools(
        self, prompt: str, system_prompt: str, history: list[dict], is_admin: bool
    ) -> tuple[str, list[dict], dict]:
        """Runs the one local-LLM call each pipeline branch already makes,
        additionally letting the model call a tool instead of answering in
        text when TOOLS_ENABLED. Returns (text, tool_calls, usage) —
        tool_calls is empty whenever tools are off, no tool applies to this
        user, or the model just answered normally.

        TOOLS_USE_NATIVE_OLLAMA picks between Ollama's native tools=
        (verified live against this exact model/server/system-prompt
        combination — see capabilities in the tool-calling plan) and the
        fallback prompt+JSON pattern already proven by the four
        app/core/*_parser.py modules, kept as a config-flippable safety net
        without needing a redeploy if native tool-calling misbehaves later
        under traffic this session's spike didn't cover."""
        if not settings.TOOLS_ENABLED:
            text, usage = await self._local.generate_with_usage(prompt, system_prompt=system_prompt, history=history)
            return text, [], usage

        tools_schema = self._tools.to_ollama_schema(is_admin)
        if not tools_schema:
            text, usage = await self._local.generate_with_usage(prompt, system_prompt=system_prompt, history=history)
            return text, [], usage

        if settings.TOOLS_USE_NATIVE_OLLAMA:
            return await self._local.generate_with_tools(
                prompt, tools=tools_schema, system_prompt=system_prompt, history=history
            )

        fallback_system_prompt = f"{system_prompt}\n\n{self._tools.to_prompt_block(is_admin)}"
        text, usage = await self._local.generate_with_usage(
            prompt, system_prompt=fallback_system_prompt, history=history
        )
        parsed = try_parse_json(text.strip())
        if parsed and isinstance(parsed.get("tool"), str):
            return text, [{"name": parsed["tool"], "arguments": parsed.get("arguments") or {}}], usage
        return text, [], usage

    async def _dispatch_tool_call(
        self,
        tool_call: dict,
        user_id: int,
        prompt: str,
        is_admin: bool,
        events: list[dict],
        timing: dict[str, float],
        trace_id: str,
    ) -> dict:
        name = tool_call.get("name")
        arguments = tool_call.get("arguments") or {}
        spec = self._tools.get(name)

        if spec is None or (spec.admin_only and not is_admin):
            # Defense in depth: the catalog shown to the model already
            # excludes tools this user can't use, but nothing stops a model
            # from hallucinating a call to one it was never shown.
            logger.warning(f"Model called unknown/unauthorized tool '{name}' for user {user_id}")
            self._emit(events, "answer_generated", {"source": "tool_denied", "tool": name})
            return {
                "text": "Не удалось выполнить это действие.",
                "source": "tool_denied",
                "context_used": False,
                "rag_debug": None,
                "confidence": None,
                "llm_usage": {},
                "timing": timing,
                "rag_trace_id": trace_id,
                "trace_events": events,
            }

        self._emit(events, "tool_called", {"tool": name, "arguments": arguments})
        tool_start = time.monotonic()
        try:
            result = await spec.handler(**arguments)
        except TypeError as exc:
            # Malformed/missing arguments from the model — surfaced like any
            # other tool failure instead of raising into the user.
            result = ToolResult(text="Не хватает данных для выполнения действия.", success=False, error=str(exc))
        timing["tool_seconds"] = round(time.monotonic() - tool_start, 2)

        await self._audit(
            user_id,
            prompt,
            decision="tool_call",
            status="success" if result.success else "error",
            detail={"tool": name, "arguments": arguments, "success": result.success},
        )
        self._emit(events, "answer_generated", {"source": "tool", "tool": name, "success": result.success})

        return {
            "text": result.text,
            "source": "tool",
            "context_used": False,
            "rag_debug": None,
            "confidence": None,
            "llm_usage": {},
            "timing": timing,
            "rag_trace_id": trace_id,
            "trace_events": events,
            "structured_data": result.structured_data,
            "tool_attachment": result.attachment,
        }

    async def _process_query(self, user_id: int, prompt: str, use_cloud_override: bool, is_admin: bool = False) -> dict:
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
        history = await self._load_recent_history(user_id)

        if use_cloud_override:
            result = await self._call_cloud(
                user_id, prompt, context=None, rag_debug=None, timing=timing, events=events, history=history
            )
            result["rag_trace_id"] = trace_id
            return result

        if is_capability_question(prompt):
            # "Умеешь ли ты...?" answered deterministically from
            # capabilities.yaml, with no RAG lookup and no LLM call at all
            # — tried asking the local LLM to just relay the (always-
            # present-in-its-system-prompt) capabilities list first, and it
            # ignored it live, answering from its own generic training-data
            # priors about "an AI" instead (occasionally in Chinese). A
            # question this well-defined doesn't need generation, only
            # correct retrieval — see app/core/capabilities.py.
            text = format_capabilities_for_user(settings.CAPABILITIES_PATH)
            self._emit(
                events, "answer_generated", {"source": "capabilities", "confidence": "high", "length": len(text)}
            )
            return {
                "text": text,
                "source": "capabilities",
                "context_used": False,
                "rag_debug": None,
                "confidence": "high",
                "llm_usage": {},
                "timing": timing,
                "rag_trace_id": trace_id,
                "trace_events": events,
            }

        base_system_prompt = get_system_prompt(detect_prompt_type(prompt)) + CONFIDENCE_INSTRUCTION

        self._emit(events, "retrieval_started", {"collection": self._rag.collection_name})
        rag_start = time.monotonic()
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
            text, tool_calls, llm_usage = await self._generate_with_optional_tools(
                prompt, system_prompt=f"{base_system_prompt}\n\nКонтекст:\n{context}", history=history, is_admin=is_admin
            )
            timing["local_seconds"] = round(time.monotonic() - local_start, 2)
            if tool_calls:
                return await self._dispatch_tool_call(
                    tool_calls[0], user_id, prompt, is_admin, events, timing, trace_id
                )
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
            text, tool_calls, llm_usage = await self._generate_with_optional_tools(
                prompt, system_prompt=base_system_prompt, history=history, is_admin=is_admin
            )
            timing["local_seconds"] = round(time.monotonic() - local_start, 2)
            if tool_calls:
                return await self._dispatch_tool_call(
                    tool_calls[0], user_id, prompt, is_admin, events, timing, trace_id
                )
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
            user_id, prompt, context=context, rag_debug=rag_debug, timing=timing, events=events, history=history
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
        history: list[dict] | None = None,
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
            text, llm_usage = await self._cloud.generate_with_usage(prompt, context=context, history=history)
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
