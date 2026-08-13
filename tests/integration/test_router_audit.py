from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.models.sqlalchemy.audit_log import AuditLog
from app.models.sqlalchemy.user import User
from app.services.local_llm import LocalLLMClient
from sqlalchemy import select
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _seed_user(telegram_id: int) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="audit", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


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
async def test_process_query_writes_audit_log_on_success(clean_db):
    user = await _seed_user(20)
    router = _make_router()

    await router.process_query(user_id=user.id, prompt="вопрос про экран")

    async with async_session_maker() as session:
        rows = (await session.execute(select(AuditLog).where(AuditLog.user_id == user.id))).scalars().all()

    assert len(rows) == 1
    assert rows[0].module == "cascade_router"
    assert rows[0].status == "success"
    assert rows[0].command_text == "вопрос про экран"


@pytest.mark.asyncio
async def test_process_query_writes_audit_log_on_exception(clean_db):
    user = await _seed_user(21)
    router = _make_router()
    router._local.generate_with_usage = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await router.process_query(user_id=user.id, prompt="сломается")

    async with async_session_maker() as session:
        rows = (await session.execute(select(AuditLog).where(AuditLog.user_id == user.id))).scalars().all()

    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].decision == "exception"
