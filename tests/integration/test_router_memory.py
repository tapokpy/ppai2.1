from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.database import async_session_maker
from app.core.router import HISTORY_RESPONSE_CHAR_LIMIT, HISTORY_TURNS, CascadeRouter
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.services.local_llm import LocalLLMClient
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_user(telegram_id: int) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="memory", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def _seed_message(user_id: int, prompt: str, response: str) -> None:
    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=user_id, prompt=prompt, response=response, source="local", context_used=False
            )
        )
        await session.commit()


def _make_router(local_response: str = "ответ") -> CascadeRouter:
    rag_engine = MagicMock()
    rag_engine.collection_name = "knowledge_base"
    rag_engine.embedding_model_name = "all-MiniLM-L6-v2"
    rag_engine.query.return_value = {
        "found": False, "max_score": 0.1, "documents": [], "metadatas": [], "scores": []
    }

    local_llm = MagicMock()
    local_llm.model_name = "qwen2.5:7b"
    local_llm.generate_with_usage = AsyncMock(return_value=(local_response, {}))
    local_llm.needs_cloud = LocalLLMClient.needs_cloud

    cloud_llm = MagicMock()

    return CascadeRouter(
        rag_engine=rag_engine,
        local_llm=local_llm,
        cloud_llm=cloud_llm,
        redis_client=FakeRedis(),
        cloud_daily_limit=50,
        cloud_enabled=False,
    )


@pytest.mark.asyncio
async def test_prior_turn_is_replayed_to_local_llm(clean_db):
    user = await _seed_user(30)
    await _seed_message(user.id, "меня зовут Коля", "Приятно познакомиться, Коля!")
    router = _make_router()

    await router.process_query(user_id=user.id, prompt="как меня зовут?")

    history = router._local.generate_with_usage.call_args.kwargs["history"]
    assert history == [
        {"role": "user", "content": "меня зовут Коля"},
        {"role": "assistant", "content": "Приятно познакомиться, Коля!"},
    ]


@pytest.mark.asyncio
async def test_history_is_scoped_per_user(clean_db):
    user_a = await _seed_user(31)
    user_b = await _seed_user(32)
    await _seed_message(user_a.id, "секрет пользователя A", "ответ A")
    router = _make_router()

    await router.process_query(user_id=user_b.id, prompt="вопрос")

    assert router._local.generate_with_usage.call_args.kwargs["history"] == []


@pytest.mark.asyncio
async def test_history_is_capped_at_history_turns(clean_db):
    user = await _seed_user(33)
    for i in range(HISTORY_TURNS + 5):
        await _seed_message(user.id, f"вопрос {i}", f"ответ {i}")
    router = _make_router()

    await router.process_query(user_id=user.id, prompt="последний вопрос")

    history = router._local.generate_with_usage.call_args.kwargs["history"]
    assert len(history) == HISTORY_TURNS * 2
    # Oldest-first, and it's the most RECENT turns that got kept (not the
    # first ones seeded) — the tail of the seeded range, not the head.
    assert history[0] == {"role": "user", "content": "вопрос 5"}
    assert history[-1] == {"role": "assistant", "content": f"ответ {HISTORY_TURNS + 4}"}


@pytest.mark.asyncio
async def test_long_past_response_is_truncated_in_history(clean_db):
    user = await _seed_user(34)
    long_response = "x" * (HISTORY_RESPONSE_CHAR_LIMIT + 100)
    await _seed_message(user.id, "длинный вопрос", long_response)
    router = _make_router()

    await router.process_query(user_id=user.id, prompt="следующий вопрос")

    history = router._local.generate_with_usage.call_args.kwargs["history"]
    assert len(history[1]["content"]) == HISTORY_RESPONSE_CHAR_LIMIT
