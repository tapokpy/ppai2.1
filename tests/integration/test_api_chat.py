from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

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


@pytest.fixture(autouse=True)
def _default_cascade_router_state():
    # app.state.cascade_router is normally populated by the app's lifespan
    # handler, which the ASGITransport client below does not trigger.
    app.state.cascade_router = AsyncMock()
    yield


async def _seed_user(telegram_id: int = 42) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="webuser")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_chat_requires_bearer_token(clean_db):
    async with await _client() as client:
        response = await client.post("/api/v1/chat", json={"message": "привет"})

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_chat_rejects_invalid_token(clean_db):
    async with await _client() as client:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "привет"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_proxies_to_cascade_router(clean_db):
    user = await _seed_user()
    token = create_access_token(user_id=user.id)
    fake_cascade_router = AsyncMock()
    fake_cascade_router.process_query.return_value = {
        "text": "Ответ ассистента",
        "source": "rag",
        "context_used": True,
    }
    app.state.cascade_router = fake_cascade_router

    async with await _client() as client:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "Сколько модулей нужно?"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "Ответ ассистента"
    assert body["source"] == "rag"
    assert body["context_used"] is True

    fake_cascade_router.process_query.assert_awaited_once_with(
        user_id=user.id, prompt="Сколько модулей нужно?"
    )


@pytest.mark.asyncio
async def test_chat_persists_message_with_null_telegram_message_id(clean_db):
    user = await _seed_user()
    token = create_access_token(user_id=user.id)
    fake_cascade_router = AsyncMock()
    fake_cascade_router.process_query.return_value = {
        "text": "Ответ ассистента",
        "source": "local",
        "context_used": False,
    }
    app.state.cascade_router = fake_cascade_router

    async with await _client() as client:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "Сколько модулей нужно?"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200

    async with async_session_maker() as session:
        result = await session.execute(select(MessageModel).where(MessageModel.user_id == user.id))
        stored_message = result.scalar_one()

    assert stored_message.telegram_message_id is None
    assert stored_message.prompt == "Сколько модулей нужно?"
    assert stored_message.response == "Ответ ассистента"
    assert stored_message.source == "local"
