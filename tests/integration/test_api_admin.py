from unittest.mock import patch

import httpx
import pytest

from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.main import app
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


async def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _seed_user(telegram_id: int, is_approved: bool = True) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="u", is_approved=is_approved)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_analytics_requires_admin(clean_db):
    user = await _seed_user(1)
    token = create_access_token(user_id=user.id)

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [999]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/analytics", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_analytics_returns_aggregates_for_admin(clean_db):
    admin_user = await _seed_user(2)
    other_user = await _seed_user(3)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=other_user.id,
                telegram_message_id=None,
                prompt="p",
                response="r",
                source="local",
                context_used=False,
            )
        )
        session.add(
            MessageModel(
                user_id=other_user.id,
                telegram_message_id=None,
                prompt="p2",
                response="r2",
                source="rag",
                context_used=True,
            )
        )
        await session.commit()

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [2]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/analytics", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_users"] == 2
    assert body["approved_users"] == 2
    assert body["total_messages"] == 2
    assert {row["source"]: row["count"] for row in body["messages_by_source"]} == {"local": 1, "rag": 1}


@pytest.mark.asyncio
async def test_rag_trace_returns_debug_payload(clean_db):
    admin_user = await _seed_user(4)
    other_user = await _seed_user(5)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        message = MessageModel(
            user_id=other_user.id,
            telegram_message_id=None,
            prompt="Какой шаг пикселя?",
            response="P2.5",
            source="rag",
            context_used=True,
            rag_debug={"max_score": 0.91, "retrieved": [{"snippet": "P2.5 модуль", "score": 0.91, "metadata": {}}]},
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        message_id = message.id

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [4]
        async with await _client() as client:
            response = await client.get(
                f"/api/v1/admin/rag_trace/{message_id}", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rag"
    assert body["rag_debug"]["max_score"] == 0.91


@pytest.mark.asyncio
async def test_rag_trace_404_for_unknown_message(clean_db):
    admin_user = await _seed_user(6)
    token = create_access_token(user_id=admin_user.id)

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [6]
        async with await _client() as client:
            response = await client.get(
                "/api/v1/admin/rag_trace/999999", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 404
