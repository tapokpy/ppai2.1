from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_reports_degraded_when_db_unreachable():
    fake_engine = MagicMock()
    fake_engine.connect.side_effect = ConnectionError("db down")

    with patch("app.main.engine", fake_engine):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": False}


@pytest.mark.asyncio
async def test_lifespan_disposes_engine_on_shutdown():
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()

    with (
        patch("app.main.engine", fake_engine),
        patch("app.main.build_cascade_router", return_value=MagicMock()) as build_mock,
        patch("app.main.configure_file_logging"),
    ):
        async with app.router.lifespan_context(app):
            pass

    build_mock.assert_called_once()
    fake_engine.dispose.assert_awaited_once()
