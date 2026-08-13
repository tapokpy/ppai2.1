import socket
from urllib.parse import urlparse

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

# _dispose_engine_pool_per_test lives in tests/conftest.py now (autouse
# fixtures apply repo-wide, not just here) — nothing to import, it's
# picked up automatically by pytest's conftest collection.


def _tcp_reachable(url: str, default_port: int) -> bool:
    parsed = urlparse(url.replace("+asyncpg", ""))
    try:
        with socket.create_connection((parsed.hostname, parsed.port or default_port), timeout=1):
            return True
    except OSError:
        return False


requires_postgres = pytest.mark.skipif(
    not _tcp_reachable(settings.POSTGRES_DSN, 5432),
    reason="Postgres is not reachable (run `docker compose up -d postgres`)",
)

requires_redis = pytest.mark.skipif(
    not _tcp_reachable(settings.REDIS_URL, 6379),
    reason="Redis is not reachable (run `docker compose up -d redis`)",
)

_TABLES_TO_RESET = (
    "messages, activity_logs, business_rules, reminders, users, showroom_media, todos, engineering_docs, "
    "stock_items, cells, shelves, racks, warehouses, project_files, projects, audit_logs"
)


@pytest.fixture
async def clean_db():
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {_TABLES_TO_RESET} RESTART IDENTITY CASCADE"))
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {_TABLES_TO_RESET} RESTART IDENTITY CASCADE"))
