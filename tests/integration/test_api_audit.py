from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.main import app
from app.models.sqlalchemy.audit_log import AuditLog
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.fixture(autouse=True)
def _default_cascade_router_state():
    app.state.cascade_router = MagicMock()
    yield


async def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _seed_user(telegram_id: int) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="u", is_approved=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_audit_requires_admin(clean_db):
    user = await _seed_user(10)
    token = create_access_token(user_id=user.id)

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [999]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/audit", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_returns_entries_for_admin(clean_db):
    admin_user = await _seed_user(11)
    other_user = await _seed_user(12)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        session.add(
            AuditLog(
                user_id=other_user.id,
                command_text="/project_new Объект 1",
                module="projects",
                decision="project_created",
                status="success",
                detail={"project_id": 1},
            )
        )
        await session.commit()

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [admin_user.telegram_id]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/audit", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["module"] == "projects"
    assert body["items"][0]["decision"] == "project_created"
    assert body["items"][0]["detail"] == {"project_id": 1}


@pytest.mark.asyncio
async def test_audit_filters_by_module_and_status(clean_db):
    admin_user = await _seed_user(13)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        session.add_all(
            [
                AuditLog(
                    user_id=admin_user.id, command_text="a", module="warehouse", decision="x", status="success"
                ),
                AuditLog(
                    user_id=admin_user.id, command_text="b", module="cascade_router", decision="y", status="error"
                ),
            ]
        )
        await session.commit()

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [admin_user.telegram_id]
        async with await _client() as client:
            response = await client.get(
                "/api/v1/admin/audit",
                params={"module": "warehouse"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["module"] == "warehouse"
