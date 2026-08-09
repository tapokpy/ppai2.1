import socket
from urllib.parse import urlparse

import pytest

from app.core.config import settings


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
