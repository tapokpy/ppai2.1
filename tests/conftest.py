import pytest

from app.core.database import engine


@pytest.fixture(autouse=True)
async def _dispose_engine_pool_per_test():
    # pytest-asyncio spins up a fresh event loop per test; pooled asyncpg
    # connections from a previous test's loop are unusable in the new one.
    # Applies repo-wide (not just tests/integration/) now that
    # CascadeRouter.process_query does a best-effort DB write on every
    # call (see app/services/audit.py) — even pure-mock unit tests that
    # exercise it pick up a real connection pool.
    await engine.dispose()
    yield
    await engine.dispose()
