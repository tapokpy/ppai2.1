import httpx
import pytest
from redis.asyncio import Redis

from app.api.v1.endpoints.auth import get_redis_client
from app.core.config import settings
from app.core.database import async_session_maker
from app.core.security import decode_access_token
from app.main import app
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres, requires_redis

pytestmark = [requires_postgres, requires_redis]


async def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
async def _override_redis():
    real_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def _get_test_redis_client():
        yield real_client

    app.dependency_overrides[get_redis_client] = _get_test_redis_client
    yield
    app.dependency_overrides.pop(get_redis_client, None)
    await real_client.aclose()


@pytest.mark.asyncio
async def test_generate_ott_requires_internal_token(clean_db):
    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/generate_ott",
            json={"telegram_id": 1},
            headers={"X-Internal-Token": "wrong-token"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_generate_ott_returns_404_for_unknown_user(clean_db):
    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/generate_ott",
            json={"telegram_id": 999999},
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_ott_and_sso_full_flow(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=321, username="webuser")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    async with await _client() as client:
        ott_response = await client.post(
            "/api/v1/auth/generate_ott",
            json={"telegram_id": 321},
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        assert ott_response.status_code == 200
        ott = ott_response.json()["ott"]

        sso_response = await client.post("/api/v1/auth/sso", json={"ott": ott})

    assert sso_response.status_code == 200
    body = sso_response.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"]) == user.id


@pytest.mark.asyncio
async def test_sso_rejects_unknown_ott(clean_db):
    async with await _client() as client:
        response = await client.post("/api/v1/auth/sso", json={"ott": "does-not-exist"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sso_rejects_reused_ott(clean_db):
    async with async_session_maker() as session:
        user = User(telegram_id=654, username="webuser2")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    async with await _client() as client:
        ott_response = await client.post(
            "/api/v1/auth/generate_ott",
            json={"telegram_id": 654},
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        ott = ott_response.json()["ott"]

        first = await client.post("/api/v1/auth/sso", json={"ott": ott})
        second = await client.post("/api/v1/auth/sso", json={"ott": ott})

    assert first.status_code == 200
    assert second.status_code == 401
