import httpx
import pytest

from app.main import app
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_health_ok():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
